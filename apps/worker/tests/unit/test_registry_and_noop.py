from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from chatledger_core.domain.jobs.job import Job, JobState
from chatledger_worker.handlers import default_registry
from chatledger_worker.handlers.noop import LeaseLostError, NoopFailure, handle_noop
from chatledger_worker.loop import format_error
from chatledger_worker.registry import JobContext, UnknownJobKindError


def _job(attempts: int, payload: dict[str, Any]) -> Job:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Job(
        id=uuid4(),
        kind="noop",
        state=JobState.LEASED,
        priority=100,
        attempts=attempts,
        max_attempts=3,
        run_after=now,
        created_at=now,
        updated_at=now,
        payload=payload,
    )


def test_registry_has_noop_and_rejects_unknown() -> None:
    registry = default_registry()
    assert registry.kinds() == ["noop"]
    with pytest.raises(UnknownJobKindError, match="UNKNOWN_JOB_KIND"):
        registry.get("bogus")


def test_noop_fails_while_attempts_within_fail_times() -> None:
    ctx = JobContext(worker_id="w")
    with pytest.raises(NoopFailure):
        handle_noop(_job(1, {"fail_times": 1}), ctx)
    handle_noop(_job(2, {"fail_times": 1}), ctx)


def test_noop_aborts_when_lease_lost() -> None:
    ctx = JobContext(worker_id="w", lease_lost=threading.Event())
    ctx.lease_lost.set()
    with pytest.raises(LeaseLostError):
        handle_noop(_job(1, {"sleep_seconds": 5}), ctx)


def test_format_error_includes_type() -> None:
    assert format_error(NoopFailure("x")) == "NoopFailure: x"
