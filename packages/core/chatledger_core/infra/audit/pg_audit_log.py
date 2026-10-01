"""PostgreSQL adapter for the append-only audit log."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any

from sqlalchemy import Connection, Engine, RowMapping, text

from chatledger_core.domain.audit.audit_event import AuditEvent
from chatledger_core.infra.db.tx import TransactionalAdapter

_COLUMNS = "id, occurred_at, action, entity_type, entity_id, details"


def _row_to_event(row: RowMapping) -> AuditEvent:
    return AuditEvent(
        id=int(row["id"]),
        occurred_at=row["occurred_at"].astimezone(UTC),
        action=row["action"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        details=dict(row["details"] or {}),
    )


class PgAuditLog(TransactionalAdapter):
    def __init__(self, engine: Engine, *, conn: Connection | None = None) -> None:
        super().__init__(engine, conn)

    def within(self, conn: Connection) -> PgAuditLog:
        """Return a log bound to the caller's transaction."""
        return PgAuditLog(self._engine, conn=conn)

    def record(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        stmt = text(
            f"""
            INSERT INTO audit_event (action, entity_type, entity_id, details)
            VALUES (:action, :entity_type, :entity_id, CAST(:details AS jsonb))
            RETURNING {_COLUMNS}
            """
        )
        with self._tx() as conn:
            row = (
                conn.execute(
                    stmt,
                    {
                        "action": action,
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "details": json.dumps(details or {}),
                    },
                )
                .mappings()
                .one()
            )
        return _row_to_event(row)

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditEvent]:
        stmt = text(
            f"""
            SELECT {_COLUMNS} FROM audit_event
            WHERE entity_type = :entity_type AND entity_id = :entity_id
            ORDER BY id
            """
        )
        with self._tx() as conn:
            rows = (
                conn.execute(stmt, {"entity_type": entity_type, "entity_id": entity_id})
                .mappings()
                .all()
            )
        return [_row_to_event(r) for r in rows]
