"""Database wiring: engine factory, transactional scope and health helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def make_engine(url: str, *, pool_size: int = 5, connect_timeout: int = 3) -> Engine:
    """Create a sync SQLAlchemy engine (psycopg 3) with UTC sessions."""
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args={"connect_timeout": connect_timeout, "options": "-c timezone=UTC"},
    )


@contextmanager
def session_scope(engine: Engine) -> Iterator[Connection]:
    """Yield a connection inside a transaction: commit on success, roll back on error."""
    with engine.begin() as conn:
        yield conn


def ping(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def current_revision(engine: Engine) -> str | None:
    """Return the Alembic revision stored in the DB (``None`` at base)."""
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
        if exists is None:
            return None
        rev = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
        return str(rev) if rev is not None else None
