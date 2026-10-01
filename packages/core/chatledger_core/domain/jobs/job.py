"""Job entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class JobState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    DONE = "done"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (JobState.DONE, JobState.FAILED)


MAX_ERROR_LENGTH = 4000


def truncate_error(error: str) -> str:
    return error if len(error) <= MAX_ERROR_LENGTH else error[: MAX_ERROR_LENGTH - 1] + "…"


@dataclass(frozen=True)
class Job:
    id: UUID
    kind: str
    state: JobState
    priority: int
    attempts: int
    max_attempts: int
    run_after: datetime
    created_at: datetime
    updated_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    group_key: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    last_error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_public_dict(self) -> dict[str, Any]:
        """Stable JSON-friendly view (used by the admin CLI)."""
        return {
            "id": str(self.id),
            "kind": self.kind,
            "state": self.state.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
