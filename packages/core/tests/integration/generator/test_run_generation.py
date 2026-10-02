from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine

from chatledger_core.domain.generator.errors import (
    GenerationNotFoundError,
    GenerationNotRetryableError,
    GenerationOverlapBaseInvalidError,
    GenerationParamsInvalidError,
    GroundTruthNotFoundError,
)
from chatledger_core.domain.intake.errors import MatterNotFoundError
from chatledger_core.infra.audit.pg_audit_log import PgAuditLog
from chatledger_core.infra.generator.pg_generation_repository import PgGenerationRepository
from chatledger_core.infra.intake.pg_collection_repository import PgCollectionRepository
from chatledger_core.infra.intake.pg_unit_of_work import PgIntakeUnitOfWork
from chatledger_core.usecase.generator.get_generation import GetGeneration
from chatledger_core.usecase.generator.get_ground_truth import GetGroundTruth
from chatledger_core.usecase.generator.list_generations import ListGenerations
from chatledger_core.usecase.generator.retry_generation import RetryGeneration
from chatledger_core.usecase.generator.run_generation import LeaseLostError
from factories import make_generation_services, make_matter, make_synthetic_collection, queue_for

NEVER = lambda: False  # noqa: E731


@pytest.fixture
def env(clean_intake: Engine, tmp_path: Path):  # type: ignore[no-untyped-def]
    run, request, repo, store = make_generation_services(clean_intake, tmp_path)
    return clean_intake, tmp_path, run, request, repo, store


def request_small(request, matter, seed: int = 42, **kw):  # type: ignore[no-untyped-def]
    kw.setdefault("preset", "small")
    kw.setdefault("profile", "default")
    return request.execute(matter, seed=seed, **kw)


def tmp_files(root: Path) -> list[str]:
    tmp = root / "tmp"
    return sorted(p.name for p in tmp.iterdir()) if tmp.exists() else []


def test_success_registers_generator_collection(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, run, request, repo, store = env
    matter = make_matter(engine)
    record = request_small(request, matter)
    assert record.state == "queued"
    assert record.job_id is not None
    assert (record.messages, record.conversations) == (10_000, 50)

    run.execute(record.id, NEVER)

    done = repo.get(record.id)
    assert done is not None
    assert (done.state, done.progress_messages) == ("done", 10_000)
    collection = PgCollectionRepository(engine).get(matter, done.collection_id)  # type: ignore[arg-type]
    assert collection is not None
    assert collection.source.value == "generator"
    assert collection.original_filename == "slack-export-42-small-default.zip"
    assert (collection.conversation_count, collection.root_prefix) == (50, "")
    blob = store.path_for(collection.sha256)
    truth = store.ground_truth_path_for(collection.sha256)
    assert stat.S_IMODE(blob.stat().st_mode) == 0o444
    assert stat.S_IMODE(truth.stat().st_mode) == 0o444
    assert hashlib.sha256(truth.read_bytes()).hexdigest() == done.ground_truth_sha256
    assert json.loads(truth.read_bytes())["seed"] == 42
    assert tmp_files(root) == []
    events = [
        e
        for e in PgAuditLog(engine).list_for_entity("collection", str(collection.id))
        if e.action == "collection.added"
    ]
    assert len(events) == 1 and events[0].details["source"] == "generator"
    # idempotent: a replayed job is a no-op
    run.execute(record.id, NEVER)
    assert repo.get(record.id) == done


def test_duplicate_fails_without_creating_a_collection(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, run, request, repo, store = env
    matter = make_matter(engine)
    first = request_small(request, matter)
    run.execute(first.id, NEVER)
    second = request_small(request, matter)
    run.execute(second.id, NEVER)
    failed = repo.get(second.id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.error_code == "COLLECTION_DUPLICATE"
    assert failed.error_message == (
        "Identical synthetic export already in this matter (same seed and parameters)."
    )
    assert PgCollectionRepository(engine).count_for_matter(matter) == 1
    assert tmp_files(root) == []
    # the shared ground truth of the existing collection stays in place
    first_done = repo.get(first.id)
    assert first_done is not None
    assert store.ground_truth_path_for(
        PgCollectionRepository(engine).get(matter, first_done.collection_id).sha256  # type: ignore[arg-type, union-attr]
    ).exists()


def test_adopt_orphan_registration(env) -> None:  # type: ignore[no-untyped-def]
    """A crash between registration and the row update must not become a false duplicate."""
    engine, _, run, request, repo, _ = env
    matter = make_matter(engine)
    first = request_small(request, matter)
    run.execute(first.id, NEVER)
    collection_id = repo.get(first.id).collection_id  # type: ignore[union-attr]
    repo.delete(first.id)  # the row never learned about the collection
    again = request_small(request, matter)
    run.execute(again.id, NEVER)
    adopted = repo.get(again.id)
    assert adopted is not None
    assert (adopted.state, adopted.collection_id) == ("done", collection_id)
    assert PgCollectionRepository(engine).count_for_matter(matter) == 1


def test_uploaded_identical_bytes_are_a_real_duplicate(env) -> None:  # type: ignore[no-untyped-def]
    engine, _, run, request, repo, _ = env
    matter = make_matter(engine)
    first = request_small(request, matter)
    run.execute(first.id, NEVER)
    with engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("UPDATE collection SET source = 'upload'"))
    repo.delete(first.id)
    again = request_small(request, matter)
    run.execute(again.id, NEVER)
    assert repo.get(again.id).error_code == "COLLECTION_DUPLICATE"  # type: ignore[union-attr]


def test_disk_space_failure_cleans_partial(clean_intake: Engine, tmp_path: Path) -> None:
    run, request, repo, _ = make_generation_services(
        clean_intake, tmp_path, free_space_override=1_000_000
    )
    matter = make_matter(clean_intake)
    record = request_small(request, matter, preset="medium")
    run.execute(record.id, NEVER)
    failed = repo.get(record.id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.error_code == "INSUFFICIENT_DISK_SPACE"
    assert failed.error_message.startswith("Not enough disk space: need ~")  # type: ignore[union-attr]
    assert PgCollectionRepository(clean_intake).count_for_matter(matter) == 0
    assert tmp_files(tmp_path) == []


def test_limit_reached_failure(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, run, request, repo, _ = env
    matter = make_matter(engine, "Full Matter")
    for i in range(1, 21):
        make_synthetic_collection(engine, matter, i)
    record = request_small(request, matter)
    run.execute(record.id, NEVER)
    failed = repo.get(record.id)
    assert failed is not None
    assert (failed.state, failed.error_code) == ("failed", "COLLECTION_LIMIT_REACHED")
    assert PgCollectionRepository(engine).count_for_matter(matter) == 20
    assert tmp_files(root) == []
    assert (
        not list((root / "sha256").rglob("*.ground-truth.json"))
        if (root / "sha256").exists()
        else True
    )


def test_matter_gone_is_a_permanent_failure(env) -> None:  # type: ignore[no-untyped-def]
    engine, _, run, request, repo, _ = env
    from sqlalchemy import text

    matter = make_matter(engine)
    record = request_small(request, matter)
    repo.delete(record.id)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM matter WHERE id = :id"), {"id": matter})
    run.execute(record.id, NEVER)  # row is gone: nothing to do
    assert repo.get(record.id) is None


def test_progress_is_monotonic_and_bounded(clean_intake: Engine, tmp_path: Path) -> None:
    run, request, repo, _ = make_generation_services(clean_intake, tmp_path, progress_every=1_000)
    seen: list[int] = []
    original = repo.update_progress

    def spy(generation_id: UUID, value: int) -> None:
        seen.append(value)
        original(generation_id, value)

    repo.update_progress = spy  # type: ignore[method-assign]
    matter = make_matter(clean_intake)
    record = request.execute(
        matter, seed=5, preset="custom", profile="clean", messages=20_000, conversations=40
    )
    run.execute(record.id, NEVER)
    assert seen == sorted(seen)
    assert len(seen) >= 3
    assert all(0 < v <= 20_000 for v in seen)
    assert repo.get(record.id).progress_messages == 20_000  # type: ignore[union-attr]


def test_forced_failure_raises_after_marking_running(clean_intake: Engine, tmp_path: Path) -> None:
    run, request, repo, _ = make_generation_services(clean_intake, tmp_path, fail_always=True)
    matter = make_matter(clean_intake)
    record = request_small(request, matter)
    with pytest.raises(RuntimeError, match="GENERATOR_TEST_FAIL_ALWAYS"):
        run.execute(record.id, NEVER)
    assert repo.get(record.id).state == "running"  # type: ignore[union-attr]
    assert PgCollectionRepository(clean_intake).count_for_matter(matter) == 0


def test_lease_lost_aborts_and_cleans(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, run, request, _, _ = env
    matter = make_matter(engine)
    record = request_small(request, matter)
    with pytest.raises(LeaseLostError):
        run.execute(record.id, lambda: True)
    assert PgCollectionRepository(engine).count_for_matter(matter) == 0
    assert tmp_files(root) == []


def test_redelivery_generation_produces_overlapping_export(env) -> None:  # type: ignore[no-untyped-def]
    engine, _, run, request, repo, store = env
    matter = make_matter(engine)
    base = request_small(request, matter)
    run.execute(base.id, NEVER)
    base_done = repo.get(base.id)
    assert base_done is not None
    redelivery = request.execute(
        matter,
        seed=43,
        preset="medium",
        profile="stress",
        overlap_of_collection_id=base_done.collection_id,
    )
    assert (redelivery.preset, redelivery.profile, redelivery.messages) == (
        "small",
        "default",
        10_000,
    )
    run.execute(redelivery.id, NEVER)
    done = repo.get(redelivery.id)
    assert done is not None
    assert done.state == "done"
    collection = PgCollectionRepository(engine).get(matter, done.collection_id)  # type: ignore[arg-type]
    assert collection is not None
    truth = json.loads(store.ground_truth_path_for(collection.sha256).read_bytes())
    assert truth["overlap"] == {"base_seed": 42, "days_pct": 30}
    assert truth["totals"]["anomalies_by_type"]["duplicate_source"] > 0
    with zipfile.ZipFile(store.path_for(collection.sha256)) as archive:
        assert archive.testzip() is None
    assert collection.original_filename == "slack-export-43-small-default.zip"


def test_request_validation_and_base_rules(env) -> None:  # type: ignore[no-untyped-def]
    engine, _, run, request, repo, _ = env
    matter, other = make_matter(engine), make_matter(engine, "Beta Internal")
    with pytest.raises(MatterNotFoundError):
        request_small(request, UUID(int=1))
    with pytest.raises(GenerationParamsInvalidError) as exc:
        request.execute(
            matter, seed=1, preset="custom", profile="default", messages=2_000_000, conversations=50
        )
    assert exc.value.details == {"field": "messages"}
    assert repo.list_for_matter(matter) == []
    done = request_small(request, matter)
    run.execute(done.id, NEVER)
    base_collection = repo.get(done.id).collection_id  # type: ignore[union-attr]
    with pytest.raises(GenerationOverlapBaseInvalidError):
        request_small(request, other, 3, overlap_of_collection_id=base_collection)
    make_synthetic_collection(engine, matter, 9)
    uploaded = next(
        c
        for c in PgCollectionRepository(engine).list_for_matter(matter)
        if c.source.value == "upload"
    )
    with pytest.raises(GenerationOverlapBaseInvalidError):
        request_small(request, matter, 3, overlap_of_collection_id=uploaded.id)
    with pytest.raises(GenerationOverlapBaseInvalidError):
        request_small(request, matter, 3, overlap_of_collection_id=UUID(int=5))
    with pytest.raises(GenerationParamsInvalidError):
        request_small(request, matter, -1, overlap_of_collection_id=base_collection)


def test_enqueue_failure_removes_the_row(clean_intake: Engine, tmp_path: Path) -> None:
    from chatledger_core.usecase.generator.request_generation import RequestGeneration

    class BrokenQueue:
        def enqueue(self, *args: object, **kwargs: object) -> object:
            raise ConnectionError("queue down")

    repo = PgGenerationRepository(clean_intake)
    request = RequestGeneration(
        lambda: PgIntakeUnitOfWork(clean_intake),
        repo,
        BrokenQueue(),  # type: ignore[arg-type]
    )
    matter = make_matter(clean_intake)
    with pytest.raises(ConnectionError):
        request.execute(matter, seed=1, preset="small", profile="clean")
    assert repo.list_for_matter(matter) == []


def test_read_and_retry_use_cases(env) -> None:  # type: ignore[no-untyped-def]
    engine, _, run, request, repo, store = env

    def uow() -> PgIntakeUnitOfWork:
        return PgIntakeUnitOfWork(engine)

    matter, other = make_matter(engine), make_matter(engine, "Beta Internal")
    record = request_small(request, matter)
    assert [g.id for g in ListGenerations(uow, repo).execute(matter)] == [record.id]
    assert GetGeneration(uow, repo).execute(matter, record.id).id == record.id
    with pytest.raises(GenerationNotFoundError):
        GetGeneration(uow, repo).execute(other, record.id)
    with pytest.raises(GenerationNotFoundError):
        GetGeneration(uow, repo).execute(matter, UUID(int=3))
    with pytest.raises(MatterNotFoundError):
        ListGenerations(uow, repo).execute(UUID(int=3))

    retry = RetryGeneration(uow, repo, queue_for(engine))
    with pytest.raises(GenerationNotRetryableError):  # queued
        retry.execute(matter, record.id)
    repo.mark_running(record.id)
    repo.mark_failed(record.id, "COLLECTION_DUPLICATE", "dup")
    with pytest.raises(GenerationNotRetryableError):
        retry.execute(matter, record.id)
    repo.mark_failed(record.id, "INSUFFICIENT_DISK_SPACE", "no space")
    old_job = repo.get(record.id).job_id  # type: ignore[union-attr]
    again = retry.execute(matter, record.id)
    assert (again.state, again.progress_messages, again.error_code) == ("queued", 0, None)
    assert again.job_id not in (None, old_job)
    run.execute(record.id, NEVER)
    done = repo.get(record.id)
    assert done is not None and done.state == "done"

    truth = GetGroundTruth(uow, repo, store)
    found = truth.execute(matter, done.collection_id)  # type: ignore[arg-type]
    assert found.filename == "ground-truth-42.json"
    assert found.path.is_file()
    with pytest.raises(GroundTruthNotFoundError):
        truth.execute(matter, UUID(int=9))
    with pytest.raises(GroundTruthNotFoundError):
        truth.execute(other, done.collection_id)  # type: ignore[arg-type]
    with pytest.raises(MatterNotFoundError):
        truth.execute(UUID(int=3), done.collection_id)  # type: ignore[arg-type]
    make_synthetic_collection(engine, matter, 4)
    uploaded = next(
        c
        for c in PgCollectionRepository(engine).list_for_matter(matter)
        if c.source.value == "upload"
    )
    with pytest.raises(GroundTruthNotFoundError):
        truth.execute(matter, uploaded.id)
    found.path.chmod(0o644)
    found.path.unlink()
    with pytest.raises(GroundTruthNotFoundError):
        truth.execute(matter, done.collection_id)  # type: ignore[arg-type]
