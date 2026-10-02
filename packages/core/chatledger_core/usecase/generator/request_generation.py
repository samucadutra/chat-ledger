"""Request a synthetic export: validate, resolve the re-delivery base, persist, enqueue."""

from __future__ import annotations

from uuid import UUID

from chatledger_core.domain.generator.errors import GenerationOverlapBaseInvalidError
from chatledger_core.domain.generator.params import (
    GenerationParams,
    params_for_effective,
    validate_params,
)
from chatledger_core.domain.generator.ports import (
    GenerationRecord,
    GenerationRepository,
    NewGeneration,
)
from chatledger_core.domain.intake.errors import MatterNotFoundError
from chatledger_core.domain.intake.ports import UnitOfWorkFactory
from chatledger_core.domain.jobs.queue import JobQueue

GENERATE_KIND = "generate"


class RequestGeneration:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        generations: GenerationRepository,
        queue: JobQueue,
    ) -> None:
        self._uow_factory = uow_factory
        self._generations = generations
        self._queue = queue

    def execute(
        self,
        matter_id: UUID,
        *,
        seed: object,
        preset: object,
        profile: object,
        messages: object = None,
        conversations: object = None,
        overlap_of_collection_id: UUID | None = None,
    ) -> GenerationRecord:
        with self._uow_factory() as uow:
            if uow.matters.get(matter_id) is None:
                raise MatterNotFoundError
            base_collection = (
                uow.collections.get(matter_id, overlap_of_collection_id)
                if overlap_of_collection_id is not None
                else None
            )

        params: GenerationParams
        if overlap_of_collection_id is None:
            params = validate_params(
                seed=seed,
                preset=preset,
                profile=profile,
                messages=messages,
                conversations=conversations,
            )
        else:
            base = self._generations.find_by_collection(overlap_of_collection_id)
            if base_collection is None or base is None or base.matter_id != matter_id:
                raise GenerationOverlapBaseInvalidError
            # A re-delivery inherits everything but the seed from its base.
            params = params_for_effective(
                seed=_checked_seed(seed),
                preset=base.preset,
                profile=base.profile,
                messages=base.messages,
                conversations=base.conversations,
            )

        record = self._generations.add(
            NewGeneration(
                matter_id=matter_id,
                seed=params.seed,
                preset=params.preset.value,
                profile=params.profile.value,
                messages=params.messages,
                conversations=params.conversations,
                overlap_of_collection_id=overlap_of_collection_id,
            )
        )
        try:
            job = self._queue.enqueue(GENERATE_KIND, {"generation_id": str(record.id)})
            self._generations.attach_job(record.id, job.id)
        except BaseException:
            self._generations.delete(record.id)
            raise
        fresh = self._generations.get(record.id)
        assert fresh is not None
        return fresh


def _checked_seed(seed: object) -> int:
    # Reuse the shared seed rule (and its message) without needing the other fields.
    params = validate_params(seed=seed, preset="small", profile="clean")
    return params.seed
