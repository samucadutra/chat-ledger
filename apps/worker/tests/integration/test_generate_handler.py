"""The ``generate`` handler through the real job loop and queue (WRK-GENERATE contract items)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from chatledger_core.domain.jobs.job import JobState
from chatledger_core.infra.intake.pg_collection_repository import PgCollectionRepository
from chatledger_worker.handlers import default_registry
from chatledger_worker.handlers.generate import KIND, make_generate_handler
from chatledger_worker.loop import JobLoop, LoopConfig
from chatledger_worker.registry import JobContext
from factories import make_generation_services, make_matter, queue_for


@pytest.fixture
def stack(clean_intake: Engine, clean_jobs: Engine, tmp_path: Path):  # type: ignore[no-untyped-def]
    def build(**run_kwargs: Any):  # type: ignore[no-untyped-def]
        run, request, repo, _ = make_generation_services(clean_intake, tmp_path, **run_kwargs)
        loop = JobLoop(
            queue_for(clean_intake),
            default_registry({KIND: make_generate_handler(run)}),
            worker_id="w-test",
            config=LoopConfig(lease_renew_seconds=1, sweep_interval_seconds=2),
        )
        return loop, request, repo

    return clean_intake, tmp_path, build


def drain(loop: JobLoop, limit: int = 10) -> None:
    for _ in range(limit):
        if not loop.run_once():
            return


def test_success_and_duplicate_use_one_attempt(stack) -> None:  # type: ignore[no-untyped-def]
    engine, root, build = stack
    loop, request, repo = build()
    matter = make_matter(engine)
    first = request.execute(matter, seed=42, preset="small", profile="default")
    drain(loop)
    assert repo.get(first.id).state == "done"  # type: ignore[union-attr]
    second = request.execute(matter, seed=42, preset="small", profile="default")
    drain(loop)
    failed = repo.get(second.id)
    assert failed is not None
    assert (failed.state, failed.error_code) == ("failed", "COLLECTION_DUPLICATE")
    job = queue_for(engine).get(failed.job_id)  # type: ignore[arg-type]
    assert (job.state, job.attempts) == (JobState.DONE, 1)
    assert PgCollectionRepository(engine).count_for_matter(matter) == 1
    assert not [p for p in (root / "tmp").iterdir() if p.name.startswith("gen-")]


def test_disk_failure_completes_the_job_without_retry(stack) -> None:  # type: ignore[no-untyped-def]
    engine, _, build = stack
    loop, request, repo = build(free_space_override=1_000)
    matter = make_matter(engine)
    record = request.execute(matter, seed=42, preset="small", profile="default")
    drain(loop)
    failed = repo.get(record.id)
    assert failed is not None
    assert failed.error_code == "INSUFFICIENT_DISK_SPACE"
    assert queue_for(engine).get(failed.job_id).attempts == 1  # type: ignore[arg-type]


def test_forced_failure_exhausts_attempts_then_retry_succeeds(stack) -> None:  # type: ignore[no-untyped-def]
    from chatledger_core.infra.intake.pg_unit_of_work import PgIntakeUnitOfWork
    from chatledger_core.usecase.generator.retry_generation import RetryGeneration

    engine, _, build = stack
    failing_loop, request, repo = build(fail_always=True)
    matter = make_matter(engine)
    record = request.execute(matter, seed=42, preset="small", profile="default")
    drain(failing_loop)
    failed = repo.get(record.id)
    assert failed is not None
    assert (failed.state, failed.error_code) == ("failed", "GENERATION_FAILED")
    assert "GENERATOR_TEST_FAIL_ALWAYS" in (failed.error_message or "")
    assert failed.job_attempts == 3
    assert PgCollectionRepository(engine).count_for_matter(matter) == 0

    healthy_loop, _, _ = build()
    retried = RetryGeneration(lambda: PgIntakeUnitOfWork(engine), repo, queue_for(engine)).execute(
        matter, record.id
    )
    assert retried.state == "queued"
    drain(healthy_loop)
    done = repo.get(record.id)
    assert done is not None and done.state == "done" and done.collection_id is not None
    assert PgCollectionRepository(engine).count_for_matter(matter) == 1


def test_handler_passes_lease_loss_to_the_run(stack) -> None:  # type: ignore[no-untyped-def]
    engine, root, build = stack
    _, request, repo = build()
    run, _, _, _ = make_generation_services(engine, root)
    matter = make_matter(engine)
    record = request.execute(matter, seed=42, preset="small", profile="default")
    ctx = JobContext(worker_id="w", lease_lost=threading.Event())
    ctx.lease_lost.set()
    job = queue_for(engine).claim("w")
    assert job is not None
    from chatledger_core.usecase.generator.run_generation import LeaseLostError

    with pytest.raises(LeaseLostError):
        make_generate_handler(run)(job, ctx)
    assert PgCollectionRepository(engine).count_for_matter(matter) == 0
    assert repo.get(record.id).state == "running"  # type: ignore[union-attr]
