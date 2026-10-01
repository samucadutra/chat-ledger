"""PgJobQueue against real PostgreSQL 16 (contract SVC-QUEUE-01..04)."""

from __future__ import annotations

import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, text

from chatledger_core.domain._shared.errors import NotFoundError
from chatledger_core.domain.jobs.job import Job, JobState
from chatledger_core.infra.queue.pg_job_queue import PgJobQueue
from factories import make_job, queue_for


@pytest.fixture
def queue(db_conn: Connection) -> PgJobQueue:
    """Queue bound to the rolled-back test transaction."""
    return queue_for(db_conn.engine).within(db_conn)


def _db_now(conn: Connection) -> datetime:
    value: datetime = conn.execute(text("SELECT now()")).scalar_one()
    return value


def test_enqueue_creates_queued_job(queue: PgJobQueue, db_conn: Connection) -> None:
    job = queue.enqueue("noop", {"a": 1}, group_key="run:1")
    assert job.state is JobState.QUEUED
    assert job.attempts == 0
    assert job.max_attempts == 3
    assert job.payload == {"a": 1}
    assert job.group_key == "run:1"
    assert job.run_after <= _db_now(db_conn)


def test_enqueue_custom_max_attempts(queue: PgJobQueue) -> None:
    assert queue.enqueue("noop", max_attempts=7).max_attempts == 7


def test_claim_orders_by_priority_then_created_at(queue: PgJobQueue) -> None:
    j1 = queue.enqueue("noop", priority=100)
    j2 = queue.enqueue("noop", priority=10)
    j3 = queue.enqueue("noop", priority=100)
    claimed = [queue.claim("w-a") for _ in range(3)]
    assert [c.id if c else None for c in claimed] == [j2.id, j1.id, j3.id]
    assert queue.claim("w-a") is None


def test_claim_sets_lease(queue: PgJobQueue) -> None:
    queue.enqueue("noop")
    job = queue.claim("w-a")
    assert job is not None
    assert job.state is JobState.LEASED
    assert job.attempts == 1
    assert job.lease_owner == "w-a"
    assert job.lease_expires_at is not None
    assert job.started_at is not None


def test_claim_skips_future_run_after(queue: PgJobQueue, db_conn: Connection) -> None:
    make_job(db_conn, run_after=_db_now(db_conn) + timedelta(seconds=10))
    assert queue.claim("w-a") is None


def test_renew_lease_only_by_owner(queue: PgJobQueue, db_conn: Connection) -> None:
    queue.enqueue("noop")
    job = queue.claim("w-a")
    assert job is not None
    assert not queue.renew_lease(job.id, "w-b")
    assert queue.get(job.id).lease_expires_at == job.lease_expires_at
    assert queue.renew_lease(job.id, "w-a")


def test_fail_requeues_with_backoff(db_conn: Connection) -> None:
    queue = queue_for(db_conn.engine, retry_backoff_seconds=5).within(db_conn)
    queue.enqueue("noop")
    job = queue.claim("w-a")
    assert job is not None
    assert queue.fail(job.id, "w-a", "boom")
    after = queue.get(job.id)
    assert after.state is JobState.QUEUED
    assert after.last_error == "boom"
    assert after.lease_expires_at is None
    delta = (after.run_after - _db_now(db_conn)).total_seconds()
    assert 4.5 <= delta <= 5.5


def test_fail_final_attempt_marks_failed(queue: PgJobQueue, db_conn: Connection) -> None:
    job = make_job(
        db_conn,
        state=JobState.LEASED,
        attempts=3,
        lease_owner="w-a",
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )
    assert queue.fail(job.id, "w-a", "boom")
    after = queue.get(job.id)
    assert after.state is JobState.FAILED
    assert after.finished_at is not None


def test_fail_by_non_owner_is_noop(queue: PgJobQueue) -> None:
    queue.enqueue("noop")
    job = queue.claim("w-a")
    assert job is not None
    assert not queue.fail(job.id, "w-b", "boom")
    assert queue.get(job.id).state is JobState.LEASED


def test_fail_truncates_long_error(queue: PgJobQueue) -> None:
    queue.enqueue("noop")
    job = queue.claim("w-a")
    assert job is not None
    queue.fail(job.id, "w-a", "x" * 9000)
    last_error = queue.get(job.id).last_error
    assert last_error is not None
    assert len(last_error) == 4000


def test_svc_queue_03_retries_then_terminally_fails(queue: PgJobQueue) -> None:
    queue.enqueue("noop")
    for attempt in (1, 2, 3):
        job = queue.claim("w-a")
        assert job is not None
        assert job.attempts == attempt
        assert queue.fail(job.id, "w-a", "boom")
        after = queue.get(job.id)
        assert after.last_error == "boom"
        if attempt < 3:
            assert after.state is JobState.QUEUED
            assert after.finished_at is None
        else:
            assert after.state is JobState.FAILED
            assert after.attempts == 3
            assert after.finished_at is not None


def test_requeue_expired_leases(queue: PgJobQueue, db_conn: Connection) -> None:
    queue.enqueue("noop")
    job = queue.claim("w-a")
    assert job is not None
    db_conn.execute(
        text("UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = :id"),
        {"id": job.id},
    )
    assert queue.requeue_expired() == 1
    after = queue.get(job.id)
    assert after.state is JobState.QUEUED
    assert after.last_error == "lease expired (owner w-a)"
    again = queue.claim("w-b")
    assert again is not None
    assert again.id == job.id
    assert again.attempts == 2
    assert again.lease_owner == "w-b"


def test_requeue_expired_exhausted_marks_failed(queue: PgJobQueue, db_conn: Connection) -> None:
    job = make_job(
        db_conn,
        state=JobState.LEASED,
        attempts=3,
        lease_owner="w-a",
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    assert queue.requeue_expired() == 1
    after = queue.get(job.id)
    assert after.state is JobState.FAILED
    assert after.finished_at is not None


def test_requeue_ignores_live_leases(queue: PgJobQueue) -> None:
    queue.enqueue("noop")
    assert queue.claim("w-a") is not None
    assert queue.requeue_expired() == 0


def test_complete(queue: PgJobQueue) -> None:
    queue.enqueue("noop")
    job = queue.claim("w-a")
    assert job is not None
    assert queue.complete(job.id, "w-a")
    after = queue.get(job.id)
    assert after.state is JobState.DONE
    assert after.finished_at is not None
    assert after.lease_owner == "w-a"
    assert after.lease_expires_at is None


def test_complete_after_lost_lease_is_noop(queue: PgJobQueue, db_conn: Connection) -> None:
    queue.enqueue("noop")
    job = queue.claim("w-a")
    assert job is not None
    db_conn.execute(
        text("UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = :id"),
        {"id": job.id},
    )
    queue.requeue_expired()
    taken = queue.claim("w-b")
    assert taken is not None
    assert not queue.complete(job.id, "w-a")
    assert queue.get(job.id).state is JobState.LEASED
    assert queue.get(job.id).lease_owner == "w-b"


def test_get_unknown_raises(queue: PgJobQueue) -> None:
    with pytest.raises(NotFoundError):
        queue.get(uuid4())


# ----------------------------------------------------------------- committed-data tests
def test_concurrent_claim_exactly_one_winner(clean_jobs: Engine) -> None:
    """SVC-QUEUE-01: two connections claim one job at the same instant."""
    queue = queue_for(clean_jobs)
    enqueued = queue.enqueue("noop")
    barrier = threading.Barrier(2)
    results: dict[str, Job | None] = {}

    def worker(worker_id: str) -> None:
        q = queue_for(clean_jobs)
        barrier.wait()
        results[worker_id] = q.claim(worker_id)

    threads = [threading.Thread(target=worker, args=(w,)) for w in ("w-a", "w-b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    winners = {w: j for w, j in results.items() if j is not None}
    assert len(results) == 2
    assert len(winners) == 1
    winner_id, claimed = next(iter(winners.items()))
    assert claimed.id == enqueued.id
    row = queue.get(enqueued.id)
    assert row.state is JobState.LEASED
    assert row.attempts == 1
    assert row.lease_owner == winner_id


def test_concurrent_claim_many_jobs_no_duplicates(clean_jobs: Engine) -> None:
    queue = queue_for(clean_jobs)
    ids = {queue.enqueue("noop").id for _ in range(50)}
    claimed: list[Job] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker(n: int) -> None:
        q = queue_for(clean_jobs)
        barrier.wait()
        while (job := q.claim(f"w-{n}")) is not None:
            with lock:
                claimed.append(job)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    counts = Counter(j.id for j in claimed)
    assert set(counts) == ids
    assert all(c == 1 for c in counts.values())
