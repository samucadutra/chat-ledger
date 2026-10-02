from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from chatledger_core.domain.intake.errors import (
    MatterNameInvalidError,
    MatterNameTakenError,
    MatterNotFoundError,
)
from chatledger_core.infra.audit.pg_audit_log import PgAuditLog
from chatledger_core.infra.intake.pg_matter_repository import PgMatterRepository
from chatledger_core.infra.intake.pg_unit_of_work import PgIntakeUnitOfWork
from chatledger_core.usecase.intake.create_matter import CreateMatter
from chatledger_core.usecase.intake.get_matter import GetMatter
from chatledger_core.usecase.intake.list_collections import GetCollection, ListCollections
from chatledger_core.usecase.intake.list_matters import ListMatters
from factories import make_matter, make_register, stage_fixture


def test_create_get_list(clean_intake: Engine) -> None:
    def factory() -> PgIntakeUnitOfWork:
        return PgIntakeUnitOfWork(clean_intake)

    created = CreateMatter(factory).execute("  Acme v. Beta ", " note ")
    assert (created.name, created.description) == ("Acme v. Beta", "note")
    assert (created.collection_count, created.total_size_bytes) == (0, 0)
    beta = CreateMatter(factory).execute("Beta Internal")
    assert beta.description is None
    fetched = GetMatter(factory).execute(created.id)
    assert fetched.id == created.id
    assert [m.name for m in ListMatters(factory).execute()] == ["Beta Internal", "Acme v. Beta"]
    events = PgAuditLog(clean_intake).list_for_entity("matter", str(created.id))
    assert [e.action for e in events] == ["matter.created"]
    assert events[0].details["name"] == "Acme v. Beta"


def test_name_clash_is_case_insensitive_and_trim_insensitive(clean_intake: Engine) -> None:
    def factory() -> PgIntakeUnitOfWork:
        return PgIntakeUnitOfWork(clean_intake)

    first = CreateMatter(factory).execute("Acme v. Beta")
    with pytest.raises(MatterNameTakenError) as info:
        CreateMatter(factory).execute("  ACME V. BETA  ")
    assert info.value.message == "A matter with this name already exists"
    assert info.value.details["existing_matter_id"] == str(first.id)
    assert len(ListMatters(factory).execute()) == 1


def test_invalid_name_not_persisted(clean_intake: Engine) -> None:
    def factory() -> PgIntakeUnitOfWork:
        return PgIntakeUnitOfWork(clean_intake)

    with pytest.raises(MatterNameInvalidError):
        CreateMatter(factory).execute("Ab")
    assert ListMatters(factory).execute() == []


def test_get_unknown_matter(clean_intake: Engine) -> None:
    with pytest.raises(MatterNotFoundError):
        GetMatter(lambda: PgIntakeUnitOfWork(clean_intake)).execute(uuid4())


def test_repository_name_exists_and_lock(clean_intake: Engine) -> None:
    matter_id = make_matter(clean_intake, "Acme v. Beta")
    repo = PgMatterRepository(clean_intake)
    assert repo.name_exists("acme V. beta ")
    assert not repo.name_exists("other")
    with PgIntakeUnitOfWork(clean_intake) as uow:
        locked = uow.matters.get_for_update(matter_id)
        assert locked is not None
        assert locked.id == matter_id
        assert uow.matters.get_for_update(uuid4()) is None


def test_uow_rolls_back_on_error(clean_intake: Engine) -> None:
    def fail() -> None:
        with PgIntakeUnitOfWork(clean_intake) as uow:
            uow.matters.add("Rolled back", None)
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        fail()
    assert not PgMatterRepository(clean_intake).name_exists("Rolled back")


def test_summaries_include_counts_and_sizes(clean_intake: Engine, tmp_path: Path) -> None:
    acme = make_matter(clean_intake, "Acme v. Beta")
    make_matter(clean_intake, "Beta Internal")
    register, _ = make_register(clean_intake, tmp_path)
    collection = register.execute(
        acme, stage_fixture(tmp_path, "minimal-export.zip"), "minimal-export.zip"
    )

    def factory() -> PgIntakeUnitOfWork:
        return PgIntakeUnitOfWork(clean_intake)

    summaries = {m.name: m for m in ListMatters(factory).execute()}
    assert summaries["Acme v. Beta"].collection_count == 1
    assert summaries["Acme v. Beta"].total_size_bytes == collection.size_bytes
    assert summaries["Beta Internal"].collection_count == 0
    listed = ListCollections(factory).execute(acme)
    assert [c.id for c in listed] == [collection.id]
    assert GetCollection(factory).execute(acme, collection.id).id == collection.id


def test_collection_lookups_scoped_to_matter(clean_intake: Engine, tmp_path: Path) -> None:
    from chatledger_core.domain.intake.errors import CollectionNotFoundError

    acme = make_matter(clean_intake, "Acme v. Beta")
    beta = make_matter(clean_intake, "Beta Internal")
    register, _ = make_register(clean_intake, tmp_path)
    collection = register.execute(
        acme, stage_fixture(tmp_path, "minimal-export.zip"), "minimal-export.zip"
    )

    def factory() -> PgIntakeUnitOfWork:
        return PgIntakeUnitOfWork(clean_intake)

    with pytest.raises(CollectionNotFoundError):
        GetCollection(factory).execute(beta, collection.id)
    with pytest.raises(CollectionNotFoundError):
        GetCollection(factory).execute(acme, uuid4())
    with pytest.raises(MatterNotFoundError):
        GetCollection(factory).execute(uuid4(), collection.id)
    with pytest.raises(MatterNotFoundError):
        ListCollections(factory).execute(uuid4())
