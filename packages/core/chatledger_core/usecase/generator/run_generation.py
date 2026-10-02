"""Job body of the ``generate`` kind: generate, store the ground truth, register the collection."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from chatledger_core.domain._shared.errors import DomainError
from chatledger_core.domain.generator.errors import (
    DUPLICATE_MESSAGE,
    InsufficientDiskSpaceError,
)
from chatledger_core.domain.generator.params import GenerationParams, params_for_effective
from chatledger_core.domain.generator.ports import (
    ExportSink,
    GenerationRecord,
    GenerationRepository,
    GroundTruthSink,
)
from chatledger_core.domain.intake.errors import (
    CollectionDuplicateError,
    CollectionLimitReachedError,
    MatterNotFoundError,
)
from chatledger_core.domain.intake.ports import BlobStore, UnitOfWorkFactory
from chatledger_core.usecase.generator.generate_export import (
    GenerateExport,
    GenerationAborted,
    GenerationResult,
    OverlapSpec,
)
from chatledger_core.usecase.intake.register_collection import RegisterCollection

OVERLAP_BASE_GONE_MESSAGE = "The re-delivery base collection is no longer available."
FORCED_FAILURE_MESSAGE = "Generation failed on purpose (GENERATOR_TEST_FAIL_ALWAYS is set)."


class LeaseLostError(RuntimeError):
    """The job lease was lost mid-generation; the queue decides what happens next."""


class RunGeneration:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        generations: GenerationRepository,
        register_collection: RegisterCollection,
        blob_store: BlobStore,
        generate_export: GenerateExport,
        tmp_dir: Path,
        zip_sink_factory: Callable[[Path], ExportSink],
        truth_sink_factory: Callable[[Path], GroundTruthSink],
        progress_every: int = 5_000,
        fail_always: bool = False,
        pause_ms_per_conversation: int = 0,
    ) -> None:
        self._uow_factory = uow_factory
        self._generations = generations
        self._register = register_collection
        self._blobs = blob_store
        self._generate = generate_export
        self._tmp_dir = tmp_dir
        self._zip_sink_factory = zip_sink_factory
        self._truth_sink_factory = truth_sink_factory
        self._progress_every = progress_every
        self._fail_always = fail_always
        self._pause_ms = pause_ms_per_conversation

    # ------------------------------------------------------------------ public
    def execute(self, generation_id: UUID, lease_lost: Callable[[], bool]) -> None:
        record = self._generations.get(generation_id)
        if record is None or record.state == "done":
            return
        self._generations.mark_running(generation_id)
        if self._fail_always:
            raise RuntimeError(FORCED_FAILURE_MESSAGE)

        params = params_for_effective(
            seed=record.seed,
            preset=record.preset,
            profile=record.profile,
            messages=record.messages,
            conversations=record.conversations,
        )
        with self._uow_factory() as uow:
            if uow.matters.get(record.matter_id) is None:
                self._fail(record, MatterNotFoundError())
                return
        overlap = self._resolve_overlap(record)
        if record.overlap_of_collection_id is not None and overlap is None:
            self._generations.mark_failed(
                record.id, "GENERATION_OVERLAP_BASE_INVALID", OVERLAP_BASE_GONE_MESSAGE
            )
            return

        zip_part = self._tmp_dir / f"gen-{record.id}.part"
        truth_part = self._tmp_dir / f"gen-{record.id}.gt.part"
        for stale in (zip_part, truth_part):
            stale.unlink(missing_ok=True)
        try:
            result = self._run_pipeline(record, params, overlap, zip_part, truth_part, lease_lost)
            if result is None:
                return
            self._store_and_register(record, params, result, zip_part, truth_part)
        finally:
            for leftover in (zip_part, truth_part):
                with contextlib.suppress(OSError):
                    leftover.unlink(missing_ok=True)

    # ------------------------------------------------------------------ steps
    def _resolve_overlap(self, record: GenerationRecord) -> OverlapSpec | None:
        if record.overlap_of_collection_id is None:
            return None
        base_seed = self._generations.find_seed_for_collection(
            record.matter_id, record.overlap_of_collection_id
        )
        if base_seed is None:
            return None
        return OverlapSpec(base_seed, record.overlap_days_pct)

    def _run_pipeline(
        self,
        record: GenerationRecord,
        params: GenerationParams,
        overlap: OverlapSpec | None,
        zip_part: Path,
        truth_part: Path,
        lease_lost: Callable[[], bool],
    ) -> GenerationResult | None:
        zip_sink = self._zip_sink_factory(zip_part)
        truth_sink = self._truth_sink_factory(truth_part)
        last_reported = 0

        def on_progress(done: int) -> None:
            nonlocal last_reported
            if done - last_reported >= self._progress_every:
                last_reported = done
                self._generations.update_progress(record.id, done)

        try:
            return self._generate.execute(
                params,
                zip_sink=zip_sink,
                ground_truth_sink=truth_sink,
                disk_path=str(self._tmp_dir),
                overlap=overlap,
                on_progress=on_progress,
                should_abort=lease_lost,
                pause_ms_per_conversation=self._pause_ms,
            )
        except InsufficientDiskSpaceError as exc:
            self._fail(record, exc)
            return None
        except GenerationAborted:
            raise LeaseLostError("job lease lost while generating") from None

    def _store_and_register(
        self,
        record: GenerationRecord,
        params: GenerationParams,
        result: GenerationResult,
        zip_part: Path,
        truth_part: Path,
    ) -> None:
        digest = result.zip_sha256
        self._blobs.put_ground_truth(digest, truth_part)
        try:
            collection = self._register.execute(
                record.matter_id, zip_part, params.filename, source="generator", sha256=digest
            )
        except CollectionDuplicateError as exc:
            existing_id = UUID(exc.details["existing_collection_id"])
            existing = self._generations.find_by_collection(existing_id)
            if existing is None and self._is_generator_collection(record, existing_id):
                self._finish(record, existing_id, result)
                return
            self._blobs.remove_ground_truth_if_unreferenced(digest)
            self._generations.mark_failed(record.id, exc.code, DUPLICATE_MESSAGE)
            return
        except (CollectionLimitReachedError, MatterNotFoundError, DomainError) as exc:
            self._blobs.remove_ground_truth_if_unreferenced(digest)
            self._fail(record, exc)
            return
        except BaseException:
            self._blobs.remove_ground_truth_if_unreferenced(digest)
            raise
        self._finish(record, collection.id, result)

    def _is_generator_collection(self, record: GenerationRecord, collection_id: UUID) -> bool:
        """A crash after registration leaves a generator collection no generation points at."""
        with self._uow_factory() as uow:
            existing = uow.collections.get(record.matter_id, collection_id)
        return existing is not None and existing.source.value == "generator"

    def _finish(
        self, record: GenerationRecord, collection_id: UUID, result: GenerationResult
    ) -> None:
        self._generations.mark_done(
            record.id,
            collection_id=collection_id,
            ground_truth_sha256=result.ground_truth_sha256,
            progress_messages=record.messages,
        )

    def _fail(self, record: GenerationRecord, exc: DomainError) -> None:
        self._generations.mark_failed(record.id, exc.code, exc.message)
