"""One PostgreSQL transaction shared by the intake repositories and the audit log."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy import Connection, Engine

from chatledger_core.infra.audit.pg_audit_log import PgAuditLog
from chatledger_core.infra.intake.pg_collection_repository import PgCollectionRepository
from chatledger_core.infra.intake.pg_matter_repository import PgMatterRepository


class PgIntakeUnitOfWork:
    """Commits when the ``with`` block exits cleanly, rolls back on any exception."""

    matters: PgMatterRepository
    collections: PgCollectionRepository
    audit: PgAuditLog

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._conn: Connection | None = None

    def __enter__(self) -> PgIntakeUnitOfWork:
        conn = self._engine.connect()
        conn.begin()
        self._conn = conn
        self.matters = PgMatterRepository(self._engine, conn)
        self.collections = PgCollectionRepository(self._engine, conn)
        self.audit = PgAuditLog(self._engine, conn=conn)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        conn = self._conn
        assert conn is not None
        self._conn = None
        try:
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
        finally:
            conn.close()
