"""Job queue port (consumed by F03, F04, F11, F12)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from chatledger_core.domain.jobs.job import Job


class JobQueue(Protocol):
    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        priority: int = 100,
        group_key: str | None = None,
        max_attempts: int | None = None,
    ) -> Job:
        """Insert a ``queued`` job runnable now."""
        ...

    def claim(self, worker_id: str) -> Job | None:
        """Lease the next runnable job (priority, then age) or return ``None``."""
        ...

    def renew_lease(self, job_id: UUID, worker_id: str) -> bool:
        """Extend the lease; ``False`` when the lease was lost (handler must abort)."""
        ...

    def complete(self, job_id: UUID, worker_id: str) -> bool:
        """Mark ``done``; ``False`` (no-op) when the lease was lost."""
        ...

    def fail(self, job_id: UUID, worker_id: str, error: str, *, retry: bool = True) -> bool:
        """Record a failure: requeue with backoff or mark ``failed`` when exhausted.

        ``retry=False`` marks the job ``failed`` immediately (permanent errors such
        as an unknown job kind). Returns ``False`` (no-op) when the lease was lost.
        """
        ...

    def requeue_expired(self) -> int:
        """Apply the retry/fail rule to every expired lease; return the count."""
        ...

    def get(self, job_id: UUID) -> Job:
        """Return the job or raise ``NotFoundError``."""
        ...
