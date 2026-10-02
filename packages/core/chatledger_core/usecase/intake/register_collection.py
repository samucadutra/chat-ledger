"""Register a staged ZIP as a collection (shared by the upload API and the F03 generator)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from chatledger_core.domain._shared.errors import DomainError
from chatledger_core.domain.intake.archive import ArchiveLimits, inspect_entries
from chatledger_core.domain.intake.collection import Collection, CollectionSource, NewCollection
from chatledger_core.domain.intake.errors import (
    CollectionDuplicateError,
    CollectionLimitReachedError,
    MatterNotFoundError,
)
from chatledger_core.domain.intake.ports import (
    ArchiveInspector,
    BlobStore,
    UnitOfWorkFactory,
)


class RegisterCollection:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        blob_store: BlobStore,
        inspector: ArchiveInspector,
        limits: ArchiveLimits,
        max_collections_per_matter: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._blobs = blob_store
        self._inspector = inspector
        self._limits = limits
        self._max_collections = max_collections_per_matter

    def execute(
        self,
        matter_id: UUID,
        staged_path: Path,
        original_filename: str,
        source: str = "upload",
        sha256: str | None = None,
    ) -> Collection:
        """Validate and store the staged file; the staged file is always consumed.

        On success it is moved into the blob store; on any failure it is deleted and,
        for domain errors, a ``collection.rejected`` audit event is written.
        """
        digest: str | None = sha256
        size: int | None = None
        try:
            digest, size = self._blobs.inspect_staged(staged_path, sha256)
            metadata = inspect_entries(self._inspector.read_entries(staged_path), self._limits)
            with self._uow_factory() as uow:
                if uow.matters.get_for_update(matter_id) is None:
                    raise MatterNotFoundError
                existing = uow.collections.find_by_sha(matter_id, digest)
                if existing is not None:
                    raise CollectionDuplicateError(
                        existing_collection_id=existing.id,
                        original_filename=existing.original_filename,
                        added_at=existing.added_at,
                        sha256=digest,
                    )
                if uow.collections.count_for_matter(matter_id) >= self._max_collections:
                    raise CollectionLimitReachedError(self._max_collections)
                blob = self._blobs.put_from_staging(staged_path, digest)
                uow.collections.ensure_blob(blob)
                collection = uow.collections.add(
                    NewCollection(
                        matter_id=matter_id,
                        sha256=digest,
                        original_filename=original_filename,
                        size_bytes=blob.size_bytes,
                        source=CollectionSource(source),
                        entry_count=metadata.entry_count,
                        conversation_count=metadata.conversation_count,
                        export_date_from=metadata.export_date_from,
                        export_date_to=metadata.export_date_to,
                        root_prefix=metadata.root_prefix,
                    )
                )
                uow.audit.record(
                    "collection.added",
                    "collection",
                    str(collection.id),
                    {
                        "matter_id": str(matter_id),
                        "sha256": digest,
                        "size_bytes": blob.size_bytes,
                        "original_filename": original_filename,
                        "source": source,
                        "entry_count": metadata.entry_count,
                        "conversation_count": metadata.conversation_count,
                    },
                )
            return collection
        except DomainError as exc:
            self._blobs.discard_staged(staged_path)
            if not isinstance(exc, MatterNotFoundError):
                self._audit_rejection(matter_id, exc, original_filename, source, digest, size)
            raise
        except BaseException:
            self._blobs.discard_staged(staged_path)
            raise

    def _audit_rejection(
        self,
        matter_id: UUID,
        exc: DomainError,
        original_filename: str,
        source: str,
        sha256: str | None,
        size_bytes: int | None,
    ) -> None:
        details: dict[str, Any] = {
            "reason_code": exc.code,
            "message": exc.message,
            "original_filename": original_filename,
            "source": source,
        }
        if "rule" in exc.details:
            details["rule"] = exc.details["rule"]
        if size_bytes is not None:
            details["size_bytes"] = size_bytes
        if sha256 is not None:
            details["sha256"] = sha256
        with self._uow_factory() as uow:
            uow.audit.record("collection.rejected", "matter", str(matter_id), details)
