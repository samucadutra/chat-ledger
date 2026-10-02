"""Streaming generation pipeline: plan, render one conversation at a time, write, summarise."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from chatledger_core.domain.generator.errors import InsufficientDiskSpaceError
from chatledger_core.domain.generator.ground_truth import (
    AnomalyRecord,
    GroundTruthMeta,
    Overlap,
    canonical_chunks,
    sort_key,
)
from chatledger_core.domain.generator.overlap import build_overlap, duplicate_records
from chatledger_core.domain.generator.params import GenerationParams
from chatledger_core.domain.generator.plan import (
    GENERATOR_VERSION,
    SegmentPlan,
    Workspace,
    build_workspace,
)
from chatledger_core.domain.generator.ports import DiskSpaceProbe, ExportSink, GroundTruthSink
from chatledger_core.domain.generator.render import ConversationRenderer, render_root_files

BYTES_PER_MESSAGE = 350
DISK_HEADROOM = 1.5


class GenerationAborted(Exception):  # noqa: N818 - control flow, not an error condition
    """Raised through ``should_abort`` callbacks to stop generation (e.g. lost job lease)."""


@dataclass(frozen=True)
class OverlapSpec:
    base_seed: int
    days_pct: int


@dataclass(frozen=True)
class GenerationResult:
    filename: str
    ground_truth_filename: str
    zip_sha256: str
    zip_size: int
    ground_truth_sha256: str
    ground_truth_size: int
    message_records: int
    anomaly_count: int


class GenerateExport:
    def __init__(
        self,
        disk_probe: DiskSpaceProbe,
        *,
        bytes_per_message: int = BYTES_PER_MESSAGE,
        headroom: float = DISK_HEADROOM,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._probe = disk_probe
        self._bytes_per_message = bytes_per_message
        self._headroom = headroom
        self._sleep = sleep

    def check_disk(self, messages: int, disk_path: str) -> None:
        required = int(self._bytes_per_message * messages * self._headroom)
        free = self._probe.free_bytes(disk_path)
        if free < required:
            raise InsufficientDiskSpaceError(required, free)

    def execute(
        self,
        params: GenerationParams,
        *,
        zip_sink: ExportSink,
        ground_truth_sink: GroundTruthSink,
        disk_path: str,
        overlap: OverlapSpec | None = None,
        on_progress: Callable[[int], None] | None = None,
        should_abort: Callable[[], bool] | None = None,
        pause_ms_per_conversation: int = 0,
    ) -> GenerationResult:
        self.check_disk(params.messages, disk_path)
        try:
            return self._run(
                params,
                zip_sink=zip_sink,
                ground_truth_sink=ground_truth_sink,
                overlap=overlap,
                on_progress=on_progress,
                should_abort=should_abort,
                pause_ms_per_conversation=pause_ms_per_conversation,
            )
        except BaseException:
            zip_sink.abort()
            raise

    def _run(
        self,
        params: GenerationParams,
        *,
        zip_sink: ExportSink,
        ground_truth_sink: GroundTruthSink,
        overlap: OverlapSpec | None,
        on_progress: Callable[[int], None] | None,
        should_abort: Callable[[], bool] | None,
        pause_ms_per_conversation: int,
    ) -> GenerationResult:
        overlap_plan = None
        if overlap is not None:
            overlap_plan = build_overlap(params, overlap.base_seed, overlap.days_pct)
            workspace: Workspace = overlap_plan.base
        else:
            workspace = build_workspace(params)

        order: list[tuple[str, str, int | None]] = [
            (name, name, None) for name in render_root_files(workspace)
        ]
        order.extend((seg.conv.folder + "/", "", i) for i, seg in enumerate(workspace.segments))
        order.sort(key=lambda entry: entry[0])
        root_files = render_root_files(workspace)

        anomalies: list[AnomalyRecord] = []
        message_records = 0
        generated = 0
        for _key, root_name, index in order:
            if index is None:
                zip_sink.add_entry(root_name, root_files[root_name])
                continue
            segment = workspace.segments[index]
            for generated_file in ConversationRenderer(workspace, segment).files(
                collect_ts=overlap_plan is not None
            ):
                generated += generated_file.base_count
                if should_abort is not None and should_abort():
                    raise GenerationAborted
                if overlap_plan is not None:
                    if generated_file.day < overlap_plan.window_start:
                        if on_progress is not None:
                            on_progress(generated)
                        continue
                    anomalies.extend(
                        duplicate_records(
                            segment.conv.id, generated_file.path, generated_file.record_ts or []
                        )
                    )
                zip_sink.add_entry(generated_file.path, generated_file.data)
                anomalies.extend(generated_file.anomalies)
                message_records += generated_file.base_count
                if on_progress is not None:
                    on_progress(generated)
            if overlap_plan is not None:
                new_segment: SegmentPlan = overlap_plan.new_segments[index]
                for generated_file in ConversationRenderer(workspace, new_segment).files():
                    zip_sink.add_entry(generated_file.path, generated_file.data)
                    anomalies.extend(generated_file.anomalies)
                    message_records += generated_file.base_count
            if pause_ms_per_conversation > 0:
                self._sleep(pause_ms_per_conversation / 1000)
            if should_abort is not None and should_abort():
                raise GenerationAborted
        zip_sha, zip_size = zip_sink.close()

        anomalies.sort(key=sort_key)
        meta = GroundTruthMeta(
            generator_version=GENERATOR_VERSION,
            seed=params.seed,
            preset=params.preset.value,
            profile=params.profile.value,
            messages=params.messages,
            conversations=params.conversations,
            message_records=message_records,
            overlap=(
                None
                if overlap is None
                else Overlap(base_seed=overlap.base_seed, days_pct=overlap.days_pct)
            ),
        )
        gt_sha, gt_size = ground_truth_sink.write(canonical_chunks(meta, anomalies))
        return GenerationResult(
            filename=params.filename,
            ground_truth_filename=params.ground_truth_filename,
            zip_sha256=zip_sha,
            zip_size=zip_size,
            ground_truth_sha256=gt_sha,
            ground_truth_size=gt_size,
            message_records=message_records,
            anomaly_count=len(anomalies),
        )
