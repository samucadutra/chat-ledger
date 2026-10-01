"""Test factories shared by every Python test package (project convention, spec A6).

DB state for tests comes from these builders plus the fixtures in the root
``conftest.py`` — there are no SQL seed files.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, text

from chatledger_core.domain.audit.audit_event import AuditEvent
from chatledger_core.domain.jobs.job import Job, JobState
from chatledger_core.infra.audit.pg_audit_log import PgAuditLog
from chatledger_core.infra.queue.pg_job_queue import PgJobQueue, row_to_job

# Contract handle ``audit-seed``.
AUDIT_SEED: dict[str, Any] = {
    "action": "test.seeded",
    "entity_type": "test",
    "entity_id": "seed-1",
    "details": {"note": "seed"},
}


def make_audit_event(conn: Connection, **overrides: Any) -> AuditEvent:
    """Insert an audit event (defaults to the ``audit-seed`` handle)."""
    fields = {**AUDIT_SEED, **overrides}
    engine: Engine = conn.engine
    return PgAuditLog(engine, conn=conn).record(
        fields["action"], fields["entity_type"], fields["entity_id"], fields["details"]
    )


def make_job(
    conn: Connection,
    *,
    kind: str = "noop",
    payload: dict[str, Any] | None = None,
    state: JobState | str = JobState.QUEUED,
    priority: int = 100,
    attempts: int = 0,
    max_attempts: int = 3,
    lease_owner: str | None = None,
    lease_expires_at: datetime | None = None,
    run_after: datetime | None = None,
    group_key: str | None = None,
) -> Job:
    """Insert a job row with arbitrary state (bypasses the queue's transitions)."""
    state_value = JobState(state).value
    row = (
        conn.execute(
            text(
                """
                INSERT INTO job (kind, payload, state, priority, attempts, max_attempts,
                                 lease_owner, lease_expires_at, run_after, group_key, created_at)
                VALUES (:kind, CAST(:payload AS jsonb), :state, :priority, :attempts,
                        :max_attempts, :lease_owner, :lease_expires_at,
                        COALESCE(:run_after, now()), :group_key, clock_timestamp())
                RETURNING *
                """
            ),
            {
                "kind": kind,
                "payload": json.dumps(payload or {}),
                "state": state_value,
                "priority": priority,
                "attempts": attempts,
                "max_attempts": max_attempts,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "run_after": run_after,
                "group_key": group_key,
            },
        )
        .mappings()
        .one()
    )
    return row_to_job(row)


def queue_for(engine: Engine, **overrides: Any) -> PgJobQueue:
    """Queue configured like ``.env.test`` (lease 5 s, 3 attempts, no backoff)."""
    params: dict[str, Any] = {"lease_seconds": 5, "max_attempts": 3, "retry_backoff_seconds": 0}
    params.update(overrides)
    return PgJobQueue(engine, **params)
