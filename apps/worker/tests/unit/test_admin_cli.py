from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from chatledger_core.domain._shared.errors import NotFoundError
from chatledger_core.domain.jobs.job import Job, JobState
from chatledger_worker import admin_cli


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: dict[UUID, Job] = {}
        self.enqueued: list[tuple[str, dict[str, Any], int]] = []

    def enqueue(self, kind: str, payload: dict[str, Any] | None = None, **kw: Any) -> Job:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        job = Job(
            id=uuid4(),
            kind=kind,
            state=JobState.QUEUED,
            priority=kw.get("priority", 100),
            attempts=0,
            max_attempts=3,
            run_after=now,
            created_at=now,
            updated_at=now,
            payload=payload or {},
        )
        self.jobs[job.id] = job
        self.enqueued.append((kind, payload or {}, job.priority))
        return job

    def get(self, job_id: UUID) -> Job:
        if job_id not in self.jobs:
            raise NotFoundError(f"Job {job_id} not found")
        return self.jobs[job_id]


def run(argv: list[str], queue: FakeQueue) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = admin_cli.main(
        argv,
        queue_factory=lambda: queue,  # type: ignore[arg-type,return-value]
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def test_enqueue_noop_prints_uuid() -> None:
    q = FakeQueue()
    code, out, _ = run(["enqueue-noop"], q)
    assert code == 0
    UUID(out.strip())
    assert q.enqueued == [("noop", {}, 100)]


def test_enqueue_noop_with_options() -> None:
    q = FakeQueue()
    code, _, _ = run(
        ["enqueue-noop", "--fail-times", "2", "--sleep-seconds", "1.5", "--priority", "5"], q
    )
    assert code == 0
    assert q.enqueued == [("noop", {"fail_times": 2, "sleep_seconds": 1.5}, 5)]


@pytest.mark.parametrize(
    "argv",
    [
        ["enqueue-noop", "--fail-times", "-1"],
        ["enqueue-noop", "--fail-times", "x"],
        ["enqueue-noop", "--sleep-seconds", "301"],
        ["enqueue-noop", "--sleep-seconds", "abc"],
        ["enqueue-noop", "--priority", "1001"],
        ["job-status", "not-a-uuid"],
        [],
    ],
)
def test_invalid_arguments_exit_2_without_enqueue(argv: list[str]) -> None:
    q = FakeQueue()
    with pytest.raises(SystemExit) as info:
        run(argv, q)
    assert info.value.code == 2
    assert q.enqueued == []


def test_job_status_prints_json() -> None:
    q = FakeQueue()
    job = q.enqueue("noop")
    code, out, _ = run(["job-status", str(job.id)], q)
    assert code == 0
    data = json.loads(out)
    assert data["id"] == str(job.id)
    assert data["kind"] == "noop"
    assert data["state"] == "queued"
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


def test_job_status_unknown_exits_1() -> None:
    zero = "00000000-0000-0000-0000-000000000000"
    code, out, err = run(["job-status", zero], FakeQueue())
    assert code == 1
    assert out == ""
    assert f"Job {zero} not found" in err
