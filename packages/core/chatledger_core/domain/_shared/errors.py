"""Domain error hierarchy, mapped to the HTTP error envelope by the API."""

from __future__ import annotations

from typing import Any, ClassVar


class DomainError(Exception):
    """Base class for every expected, user-facing failure.

    Subclasses set ``default_code`` and ``http_status``; instances may override
    the code (e.g. ``MATTER_NAME_TAKEN``) while keeping the status.
    """

    default_code: ClassVar[str] = "DOMAIN_ERROR"
    http_status: ClassVar[int] = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.message = message
        self.details: dict[str, Any] = details or {}


class NotFoundError(DomainError):
    default_code = "NOT_FOUND"
    http_status = 404


class ConflictError(DomainError):
    default_code = "CONFLICT"
    http_status = 409


class ValidationFailedError(DomainError):
    default_code = "VALIDATION_ERROR"
    http_status = 422


class UnavailableError(DomainError):
    default_code = "SERVICE_UNAVAILABLE"
    http_status = 503
