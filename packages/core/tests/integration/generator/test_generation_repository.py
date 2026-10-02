from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Engine, text

from chatledger_core.domain.generator.ports import NewGeneration
from chatledger_core.domain.jobs.job import JobState
from chatledger_core.infra.generator.pg_generation_repository import PgGenerationRepository
from factories import make_job, make_matter


@pytest.fixture
def repo(clean_intake: Engine) -> PgGenerationRepository:
    return PgGenerationRepository(clean_intake)


def new(matter_id, seed: int = 42, **overrides):  # type: ignore[no-untyped-def]
    values = {
        "matter_id": matter_id,
        "seed": seed,
        "preset": "small",
        "profile": "default",
        "messages": 10_000,
        "conversations": 50,
        "overlap_of_collection_id": None,
    }
    values.update(overrides)
    return NewGeneration(**values)


def test_add_get_list_newest_first(repo: PgGenerationRepository, clean_intake: Engine) -> None:
    matter = make_matter(clean_intake)
    first = repo.add(new(matter, 1))
    second = repo.add(new(matter, 2))
    assert first.state == "queued"
    assert (first.progress_messages, first.error_code, first.collection_id) == (0, None, None)
    assert first.overlap_days_pct == 30
    assert repo.get(first.id) == first
    assert [g.id for g in repo.list_for_matter(matter)] == [second.id, first.id]
    assert repo.list_for_matter(uuid4()) == []
    assert repo.get(uuid4()) is None


def test_progress_is_monotonic_and_only_while_running(
    repo: PgGenerationRepository, clean_intake: Engine
) -> None:
    record = repo.add(new(make_matter(clean_intake)))
    repo.update_progress(record.id, 5_000)  # still queued: ignored
    assert repo.get(record.id).progress_messages == 0  # type: ignore[union-attr]
    repo.mark_running(record.id)
    repo.update_progress(record.id, 5_000)
    repo.update_progress(record.id, 3_000)
    running = repo.get(record.id)
    assert running is not None
    assert (running.state, running.progress_messages) == ("running", 5_000)


def test_failed_job_makes_the_generation_failed(
    repo: PgGenerationRepository, clean_intake: Engine
) -> None:
    record = repo.add(new(make_matter(clean_intake)))
    with clean_intake.begin() as conn:
        job = make_job(
            conn,
            kind="generate",
            state=JobState.FAILED,
            attempts=3,
            payload={"generation_id": str(record.id)},
        )
        conn.execute(
            text("UPDATE job SET last_error = 'RuntimeError: boom' WHERE id = :id"), {"id": job.id}
        )
    repo.attach_job(record.id, job.id)
    repo.mark_running(record.id)
    failed = repo.get(record.id)
    assert failed is not None
    assert (failed.state, failed.error_code) == ("failed", "GENERATION_FAILED")
    assert failed.error_message == "RuntimeError: boom"
    assert failed.job_attempts == 3
    with clean_intake.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE id = :id"), {"id": job.id})
    assert repo.get(record.id).job_id is None  # type: ignore[union-attr]


def test_mark_failed_and_reset_for_retry(
    repo: PgGenerationRepository, clean_intake: Engine
) -> None:
    record = repo.add(new(make_matter(clean_intake)))
    repo.mark_running(record.id)
    repo.mark_failed(record.id, "INSUFFICIENT_DISK_SPACE", "Not enough disk space: ...")
    failed = repo.get(record.id)
    assert failed is not None
    assert (failed.state, failed.error_code) == ("failed", "INSUFFICIENT_DISK_SPACE")
    with clean_intake.begin() as conn:
        job = make_job(conn, kind="generate")
    reset = repo.reset_for_retry(record.id, job.id)
    assert (reset.state, reset.progress_messages, reset.error_code) == ("queued", 0, None)
    assert reset.job_id == job.id


def test_done_requires_collection_and_links_it(
    repo: PgGenerationRepository, clean_intake: Engine
) -> None:
    from factories import make_synthetic_collection

    matter = make_matter(clean_intake)
    make_synthetic_collection(clean_intake, matter, 1)
    with clean_intake.connect() as conn:
        collection_id = conn.execute(text("SELECT id FROM collection")).scalar_one()
    record = repo.add(new(matter, 7))
    with (
        pytest.raises(Exception, match="ck_generation_done_collection"),
        clean_intake.begin() as conn,
    ):
        conn.execute(text("UPDATE generation SET state = 'done' WHERE id = :id"), {"id": record.id})
    repo.mark_done(
        record.id,
        collection_id=collection_id,
        ground_truth_sha256="a" * 64,
        progress_messages=10_000,
    )
    done = repo.get(record.id)
    assert done is not None
    assert (done.state, done.collection_id) == ("done", collection_id)
    assert repo.find_by_collection(collection_id) == done
    assert repo.find_seed_for_collection(matter, collection_id) == 7
    assert repo.find_seed_for_collection(uuid4(), collection_id) is None
    assert repo.find_by_collection(uuid4()) is None
    repo.delete(record.id)
    assert repo.get(record.id) is None


def test_check_constraints_reject_bad_values(clean_intake: Engine) -> None:
    matter = make_matter(clean_intake)
    repo = PgGenerationRepository(clean_intake)
    for bad in (
        {"seed": 2_147_483_648},
        {"messages": 999},
        {"conversations": 5_001},
        {"preset": "huge"},
        {"profile": "wild"},
    ):
        with pytest.raises(Exception, match="ck_generation"):
            repo.add(new(matter, **bad))
