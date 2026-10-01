"""Worker loop against real PostgreSQL (contract WRK-JOBS-01..06 at process level)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from sqlalchemy import Engine, text

from chatledger_core.domain.jobs.job import JobState
from chatledger_core.infra.heartbeat.pg_heartbeat import PgHeartbeat
from chatledger_core.infra.queue.pg_job_queue import PgJobQueue
from chatledger_worker.handlers import default_registry
from chatledger_worker.heartbeat import HeartbeatThread
from chatledger_worker.loop import JobLoop, LoopConfig
from chatledger_worker.registry import HandlerRegistry
from factories import queue_for


def _loop(
    engine: Engine, worker_id: str = "w-test", queue: PgJobQueue | None = None, **cfg: Any
) -> JobLoop:
    config = LoopConfig(
        lease_renew_seconds=cfg.get("renew", 1),
        sweep_interval_seconds=cfg.get("sweep", 2),
        poll_interval_seconds=cfg.get("poll", 0.05),
    )
    return JobLoop(
        queue or queue_for(engine), default_registry(), worker_id=worker_id, config=config
    )


def _drain(loop: JobLoop, max_iterations: int = 10) -> None:
    for _ in range(max_iterations):
        if not loop.run_once():
            return


def test_noop_job_completes(clean_jobs: Engine) -> None:
    queue = queue_for(clean_jobs)
    job = queue.enqueue("noop")
    assert _loop(clean_jobs).run_once()
    after = queue.get(job.id)
    assert after.state is JobState.DONE
    assert after.attempts == 1
    assert after.finished_at is not None


def test_noop_fail_times_retried_then_done(clean_jobs: Engine) -> None:
    queue = queue_for(clean_jobs)
    job = queue.enqueue("noop", {"fail_times": 1})
    _drain(_loop(clean_jobs))
    after = queue.get(job.id)
    assert after.state is JobState.DONE
    assert after.attempts == 2


def test_noop_exhausts_attempts(clean_jobs: Engine) -> None:
    queue = queue_for(clean_jobs)
    job = queue.enqueue("noop", {"fail_times": 5})
    _drain(_loop(clean_jobs))
    after = queue.get(job.id)
    assert after.state is JobState.FAILED
    assert after.attempts == 3
    assert after.last_error is not None
    assert "NoopFailure" in after.last_error


def test_unknown_kind_fails_job(clean_jobs: Engine) -> None:
    queue = queue_for(clean_jobs)
    job = queue.enqueue("bogus")
    _drain(_loop(clean_jobs))
    after = queue.get(job.id)
    assert after.state is JobState.FAILED
    assert after.last_error is not None
    assert "UNKNOWN_JOB_KIND" in after.last_error


def test_lease_renewed_during_long_job(clean_jobs: Engine) -> None:
    """A job running longer than its lease keeps it through renewals.

    Lease 5 s / renew 0.5 s / sleep 6 s: the margin tolerates wall-clock jumps
    of the DB host (observed on WSL2), which a 2 s lease does not.
    """
    short = queue_for(clean_jobs, lease_seconds=5)
    job = short.enqueue("noop", {"sleep_seconds": 6})
    first = _loop(clean_jobs, "w-1", queue=short, renew=0.5)
    second = _loop(clean_jobs, "w-2", queue=short, sweep=0.1)
    t = threading.Thread(target=first.run_once)
    t.start()
    leased_by = time.monotonic() + 3
    while short.get(job.id).state is not JobState.LEASED and time.monotonic() < leased_by:
        time.sleep(0.02)
    deadline = time.monotonic() + 6.5
    while time.monotonic() < deadline:
        second.run_once()
        time.sleep(0.2)
    t.join(timeout=5)
    after = short.get(job.id)
    assert after.state is JobState.DONE
    assert after.attempts == 1
    assert after.lease_owner == "w-1"


def test_crashed_lease_is_recovered_by_sweep(clean_jobs: Engine) -> None:
    queue = queue_for(clean_jobs)
    job = queue.enqueue("noop")
    assert queue.claim("dead-worker") is not None
    with clean_jobs.begin() as conn:
        conn.execute(
            text("UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = :id"),
            {"id": job.id},
        )
    loop = _loop(clean_jobs, "w-live")
    loop.sweep_if_due(force=True)
    _drain(loop)
    after = queue.get(job.id)
    assert after.state is JobState.DONE
    assert after.attempts == 2
    assert after.lease_owner == "w-live"


def test_graceful_stop_finishes_current_job(clean_jobs: Engine) -> None:
    queue = queue_for(clean_jobs)
    job = queue.enqueue("noop", {"sleep_seconds": 1})
    loop = _loop(clean_jobs)
    t = threading.Thread(target=loop.run)
    t.start()
    deadline = time.monotonic() + 5
    while queue.get(job.id).state is not JobState.LEASED and time.monotonic() < deadline:
        time.sleep(0.02)
    loop.stop()
    later = queue.enqueue("noop")
    t.join(timeout=5)
    assert not t.is_alive()
    assert queue.get(job.id).state is JobState.DONE
    assert queue.get(job.id).attempts == 1
    assert queue.get(later.id).state is JobState.QUEUED


def test_loop_survives_handler_registry_errors(clean_jobs: Engine) -> None:
    registry = HandlerRegistry()
    loop = JobLoop(queue_for(clean_jobs), registry, worker_id="w", config=LoopConfig())
    assert not loop.run_once()
    registry.register("x", lambda job, ctx: None)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("x", lambda job, ctx: None)


def test_heartbeat_upserts(clean_jobs: Engine) -> None:
    hb = HeartbeatThread(
        PgHeartbeat(clean_jobs),
        worker_id="hb-1",
        hostname="h",
        pid=1,
        git_sha="a" * 40,
        interval_seconds=0.2,
    )
    hb.start()

    def last_seen() -> Any:
        with clean_jobs.connect() as conn:
            return conn.execute(
                text("SELECT last_seen_at FROM worker_heartbeat WHERE worker_id = 'hb-1'")
            ).scalar()

    deadline = time.monotonic() + 3
    while last_seen() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    first = last_seen()
    time.sleep(0.5)
    second = last_seen()
    hb.stop(remove=True)
    assert first is not None
    assert second > first
    assert last_seen() is None
