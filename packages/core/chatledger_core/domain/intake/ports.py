"""Intake ports: repositories, blob store, archive inspector and unit of work."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Protocol
from uuid import UUID

from chatledger_core.domain.audit.audit_event import AuditLog
from chatledger_core.domain.intake.archive import ArchiveEntry
from chatledger_core.domain.intake.collection import BlobRef, Collection, NewCollection
from chatledger_core.domain.intake.matter import Matter, MatterSummary


class MatterRepository(Protocol):
    def add(self, name: str, description: str | None) -> Matter:
        """Insert a matter; raises ``MatterNameTakenError`` on a case-insensitive clash."""
        ...

    def get(self, matter_id: UUID) -> MatterSummary | None: ...

    def get_for_update(self, matter_id: UUID) -> Matter | None:
        """Fetch the matter row and lock it until the transaction ends."""
        ...

    def list_summaries(self) -> list[MatterSummary]:
        """All matters, newest first, with collection counts and total size."""
        ...

    def name_exists(self, name: str) -> bool: ...


class CollectionRepository(Protocol):
    def ensure_blob(self, blob: BlobRef) -> None:
        """Insert the blob row unless it already exists."""
        ...

    def add(self, collection: NewCollection) -> Collection: ...

    def find_by_sha(self, matter_id: UUID, sha256: str) -> Collection | None: ...

    def count_for_matter(self, matter_id: UUID) -> int: ...

    def list_for_matter(self, matter_id: UUID) -> list[Collection]:
        """Collections in ``added_at`` order."""
        ...

    def get(self, matter_id: UUID, collection_id: UUID) -> Collection | None: ...


class BlobStore(Protocol):
    def inspect_staged(self, staged_path: Path, sha256: str | None = None) -> tuple[str, int]:
        """Return ``(sha256, size_bytes)`` of the staged file; hash it when no digest is given."""
        ...

    def put_from_staging(self, staged_path: Path, sha256: str) -> BlobRef:
        """Move the staged file into the store (idempotent for existing digests)."""
        ...

    def discard_staged(self, staged_path: Path) -> None: ...

    def path_for(self, sha256: str) -> Path: ...

    def exists(self, sha256: str) -> bool: ...

    def ground_truth_path_for(self, sha256: str) -> Path:
        """Where the generator's ground truth for the blob with this digest is stored."""
        ...

    def put_ground_truth(self, sha256: str, staged_path: Path) -> Path:
        """Move a staged ground-truth file beside its blob, read-only (idempotent)."""
        ...

    def remove_ground_truth_if_unreferenced(self, sha256: str) -> bool:
        """Delete the ground truth when no ZIP blob with that digest exists."""
        ...


class ArchiveInspector(Protocol):
    def read_entries(self, path: Path) -> list[ArchiveEntry]:
        """Read the ZIP central directory only; raises ``ArchiveRejectedError`` if not a ZIP."""
        ...


class IntakeUnitOfWork(Protocol):
    """One database transaction spanning the intake repositories and the audit log."""

    @property
    def matters(self) -> MatterRepository: ...

    @property
    def collections(self) -> CollectionRepository: ...

    @property
    def audit(self) -> AuditLog: ...

    def __enter__(self) -> IntakeUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


UnitOfWorkFactory = Callable[[], IntakeUnitOfWork]
