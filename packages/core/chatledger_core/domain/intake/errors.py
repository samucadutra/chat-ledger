"""Typed intake errors, mapped to the HTTP error envelope by the API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from chatledger_core.domain._shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationFailedError,
)

NAME_INVALID_MESSAGE = "Name must be 3\u201380 characters"
DESCRIPTION_INVALID_MESSAGE = "Description must be at most 500 characters"


class MatterNotFoundError(NotFoundError):
    default_code = "MATTER_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Matter not found.")


class CollectionNotFoundError(NotFoundError):
    default_code = "COLLECTION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Collection not found.")


class MatterNameInvalidError(ValidationFailedError):
    default_code = "MATTER_NAME_INVALID"

    def __init__(self) -> None:
        super().__init__(NAME_INVALID_MESSAGE)


class MatterDescriptionInvalidError(ValidationFailedError):
    default_code = "MATTER_DESCRIPTION_INVALID"

    def __init__(self) -> None:
        super().__init__(DESCRIPTION_INVALID_MESSAGE)


class MatterNameTakenError(ConflictError):
    default_code = "MATTER_NAME_TAKEN"

    def __init__(self, existing_matter_id: UUID | None = None) -> None:
        details = {"existing_matter_id": str(existing_matter_id)} if existing_matter_id else {}
        super().__init__("A matter with this name already exists", details=details)


class CollectionDuplicateError(ConflictError):
    default_code = "COLLECTION_DUPLICATE"

    def __init__(
        self,
        *,
        existing_collection_id: UUID,
        original_filename: str,
        added_at: datetime,
        sha256: str,
    ) -> None:
        super().__init__(
            "This export is already in this matter as collection "
            f"{original_filename} (added {added_at:%Y-%m-%d}). SHA-256: {sha256}.",
            details={
                "existing_collection_id": str(existing_collection_id),
                "original_filename": original_filename,
                "added_at": added_at.isoformat(),
                "sha256": sha256,
            },
        )


class CollectionLimitReachedError(ConflictError):
    default_code = "COLLECTION_LIMIT_REACHED"

    def __init__(self, limit: int) -> None:
        super().__init__(
            f"This matter already has {limit} collections (limit {limit}).",
            details={"limit": limit},
        )


class FileTooLargeError(DomainError):
    default_code = "FILE_TOO_LARGE"
    http_status = 413

    def __init__(self, limit_bytes: int, size_bytes: int | None = None) -> None:
        details: dict[str, int] = {"limit_bytes": limit_bytes}
        shown = "over the limit"
        if size_bytes is not None:
            details["size_bytes"] = size_bytes
            shown = f"{size_bytes / 1024**3:.2f} GB"
        super().__init__(f"File exceeds the 2 GB limit ({shown}).", details=details)


class NotASlackExportError(ValidationFailedError):
    default_code = "NOT_A_SLACK_EXPORT"

    def __init__(self) -> None:
        super().__init__("Not a Slack workspace export: users.json and channels.json not found.")


class ArchiveRejectedError(ValidationFailedError):
    default_code = "ARCHIVE_REJECTED"

    def __init__(self, rule: str, rule_text: str) -> None:
        super().__init__(f"Archive rejected: {rule_text}", details={"rule": rule})


class InvalidFilenameError(ValidationFailedError):
    default_code = "INVALID_FILENAME"

    def __init__(self) -> None:
        super().__init__("File must be a .zip archive.")
