"""PostgreSQL adapter for collections and their blob rows."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, Engine, RowMapping, text

from chatledger_core.domain.intake.collection import (
    BlobRef,
    Collection,
    CollectionGeneration,
    CollectionSource,
    NewCollection,
)
from chatledger_core.infra.db.tx import TransactionalAdapter

_COLUMNS = (
    "id, matter_id, blob_sha256, original_filename, size_bytes, source, entry_count, "
    "conversation_count, export_date_from, export_date_to, root_prefix, added_at"
)


_JOINED_COLUMNS = (
    "c.id, c.matter_id, c.blob_sha256, c.original_filename, c.size_bytes, c.source, "
    "c.entry_count, c.conversation_count, c.export_date_from, c.export_date_to, "
    "c.root_prefix, c.added_at, g.id AS gen_id, g.seed AS gen_seed, g.preset AS gen_preset, "
    "g.profile AS gen_profile, (g.ground_truth_sha256 IS NOT NULL) AS gen_has_ground_truth"
)
_JOINED_FROM = "collection c LEFT JOIN generation g ON g.collection_id = c.id"


def _row_to_collection(row: RowMapping) -> Collection:
    generation = None
    if row.get("gen_id") is not None:
        generation = CollectionGeneration(
            id=row["gen_id"],
            seed=int(row["gen_seed"]),
            preset=row["gen_preset"],
            profile=row["gen_profile"],
            has_ground_truth=bool(row["gen_has_ground_truth"]),
        )
    return Collection(
        id=row["id"],
        matter_id=row["matter_id"],
        sha256=row["blob_sha256"],
        original_filename=row["original_filename"],
        size_bytes=int(row["size_bytes"]),
        source=CollectionSource(row["source"]),
        entry_count=int(row["entry_count"]),
        conversation_count=int(row["conversation_count"]),
        export_date_from=row["export_date_from"],
        export_date_to=row["export_date_to"],
        root_prefix=row["root_prefix"],
        added_at=row["added_at"],
        generation=generation,
    )


class PgCollectionRepository(TransactionalAdapter):
    def __init__(self, engine: Engine, conn: Connection | None = None) -> None:
        super().__init__(engine, conn)

    def ensure_blob(self, blob: BlobRef) -> None:
        stmt = text(
            """
            INSERT INTO blob (sha256, size_bytes, storage_path)
            VALUES (:sha256, :size_bytes, :storage_path)
            ON CONFLICT (sha256) DO NOTHING
            """
        )
        with self._tx() as conn:
            conn.execute(
                stmt,
                {
                    "sha256": blob.sha256,
                    "size_bytes": blob.size_bytes,
                    "storage_path": blob.storage_path,
                },
            )

    def add(self, collection: NewCollection) -> Collection:
        stmt = text(
            f"""
            INSERT INTO collection (matter_id, blob_sha256, original_filename, size_bytes, source,
                                    entry_count, conversation_count, export_date_from,
                                    export_date_to, root_prefix)
            VALUES (:matter_id, :sha256, :original_filename, :size_bytes, :source, :entry_count,
                    :conversation_count, :export_date_from, :export_date_to, :root_prefix)
            RETURNING {_COLUMNS}
            """
        )
        with self._tx() as conn:
            row = (
                conn.execute(
                    stmt,
                    {
                        "matter_id": collection.matter_id,
                        "sha256": collection.sha256,
                        "original_filename": collection.original_filename,
                        "size_bytes": collection.size_bytes,
                        "source": collection.source.value,
                        "entry_count": collection.entry_count,
                        "conversation_count": collection.conversation_count,
                        "export_date_from": collection.export_date_from,
                        "export_date_to": collection.export_date_to,
                        "root_prefix": collection.root_prefix,
                    },
                )
                .mappings()
                .one()
            )
        return _row_to_collection(row)

    def find_by_sha(self, matter_id: UUID, sha256: str) -> Collection | None:
        stmt = text(
            f"SELECT {_COLUMNS} FROM collection WHERE matter_id = :matter_id "
            "AND blob_sha256 = :sha256"
        )
        with self._tx() as conn:
            row = conn.execute(stmt, {"matter_id": matter_id, "sha256": sha256}).mappings().first()
        return _row_to_collection(row) if row is not None else None

    def count_for_matter(self, matter_id: UUID) -> int:
        stmt = text("SELECT COUNT(*) FROM collection WHERE matter_id = :matter_id")
        with self._tx() as conn:
            return int(conn.execute(stmt, {"matter_id": matter_id}).scalar_one())

    def list_for_matter(self, matter_id: UUID) -> list[Collection]:
        stmt = text(
            f"SELECT {_JOINED_COLUMNS} FROM {_JOINED_FROM} WHERE c.matter_id = :matter_id "
            "ORDER BY c.added_at, c.id"
        )
        with self._tx() as conn:
            rows = conn.execute(stmt, {"matter_id": matter_id}).mappings().all()
        return [_row_to_collection(r) for r in rows]

    def get(self, matter_id: UUID, collection_id: UUID) -> Collection | None:
        stmt = text(
            f"SELECT {_JOINED_COLUMNS} FROM {_JOINED_FROM} "
            "WHERE c.matter_id = :matter_id AND c.id = :id"
        )
        with self._tx() as conn:
            row = (
                conn.execute(stmt, {"matter_id": matter_id, "id": collection_id}).mappings().first()
            )
        return _row_to_collection(row) if row is not None else None
