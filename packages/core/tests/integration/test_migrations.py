from sqlalchemy import Engine, text

from chatledger_core.infra.db import migrations
from chatledger_core.infra.db.engine import current_revision, ping, session_scope


def test_head_is_intake() -> None:
    assert migrations.head_revision() == "0003_generation"


def test_upgrade_downgrade_round_trip(engine: Engine, test_database_url: str) -> None:
    assert current_revision(engine) == "0003_generation"
    migrations.downgrade(test_database_url, "base")
    try:
        assert current_revision(engine) is None
        with engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('public.job')")).scalar() is None
    finally:
        migrations.upgrade(test_database_url, "head")
    assert current_revision(engine) == "0003_generation"
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
    assert {"job", "audit_event", "worker_heartbeat", "generation"} <= tables


def test_indexes_and_triggers_exist(engine: Engine) -> None:
    with engine.connect() as conn:
        indexes = {r[0] for r in conn.execute(text("SELECT indexname FROM pg_indexes"))}
        triggers = {
            r[0] for r in conn.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"))
        }
    assert {
        "ix_job_claimable",
        "ix_job_leased_expiry",
        "ix_job_group_state",
        "ix_audit_entity",
        "ix_audit_occurred_at",
        "ix_worker_heartbeat_last_seen",
        "ix_generation_matter_created",
        "uq_generation_collection",
    } <= indexes
    assert {"trg_audit_event_no_update_delete", "trg_audit_event_no_truncate"} <= triggers


def test_ping_and_session_scope(engine: Engine) -> None:
    assert ping(engine)
    with session_scope(engine) as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_ping_false_when_unreachable() -> None:
    from chatledger_core.infra.db.engine import make_engine

    dead = make_engine("postgresql+psycopg://x:y@127.0.0.1:1/none", connect_timeout=1)
    assert not ping(dead)
    dead.dispose()
