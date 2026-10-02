"""Root pytest configuration shared by every Python test package.

Loads ``.env.test`` into the process environment *before* any test module
imports application code, without overriding variables already exported
(CI or a developer can point ``TEST_DATABASE_URL`` elsewhere).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent

for _key, _value in dotenv_values(ROOT / ".env.test").items():
    if _value is not None:
        os.environ.setdefault(_key, _value)


# --------------------------------------------------------------------------- DB fixtures
# Imported after the environment is loaded so Settings sees .env.test values.
from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import Connection, Engine, text  # noqa: E402

from chatledger_core.domain.audit.audit_event import AuditEvent  # noqa: E402
from chatledger_core.infra.db import migrations  # noqa: E402
from chatledger_core.infra.db.engine import make_engine  # noqa: E402


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return os.environ["TEST_DATABASE_URL"]


@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Iterator[Engine]:
    """Engine on the real PostgreSQL 16 test DB, migrated to head once per session."""
    eng = make_engine(test_database_url, pool_size=10)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.fail(f"PostgreSQL not reachable at TEST_DATABASE_URL={test_database_url}: {exc}")
    migrations.upgrade(test_database_url, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db_conn(engine: Engine) -> Iterator[Connection]:
    """A connection whose transaction is rolled back after the test."""
    conn = engine.connect()
    tx = conn.begin()
    try:
        yield conn
    finally:
        tx.rollback()
        conn.close()


def _purge_jobs(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job"))
        conn.execute(text("DELETE FROM worker_heartbeat"))


@pytest.fixture
def clean_jobs(engine: Engine) -> Iterator[Engine]:
    """Committed-data tests: start and end with no job / heartbeat rows."""
    _purge_jobs(engine)
    yield engine
    _purge_jobs(engine)


@pytest.fixture
def audit_seed(db_conn: Connection) -> AuditEvent:
    """Contract prerequisite ``audit-seed`` (inside the rolled-back test transaction)."""
    from factories import make_audit_event

    return make_audit_event(db_conn)


def _purge_intake(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM collection"))
        conn.execute(text("DELETE FROM blob"))
        conn.execute(text("DELETE FROM matter"))


@pytest.fixture
def clean_intake(engine: Engine) -> Iterator[Engine]:
    """Committed-data tests: start and end with no matter / collection / blob rows."""
    _purge_intake(engine)
    yield engine
    _purge_intake(engine)
