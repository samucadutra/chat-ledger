"""PostgreSQL adapter for generations (raw SQL, like the intake adapters).

The effective state joins the queue: a ``queued``/``running`` row whose job permanently failed
(crash retries exhausted) is reported as ``failed`` with the job's last error.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, Engine, RowMapping, text

from chatledger_core.domain.generator.ports import GenerationRecord, NewGeneration
from chatledger_core.infra.db.tx import TransactionalAdapter

_JOB_FAILED = "g.state IN ('queued', 'running') AND j.state = 'failed'"
_SELECT = f"""
    SELECT g.id, g.matter_id, g.seed, g.preset, g.profile, g.messages, g.conversations,
           g.overlap_of_collection_id, g.overlap_days_pct, g.job_id,
           CASE WHEN {_JOB_FAILED} THEN 'failed' ELSE g.state END AS state,
           g.progress_messages, g.collection_id, g.ground_truth_sha256,
           CASE WHEN {_JOB_FAILED} THEN 'GENERATION_FAILED' ELSE g.error_code END AS error_code,
           CASE WHEN {_JOB_FAILED} THEN COALESCE(j.last_error, 'Job failed')
                ELSE g.error_message END AS error_message,
           g.created_at, g.updated_at, COALESCE(j.attempts, 0) AS job_attempts
    FROM generation g LEFT JOIN job j ON j.id = g.job_id
"""


def _record(row: RowMapping) -> GenerationRecord:
    return GenerationRecord(
        id=row["id"],
        matter_id=row["matter_id"],
        seed=int(row["seed"]),
        preset=row["preset"],
        profile=row["profile"],
        messages=int(row["messages"]),
        conversations=int(row["conversations"]),
        overlap_of_collection_id=row["overlap_of_collection_id"],
        overlap_days_pct=int(row["overlap_days_pct"]),
        job_id=row["job_id"],
        state=row["state"],
        progress_messages=int(row["progress_messages"]),
        collection_id=row["collection_id"],
        ground_truth_sha256=row["ground_truth_sha256"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        job_attempts=int(row["job_attempts"]),
    )


class PgGenerationRepository(TransactionalAdapter):
    def __init__(self, engine: Engine, conn: Connection | None = None) -> None:
        super().__init__(engine, conn)

    def add(self, generation: NewGeneration) -> GenerationRecord:
        stmt = text(
            """
            INSERT INTO generation (matter_id, seed, preset, profile, messages, conversations,
                                    overlap_of_collection_id, overlap_days_pct)
            VALUES (:matter_id, :seed, :preset, :profile, :messages, :conversations,
                    :overlap_of_collection_id, :overlap_days_pct)
            RETURNING id
            """
        )
        with self._tx() as conn:
            new_id: UUID = conn.execute(
                stmt,
                {
                    "matter_id": generation.matter_id,
                    "seed": generation.seed,
                    "preset": generation.preset,
                    "profile": generation.profile,
                    "messages": generation.messages,
                    "conversations": generation.conversations,
                    "overlap_of_collection_id": generation.overlap_of_collection_id,
                    "overlap_days_pct": generation.overlap_days_pct,
                },
            ).scalar_one()
        record = self.get(new_id)
        assert record is not None
        return record

    def get(self, generation_id: UUID) -> GenerationRecord | None:
        with self._tx() as conn:
            row = (
                conn.execute(text(_SELECT + " WHERE g.id = :id"), {"id": generation_id})
                .mappings()
                .first()
            )
        return _record(row) if row is not None else None

    def list_for_matter(self, matter_id: UUID) -> list[GenerationRecord]:
        stmt = text(_SELECT + " WHERE g.matter_id = :matter_id ORDER BY g.created_at DESC, g.id")
        with self._tx() as conn:
            rows = conn.execute(stmt, {"matter_id": matter_id}).mappings().all()
        return [_record(r) for r in rows]

    def delete(self, generation_id: UUID) -> None:
        with self._tx() as conn:
            conn.execute(text("DELETE FROM generation WHERE id = :id"), {"id": generation_id})

    def attach_job(self, generation_id: UUID, job_id: UUID) -> None:
        stmt = text(
            "UPDATE generation SET job_id = :job_id, updated_at = clock_timestamp() WHERE id = :id"
        )
        with self._tx() as conn:
            conn.execute(stmt, {"id": generation_id, "job_id": job_id})

    def reset_for_retry(self, generation_id: UUID, job_id: UUID) -> GenerationRecord:
        stmt = text(
            """
            UPDATE generation
            SET state = 'queued', progress_messages = 0, error_code = NULL,
                error_message = NULL, collection_id = NULL, ground_truth_sha256 = NULL,
                job_id = :job_id, updated_at = clock_timestamp()
            WHERE id = :id
            """
        )
        with self._tx() as conn:
            conn.execute(stmt, {"id": generation_id, "job_id": job_id})
        record = self.get(generation_id)
        assert record is not None
        return record

    def mark_running(self, generation_id: UUID) -> None:
        stmt = text(
            """
            UPDATE generation
            SET state = 'running', progress_messages = 0, error_code = NULL,
                error_message = NULL, updated_at = clock_timestamp()
            WHERE id = :id
            """
        )
        with self._tx() as conn:
            conn.execute(stmt, {"id": generation_id})

    def update_progress(self, generation_id: UUID, progress_messages: int) -> None:
        stmt = text(
            """
            UPDATE generation
            SET progress_messages = GREATEST(progress_messages, :progress),
                updated_at = clock_timestamp()
            WHERE id = :id AND state = 'running'
            """
        )
        with self._tx() as conn:
            conn.execute(stmt, {"id": generation_id, "progress": progress_messages})

    def mark_done(
        self,
        generation_id: UUID,
        *,
        collection_id: UUID,
        ground_truth_sha256: str,
        progress_messages: int,
    ) -> None:
        stmt = text(
            """
            UPDATE generation
            SET state = 'done', collection_id = :collection_id,
                ground_truth_sha256 = :ground_truth_sha256, progress_messages = :progress,
                error_code = NULL, error_message = NULL, updated_at = clock_timestamp()
            WHERE id = :id
            """
        )
        with self._tx() as conn:
            conn.execute(
                stmt,
                {
                    "id": generation_id,
                    "collection_id": collection_id,
                    "ground_truth_sha256": ground_truth_sha256,
                    "progress": progress_messages,
                },
            )

    def mark_failed(self, generation_id: UUID, code: str, message: str) -> None:
        stmt = text(
            """
            UPDATE generation
            SET state = 'failed', error_code = :code, error_message = :message,
                updated_at = clock_timestamp()
            WHERE id = :id
            """
        )
        with self._tx() as conn:
            conn.execute(stmt, {"id": generation_id, "code": code, "message": message})

    def find_by_collection(self, collection_id: UUID) -> GenerationRecord | None:
        with self._tx() as conn:
            row = (
                conn.execute(
                    text(_SELECT + " WHERE g.collection_id = :collection_id"),
                    {"collection_id": collection_id},
                )
                .mappings()
                .first()
            )
        return _record(row) if row is not None else None

    def find_seed_for_collection(self, matter_id: UUID, collection_id: UUID) -> int | None:
        stmt = text(
            "SELECT seed FROM generation WHERE matter_id = :matter_id "
            "AND collection_id = :collection_id"
        )
        with self._tx() as conn:
            value = conn.execute(
                stmt, {"matter_id": matter_id, "collection_id": collection_id}
            ).scalar_one_or_none()
        return int(value) if value is not None else None
