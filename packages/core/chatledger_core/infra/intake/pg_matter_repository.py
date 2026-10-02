"""PostgreSQL adapter for matters."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, Engine, RowMapping, text

from chatledger_core.domain.intake.errors import MatterNameTakenError
from chatledger_core.domain.intake.matter import Matter, MatterSummary
from chatledger_core.infra.db.tx import TransactionalAdapter

_SUMMARY_SQL = """
    SELECT m.id, m.name, m.description, m.created_at,
           COUNT(c.id)::int AS collection_count,
           COALESCE(SUM(c.size_bytes), 0)::bigint AS total_size_bytes
    FROM matter m LEFT JOIN collection c ON c.matter_id = m.id
"""


def _summary(row: RowMapping) -> MatterSummary:
    return MatterSummary(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
        collection_count=int(row["collection_count"]),
        total_size_bytes=int(row["total_size_bytes"]),
    )


class PgMatterRepository(TransactionalAdapter):
    def __init__(self, engine: Engine, conn: Connection | None = None) -> None:
        super().__init__(engine, conn)

    def add(self, name: str, description: str | None) -> Matter:
        stmt = text(
            """
            INSERT INTO matter (name, description) VALUES (:name, :description)
            ON CONFLICT (name_key) DO NOTHING
            RETURNING id, name, description, created_at
            """
        )
        with self._tx() as conn:
            row = conn.execute(stmt, {"name": name, "description": description}).mappings().first()
            if row is None:
                existing = conn.execute(
                    text("SELECT id FROM matter WHERE name_key = lower(btrim(:name))"),
                    {"name": name},
                ).scalar()
                raise MatterNameTakenError(existing)
        return Matter(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
        )

    def get(self, matter_id: UUID) -> MatterSummary | None:
        stmt = text(f"{_SUMMARY_SQL} WHERE m.id = :id GROUP BY m.id")
        with self._tx() as conn:
            row = conn.execute(stmt, {"id": matter_id}).mappings().first()
        return _summary(row) if row is not None else None

    def get_for_update(self, matter_id: UUID) -> Matter | None:
        stmt = text(
            "SELECT id, name, description, created_at FROM matter WHERE id = :id FOR UPDATE"
        )
        with self._tx() as conn:
            row = conn.execute(stmt, {"id": matter_id}).mappings().first()
        if row is None:
            return None
        return Matter(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
        )

    def list_summaries(self) -> list[MatterSummary]:
        stmt = text(f"{_SUMMARY_SQL} GROUP BY m.id ORDER BY m.created_at DESC, m.id DESC")
        with self._tx() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [_summary(r) for r in rows]

    def name_exists(self, name: str) -> bool:
        stmt = text("SELECT 1 FROM matter WHERE name_key = lower(btrim(:name))")
        with self._tx() as conn:
            return conn.execute(stmt, {"name": name}).first() is not None
