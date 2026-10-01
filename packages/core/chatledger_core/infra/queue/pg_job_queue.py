"""PostgreSQL job-queue adapter (``FOR UPDATE SKIP LOCKED``).

Semantics (spec §5 "Queue port semantics"):

* ``claim`` leases the next runnable job ordered by ``(priority, created_at)``.
* ``fail`` / ``requeue_expired`` requeue with linear backoff ``backoff * attempts``
  while ``attempts < max_attempts``; otherwise the job becomes ``failed``.
* On any transition out of ``leased`` the lease deadline is cleared, while
  ``lease_owner`` is kept as the *last* owner for observability.
* With ``stale_owner_seconds`` set, ``requeue_expired`` also recovers leases
  held by workers whose heartbeat is older than that window (a crashed worker
  is detected well before its lease deadline).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, RowMapping, text

from chatledger_core.domain._shared.errors import NotFoundError
from chatledger_core.domain.jobs.job import Job, JobState, truncate_error
from chatledger_core.infra.db.tx import TransactionalAdapter

_COLUMNS = (
    "id, kind, payload, state, priority, group_key, attempts, max_attempts, lease_owner, "
    "lease_expires_at, run_after, last_error, created_at, started_at, finished_at, updated_at"
)
_JOB_COLUMNS = ", ".join(f"job.{c.strip()}" for c in _COLUMNS.split(","))


def row_to_job(row: RowMapping | Mapping[str, Any]) -> Job:
    return Job(
        id=row["id"],
        kind=row["kind"],
        payload=dict(row["payload"] or {}),
        state=JobState(row["state"]),
        priority=row["priority"],
        group_key=row["group_key"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        lease_owner=row["lease_owner"],
        lease_expires_at=row["lease_expires_at"],
        run_after=row["run_after"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        updated_at=row["updated_at"],
    )


# Shared retry/fail rule, applied to a row being taken out of ``leased``.
# ``:retry`` false forces a terminal failure regardless of remaining attempts.
_CAN_RETRY = "(:retry AND job.attempts < job.max_attempts)"
_RETRY_SET = f"""
    state = CASE WHEN {_CAN_RETRY} THEN 'queued' ELSE 'failed' END,
    run_after = CASE WHEN {_CAN_RETRY}
        THEN now() + make_interval(secs => :backoff * job.attempts)
        ELSE job.run_after END,
    finished_at = CASE WHEN {_CAN_RETRY} THEN NULL ELSE now() END,
    lease_expires_at = NULL,
    updated_at = now()
"""


class PgJobQueue(TransactionalAdapter):
    def __init__(
        self,
        engine: Engine,
        *,
        lease_seconds: float = 60,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 5,
        stale_owner_seconds: float | None = None,
        conn: Connection | None = None,
    ) -> None:
        super().__init__(engine, conn)
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.stale_owner_seconds = stale_owner_seconds

    def within(self, conn: Connection) -> PgJobQueue:
        """Return a queue bound to the caller's transaction (transactional enqueue)."""
        return PgJobQueue(
            self._engine,
            lease_seconds=self.lease_seconds,
            max_attempts=self.max_attempts,
            retry_backoff_seconds=self.retry_backoff_seconds,
            stale_owner_seconds=self.stale_owner_seconds,
            conn=conn,
        )

    # ------------------------------------------------------------------ port
    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        priority: int = 100,
        group_key: str | None = None,
        max_attempts: int | None = None,
    ) -> Job:
        stmt = text(
            f"""
            INSERT INTO job (kind, payload, priority, group_key, max_attempts,
                             run_after, created_at, updated_at)
            VALUES (:kind, CAST(:payload AS jsonb), :priority, :group_key, :max_attempts,
                    now(), clock_timestamp(), now())
            RETURNING {_COLUMNS}
            """
        )
        with self._tx() as conn:
            row = (
                conn.execute(
                    stmt,
                    {
                        "kind": kind,
                        "payload": json.dumps(payload or {}),
                        "priority": priority,
                        "group_key": group_key,
                        "max_attempts": max_attempts or self.max_attempts,
                    },
                )
                .mappings()
                .one()
            )
        return row_to_job(row)

    def claim(self, worker_id: str) -> Job | None:
        stmt = text(
            f"""
            WITH next AS (
                SELECT id FROM job
                WHERE state = 'queued' AND run_after <= now()
                ORDER BY priority, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE job SET
                state = 'leased',
                lease_owner = :worker_id,
                lease_expires_at = now() + make_interval(secs => :lease),
                attempts = job.attempts + 1,
                started_at = COALESCE(job.started_at, now()),
                updated_at = now()
            FROM next
            WHERE job.id = next.id
            RETURNING {_JOB_COLUMNS}
            """
        )
        with self._tx() as conn:
            row = (
                conn.execute(stmt, {"worker_id": worker_id, "lease": self.lease_seconds})
                .mappings()
                .one_or_none()
            )
        return row_to_job(row) if row is not None else None

    def renew_lease(self, job_id: UUID, worker_id: str) -> bool:
        stmt = text(
            """
            UPDATE job SET lease_expires_at = now() + make_interval(secs => :lease),
                           updated_at = now()
            WHERE id = :id AND state = 'leased' AND lease_owner = :worker_id
            RETURNING id
            """
        )
        with self._tx() as conn:
            row = conn.execute(
                stmt, {"id": job_id, "worker_id": worker_id, "lease": self.lease_seconds}
            ).one_or_none()
        return row is not None

    def complete(self, job_id: UUID, worker_id: str) -> bool:
        stmt = text(
            """
            UPDATE job SET state = 'done', finished_at = now(), lease_expires_at = NULL,
                           updated_at = now()
            WHERE id = :id AND state = 'leased' AND lease_owner = :worker_id
            RETURNING id
            """
        )
        with self._tx() as conn:
            row = conn.execute(stmt, {"id": job_id, "worker_id": worker_id}).one_or_none()
        return row is not None

    def fail(self, job_id: UUID, worker_id: str, error: str, *, retry: bool = True) -> bool:
        stmt = text(
            f"""
            UPDATE job SET last_error = :error, {_RETRY_SET}
            WHERE id = :id AND state = 'leased' AND lease_owner = :worker_id
            RETURNING id
            """
        )
        with self._tx() as conn:
            row = conn.execute(
                stmt,
                {
                    "id": job_id,
                    "worker_id": worker_id,
                    "error": truncate_error(error),
                    "backoff": self.retry_backoff_seconds,
                    "retry": retry,
                },
            ).one_or_none()
        return row is not None

    def requeue_expired(self) -> int:
        params: dict[str, Any] = {"backoff": self.retry_backoff_seconds, "retry": True}
        stale_clause = ""
        if self.stale_owner_seconds is not None:
            stale_clause = """
                    OR lease_owner IN (
                        SELECT worker_id FROM worker_heartbeat
                        WHERE last_seen_at < now() - make_interval(secs => :stale)
                    )"""
            params["stale"] = self.stale_owner_seconds
        stmt = text(
            f"""
            WITH expired AS (
                SELECT id FROM job
                WHERE state = 'leased' AND (lease_expires_at < now(){stale_clause})
                FOR UPDATE SKIP LOCKED
            )
            UPDATE job SET
                last_error = CASE WHEN job.lease_expires_at < now()
                    THEN 'lease expired (owner ' || job.lease_owner || ')'
                    ELSE 'worker heartbeat lost (owner ' || job.lease_owner || ')' END,
                {_RETRY_SET}
            FROM expired
            WHERE job.id = expired.id
            RETURNING job.id
            """
        )
        with self._tx() as conn:
            rows = conn.execute(stmt, params).all()
        return len(rows)

    def get(self, job_id: UUID) -> Job:
        with self._tx() as conn:
            row = (
                conn.execute(text(f"SELECT {_COLUMNS} FROM job WHERE id = :id"), {"id": job_id})
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise NotFoundError(f"Job {job_id} not found", code="JOB_NOT_FOUND")
        return row_to_job(row)
