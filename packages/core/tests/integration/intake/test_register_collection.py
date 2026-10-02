from __future__ import annotations

import hashlib
import stat
import threading
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from chatledger_core.domain._shared.errors import DomainError
from chatledger_core.domain.audit.audit_event import AuditEvent
from chatledger_core.infra.audit.pg_audit_log import PgAuditLog
from chatledger_core.infra.intake.pg_collection_repository import PgCollectionRepository
from factories import (
    FIXTURES_DIR,
    make_matter,
    make_register,
    make_synthetic_collection,
    stage_fixture,
)

MINIMAL = "minimal-export.zip"


def sha_of(fixture: str) -> str:
    return hashlib.sha256((FIXTURES_DIR / fixture).read_bytes()).hexdigest()


def audit(engine: Engine, entity_type: str, entity_id: UUID, action: str) -> list[AuditEvent]:
    events = PgAuditLog(engine).list_for_entity(entity_type, str(entity_id))
    return [e for e in events if e.action == action]


def count(engine: Engine, matter_id: UUID) -> int:
    return PgCollectionRepository(engine).count_for_matter(matter_id)


@pytest.fixture
def env(clean_intake: Engine, tmp_path: Path):  # type: ignore[no-untyped-def]
    register, store = make_register(clean_intake, tmp_path)
    return clean_intake, tmp_path, register, store


def test_registers_new_collection(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, store = env
    acme = make_matter(engine)
    staged = stage_fixture(root, MINIMAL)
    collection = register.execute(acme, staged, MINIMAL, source="upload")

    digest = sha_of(MINIMAL)
    assert collection.sha256 == digest
    stored = root / "sha256" / digest[:2] / f"{digest}.zip"
    assert stored.read_bytes() == (FIXTURES_DIR / MINIMAL).read_bytes()
    assert stat.S_IMODE(stored.stat().st_mode) == 0o444
    assert not staged.exists()
    assert (collection.entry_count, collection.conversation_count, collection.root_prefix) == (
        8,
        2,
        "",
    )
    assert collection.source.value == "upload"
    events = audit(engine, "collection", collection.id, "collection.added")
    assert len(events) == 1
    assert events[0].details["sha256"] == digest
    assert events[0].details["source"] == "upload"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM blob")).scalar_one() == 1
    assert store.path_for(digest) == stored


def test_duplicate_in_same_matter_rejected(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine)
    first = register.execute(acme, stage_fixture(root, MINIMAL), MINIMAL)
    staged = stage_fixture(root, MINIMAL)
    with pytest.raises(DomainError) as info:
        register.execute(acme, staged, MINIMAL)
    assert info.value.code == "COLLECTION_DUPLICATE"
    assert info.value.details["existing_collection_id"] == str(first.id)
    assert MINIMAL in info.value.message
    assert first.sha256 in info.value.message
    assert count(engine, acme) == 1
    assert not staged.exists()
    rejected = audit(engine, "matter", acme, "collection.rejected")
    assert [e.details["reason_code"] for e in rejected] == ["COLLECTION_DUPLICATE"]
    assert rejected[0].details["sha256"] == first.sha256


def test_same_blob_other_matter_reused(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine, "Acme v. Beta")
    beta = make_matter(engine, "Beta Internal")
    first = register.execute(acme, stage_fixture(root, MINIMAL), MINIMAL)
    second_staged = stage_fixture(root, MINIMAL)
    second = register.execute(beta, second_staged, MINIMAL)
    assert second.id != first.id
    assert second.sha256 == first.sha256
    assert not second_staged.exists()
    assert len(list((root / "sha256").rglob("*.zip"))) == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM blob")).scalar_one() == 1


def test_limit_reached(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    full = make_matter(engine, "Full Matter")
    for i in range(1, 21):
        make_synthetic_collection(engine, full, i)
    staged = stage_fixture(root, MINIMAL)
    with pytest.raises(DomainError) as info:
        register.execute(full, staged, MINIMAL)
    assert info.value.code == "COLLECTION_LIMIT_REACHED"
    assert info.value.message == "This matter already has 20 collections (limit 20)."
    assert count(engine, full) == 20
    assert not staged.exists()


def test_not_slack_export_audited(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine)
    staged = stage_fixture(root, "missing-users.zip")
    with pytest.raises(DomainError) as info:
        register.execute(acme, staged, "missing-users.zip")
    assert info.value.code == "NOT_A_SLACK_EXPORT"
    assert count(engine, acme) == 0
    (event,) = audit(engine, "matter", acme, "collection.rejected")
    assert event.details["reason_code"] == "NOT_A_SLACK_EXPORT"
    assert event.details["original_filename"] == "missing-users.zip"
    assert event.details["sha256"] == sha_of("missing-users.zip")
    assert not (root / "sha256").exists()
    assert not staged.exists()


def test_path_traversal_rejected(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine)
    with pytest.raises(DomainError) as info:
        register.execute(acme, stage_fixture(root, "path-traversal.zip"), "path-traversal.zip")
    assert info.value.code == "ARCHIVE_REJECTED"
    assert info.value.details["rule"] == "path_escape"
    assert info.value.message == "Archive rejected: entry path escapes archive"
    (event,) = audit(engine, "matter", acme, "collection.rejected")
    assert event.details["rule"] == "path_escape"
    assert count(engine, acme) == 0


def test_not_a_zip_rejected(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine)
    with pytest.raises(DomainError) as info:
        register.execute(acme, stage_fixture(root, "not-a-zip.zip"), "not-a-zip.zip")
    assert info.value.details["rule"] == "not_a_zip"


def test_unknown_matter(env) -> None:  # type: ignore[no-untyped-def]
    _, root, register, _ = env
    staged = stage_fixture(root, MINIMAL)
    with pytest.raises(DomainError) as info:
        register.execute(uuid4(), staged, MINIMAL)
    assert info.value.code == "MATTER_NOT_FOUND"
    assert not staged.exists()
    assert not (root / "sha256").exists()


def test_hashes_when_sha_not_supplied(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine)
    collection = register.execute(acme, stage_fixture(root, MINIMAL), MINIMAL, sha256=None)
    assert collection.sha256 == sha_of(MINIMAL)


def test_supplied_sha_is_trusted(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine)
    collection = register.execute(
        acme, stage_fixture(root, MINIMAL), MINIMAL, sha256=sha_of(MINIMAL)
    )
    assert collection.sha256 == sha_of(MINIMAL)


def test_concurrent_duplicate_registration(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine)
    staged = [stage_fixture(root, MINIMAL), stage_fixture(root, MINIMAL)]
    outcomes: list[object] = []
    barrier = threading.Barrier(2)

    def work(path: Path) -> None:
        barrier.wait()
        try:
            outcomes.append(register.execute(acme, path, MINIMAL))
        except DomainError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=work, args=(p,)) for p in staged]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    errors = [o for o in outcomes if isinstance(o, DomainError)]
    assert len(outcomes) == 2
    assert len(errors) == 1
    assert errors[0].code == "COLLECTION_DUPLICATE"
    assert count(engine, acme) == 1
    assert not any(p.exists() for p in staged)


def test_generator_source_recorded(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, _ = env
    acme = make_matter(engine)
    collection = register.execute(
        acme,
        stage_fixture(root, MINIMAL),
        "slack-export-42-small-default.zip",
        source="generator",
    )
    assert collection.source.value == "generator"
    (event,) = audit(engine, "collection", collection.id, "collection.added")
    assert event.details["source"] == "generator"
    with engine.connect() as conn:
        source = conn.execute(
            text("SELECT source FROM collection WHERE id = :i"), {"i": collection.id}
        ).scalar_one()
    assert source == "generator"


def test_list_for_matter_in_registration_order(env) -> None:  # type: ignore[no-untyped-def]
    engine, root, register, store = env
    acme = make_matter(engine)
    register.execute(acme, stage_fixture(root, MINIMAL), MINIMAL)
    register.execute(acme, stage_fixture(root, "nested-export.zip"), "nested-export.zip")
    records = PgCollectionRepository(engine).list_for_matter(acme)
    assert [r.original_filename for r in records] == [MINIMAL, "nested-export.zip"]
    for r in records:
        assert store.path_for(r.sha256).is_file()
        assert r.size_bytes > 0
        assert r.added_at is not None


def test_db_failure_after_blob_move_keeps_blob_and_reuses_it(  # type: ignore[no-untyped-def]
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, root, register, store = env
    acme = make_matter(engine)
    original = PgCollectionRepository.add

    def boom(self, collection):  # type: ignore[no-untyped-def]
        raise RuntimeError("db down")

    monkeypatch.setattr(PgCollectionRepository, "add", boom)
    staged = stage_fixture(root, MINIMAL)
    with pytest.raises(RuntimeError):
        register.execute(acme, staged, MINIMAL)
    assert store.exists(sha_of(MINIMAL))
    assert count(engine, acme) == 0
    monkeypatch.setattr(PgCollectionRepository, "add", original)
    again = register.execute(acme, stage_fixture(root, MINIMAL), MINIMAL)
    assert again.sha256 == sha_of(MINIMAL)
