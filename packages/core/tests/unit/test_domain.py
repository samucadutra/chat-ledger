from datetime import UTC, datetime
from uuid import uuid4

from chatledger_core.domain._shared.clock import FixedClock, SystemClock
from chatledger_core.domain._shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    UnavailableError,
    ValidationFailedError,
)
from chatledger_core.domain.jobs.job import MAX_ERROR_LENGTH, Job, JobState, truncate_error


def test_error_codes_and_statuses() -> None:
    assert (NotFoundError("x").code, NotFoundError.http_status) == ("NOT_FOUND", 404)
    assert (ConflictError("x").code, ConflictError.http_status) == ("CONFLICT", 409)
    assert ValidationFailedError("x").code == "VALIDATION_ERROR"
    assert UnavailableError("x").http_status == 503
    err = ConflictError("taken", code="NAME_TAKEN", details={"name": "a"})
    assert isinstance(err, DomainError)
    assert (err.code, err.message, err.details) == ("NAME_TAKEN", "taken", {"name": "a"})
    assert DomainError("x").details == {}


def test_clocks() -> None:
    assert SystemClock().now().tzinfo is UTC
    at = datetime(2026, 1, 1, tzinfo=UTC)
    clock = FixedClock(at)
    clock.advance(60)
    assert clock.now() == datetime(2026, 1, 1, 0, 1, tzinfo=UTC)


def test_job_state_terminal() -> None:
    assert JobState.DONE.is_terminal
    assert JobState.FAILED.is_terminal
    assert not JobState.QUEUED.is_terminal


def test_truncate_error() -> None:
    assert truncate_error("boom") == "boom"
    assert len(truncate_error("x" * 10_000)) == MAX_ERROR_LENGTH


def test_job_public_dict() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    job = Job(
        id=uuid4(),
        kind="noop",
        state=JobState.DONE,
        priority=100,
        attempts=1,
        max_attempts=3,
        run_after=now,
        created_at=now,
        updated_at=now,
        finished_at=now,
    )
    data = job.to_public_dict()
    assert data["state"] == "done"
    assert data["finished_at"] == now.isoformat()
    assert set(data) == {
        "id",
        "kind",
        "state",
        "attempts",
        "max_attempts",
        "last_error",
        "created_at",
        "finished_at",
    }
