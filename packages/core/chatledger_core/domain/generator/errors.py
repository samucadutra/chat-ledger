"""Typed generator errors, mapped to the HTTP error envelope by the API."""

from __future__ import annotations

from chatledger_core.domain._shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationFailedError,
)

OVERLAP_BASE_INVALID_MESSAGE = "Re-delivery base must be a synthetic collection of this matter."
DUPLICATE_MESSAGE = "Identical synthetic export already in this matter (same seed and parameters)."


class GenerationParamsInvalidError(ValidationFailedError):
    default_code = "GENERATION_PARAMS_INVALID"

    def __init__(self, message: str, field: str) -> None:
        super().__init__(message, details={"field": field})
        self.field = field


class GenerationOverlapBaseInvalidError(ValidationFailedError):
    default_code = "GENERATION_OVERLAP_BASE_INVALID"

    def __init__(self) -> None:
        super().__init__(OVERLAP_BASE_INVALID_MESSAGE)


class GenerationNotFoundError(NotFoundError):
    default_code = "GENERATION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Generation not found.")


class GenerationNotRetryableError(ConflictError):
    default_code = "GENERATION_NOT_RETRYABLE"

    def __init__(self) -> None:
        super().__init__("Only failed generations can be retried.")


class GroundTruthNotFoundError(NotFoundError):
    default_code = "GROUND_TRUTH_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Ground truth not found.")


class InsufficientDiskSpaceError(DomainError):
    default_code = "INSUFFICIENT_DISK_SPACE"
    http_status = 507

    def __init__(self, need_bytes: int, free_bytes: int) -> None:
        super().__init__(
            f"Not enough disk space: need ~{need_bytes / 1e9:.1f} GB, "
            f"{free_bytes / 1e9:.1f} GB free.",
            details={"need_bytes": need_bytes, "free_bytes": free_bytes},
        )
        self.need_bytes = need_bytes
        self.free_bytes = free_bytes
