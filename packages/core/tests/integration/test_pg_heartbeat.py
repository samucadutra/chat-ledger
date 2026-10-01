from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Connection, text

from chatledger_core.infra.heartbeat.pg_heartbeat import PgHeartbeat


def test_beat_upserts_and_counts(db_conn: Connection) -> None:
    db_conn.execute(text("DELETE FROM worker_heartbeat"))
    hb = PgHeartbeat(db_conn.engine, conn=db_conn)
    hb.beat("h-1", hostname="h", pid=1, git_sha="unknown")
    first = db_conn.execute(
        text("SELECT last_seen_at FROM worker_heartbeat WHERE worker_id = 'h-1'")
    ).scalar_one()
    job_id = uuid4()
    hb.beat("h-1", hostname="h", pid=1, git_sha="a" * 40, current_job_id=job_id)
    row = db_conn.execute(text("SELECT * FROM worker_heartbeat")).mappings().all()
    assert len(row) == 1
    assert row[0]["git_sha"] == "a" * 40
    assert row[0]["current_job_id"] == job_id
    assert row[0]["last_seen_at"] >= first
    assert hb.count_active(30) == 1


def test_count_active_counts_recent_only(db_conn: Connection) -> None:
    db_conn.execute(text("DELETE FROM worker_heartbeat"))
    hb = PgHeartbeat(db_conn.engine, conn=db_conn)
    hb.beat("fresh", hostname="h", pid=1, git_sha="unknown")
    hb.beat("stale", hostname="h", pid=2, git_sha="unknown")
    db_conn.execute(
        text(
            "UPDATE worker_heartbeat SET last_seen_at = now() - interval '45 seconds' "
            "WHERE worker_id = 'stale'"
        )
    )
    assert hb.count_active(30) == 1


def test_remove(db_conn: Connection) -> None:
    db_conn.execute(text("DELETE FROM worker_heartbeat"))
    hb = PgHeartbeat(db_conn.engine, conn=db_conn)
    hb.beat("gone", hostname="h", pid=1, git_sha="unknown")
    hb.remove("gone")
    assert hb.count_active(30) == 0
