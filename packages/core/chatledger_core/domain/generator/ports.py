"""Ports of the generator: output sinks, disk probe and the generation repository."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class ExportSink(Protocol):
    def add_entry(self, path: str, data: bytes) -> None:
        """Append one archive entry (callers add them in sorted path order)."""
        ...

    def close(self) -> tuple[str, int]:
        """Finish the archive; return ``(sha256, size_bytes)`` of the written file."""
        ...

    def abort(self) -> None:
        """Release handles without finishing the archive (the caller deletes the file)."""
        ...


class GroundTruthSink(Protocol):
    def write(self, chunks: Iterable[bytes]) -> tuple[str, int]:
        """Write the chunks as one file; return ``(sha256, size_bytes)``."""
        ...


class DiskSpaceProbe(Protocol):
    def free_bytes(self, path: str) -> int: ...


@dataclass(frozen=True)
class GenerationRecord:
    id: UUID
    matter_id: UUID
    seed: int
    preset: str
    profile: str
    messages: int
    conversations: int
    overlap_of_collection_id: UUID | None
    overlap_days_pct: int
    job_id: UUID | None
    state: str  # effective state (queued, running, done, failed)
    progress_messages: int
    collection_id: UUID | None
    ground_truth_sha256: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    job_attempts: int = 0


@dataclass(frozen=True)
class NewGeneration:
    matter_id: UUID
    seed: int
    preset: str
    profile: str
    messages: int
    conversations: int
    overlap_of_collection_id: UUID | None
    overlap_days_pct: int = 30


class GenerationRepository(Protocol):
    def add(self, generation: NewGeneration) -> GenerationRecord: ...

    def get(self, generation_id: UUID) -> GenerationRecord | None:
        """Fetch one generation with its effective state (derived from the job)."""
        ...

    def list_for_matter(self, matter_id: UUID) -> list[GenerationRecord]:
        """Newest first."""
        ...

    def delete(self, generation_id: UUID) -> None: ...

    def attach_job(self, generation_id: UUID, job_id: UUID) -> None: ...

    def reset_for_retry(self, generation_id: UUID, job_id: UUID) -> GenerationRecord: ...

    def mark_running(self, generation_id: UUID) -> None: ...

    def update_progress(self, generation_id: UUID, progress_messages: int) -> None: ...

    def mark_done(
        self,
        generation_id: UUID,
        *,
        collection_id: UUID,
        ground_truth_sha256: str,
        progress_messages: int,
    ) -> None: ...

    def mark_failed(self, generation_id: UUID, code: str, message: str) -> None: ...

    def find_by_collection(self, collection_id: UUID) -> GenerationRecord | None: ...

    def find_seed_for_collection(self, matter_id: UUID, collection_id: UUID) -> int | None:
        """Seed of the generation that produced the collection (None for uploads)."""
        ...
