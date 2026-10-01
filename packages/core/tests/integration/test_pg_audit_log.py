"""PgAuditLog + append-only triggers (contract SVC-AUDIT-01..04)."""

from __future__ import annotations

from datetime import UTC

import psycopg
import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from chatledger_core.domain.audit.audit_event import AuditEvent
from chatledger_core.infra.audit.pg_audit_log import PgAuditLog
from factories import make_audit_event


@pytest.fixture
def audit(db_conn: Connection) -> PgAuditLog:
    return PgAuditLog(db_conn.engine).within(db_conn)


def _assert_append_only(exc: DBAPIError) -> None:
    orig = exc.orig
    assert isinstance(orig, psycopg.Error)
    assert orig.sqlstate == "55000"
    assert "audit_event is append-only" in str(orig)


def test_record_returns_event_with_id(audit: PgAuditLog) -> None:
    event = audit.record("test.recorded", "test", "rec-1", {"k": "v"})
    assert event.id > 0
    assert event.occurred_at.tzinfo is not None
    assert event.occurred_at.utcoffset() == UTC.utcoffset(None)
    assert audit.list_for_entity("test", "rec-1") == [event]
    assert event.details == {"k": "v"}


def test_record_without_details(audit: PgAuditLog) -> None:
    assert audit.record("test.recorded", "test", "rec-2").details == {}


def test_audit_seed_fixture(audit_seed: AuditEvent) -> None:
    assert audit_seed.action == "test.seeded"
    assert (audit_seed.entity_type, audit_seed.entity_id) == ("test", "seed-1")
    assert audit_seed.details == {"note": "seed"}


def test_update_rejected_by_trigger(db_conn: Connection, audit_seed: AuditEvent) -> None:
    sp = db_conn.begin_nested()
    with pytest.raises(DBAPIError) as info:
        db_conn.execute(
            text("UPDATE audit_event SET action = 'test.changed' WHERE id = :id"),
            {"id": audit_seed.id},
        )
    sp.rollback()
    _assert_append_only(info.value)
    action = db_conn.execute(
        text("SELECT action FROM audit_event WHERE id = :id"), {"id": audit_seed.id}
    ).scalar()
    assert action == "test.seeded"


def test_delete_rejected_by_trigger(db_conn: Connection, audit_seed: AuditEvent) -> None:
    sp = db_conn.begin_nested()
    with pytest.raises(DBAPIError) as info:
        db_conn.execute(text("DELETE FROM audit_event WHERE id = :id"), {"id": audit_seed.id})
    sp.rollback()
    _assert_append_only(info.value)
    assert (
        db_conn.execute(
            text("SELECT count(*) FROM audit_event WHERE id = :id"), {"id": audit_seed.id}
        ).scalar()
        == 1
    )


def test_truncate_rejected_by_trigger(db_conn: Connection, audit_seed: AuditEvent) -> None:
    sp = db_conn.begin_nested()
    with pytest.raises(DBAPIError) as info:
        db_conn.execute(text("TRUNCATE audit_event"))
    sp.rollback()
    _assert_append_only(info.value)
    assert (
        db_conn.execute(
            text("SELECT count(*) FROM audit_event WHERE id = :id"), {"id": audit_seed.id}
        ).scalar()
        == 1
    )


def test_invalid_action_format_rejected(db_conn: Connection) -> None:
    sp = db_conn.begin_nested()
    with pytest.raises(IntegrityError, match="ck_audit_action_format"):
        make_audit_event(db_conn, action="Bad Action")
    sp.rollback()


def test_list_for_entity_ordered(audit: PgAuditLog) -> None:
    events = [audit.record("test.step", "test", "ord-1", {"n": n}) for n in range(3)]
    audit.record("test.step", "test", "other", {})
    listed = audit.list_for_entity("test", "ord-1")
    assert [e.id for e in listed] == sorted(e.id for e in events)
    assert [e.details["n"] for e in listed] == [0, 1, 2]
