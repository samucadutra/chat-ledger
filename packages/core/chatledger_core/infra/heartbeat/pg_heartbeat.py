"""Worker heartbeat adapter: liveness upsert and active-worker count."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, Engine, text

from chatledger_core.infra.db.tx import TransactionalAdapter


class PgHeartbeat(TransactionalAdapter):
    def __init__(self, engine: Engine, *, conn: Connection | None = None) -> None:
        super().__init__(engine, conn)

    def beat(
        self,
        worker_id: str,
        *,
        hostname: str,
        pid: int,
        git_sha: str,
        current_job_id: UUID | None = None,
    ) -> None:
        stmt = text(
            """
            INSERT INTO worker_heartbeat
                (worker_id, hostname, pid, git_sha, started_at, last_seen_at, current_job_id)
            VALUES (:worker_id, :hostname, :pid, :git_sha, now(), now(), :current_job_id)
            ON CONFLICT (worker_id) DO UPDATE SET
                last_seen_at = now(),
                git_sha = EXCLUDED.git_sha,
                current_job_id = EXCLUDED.current_job_id
            """
        )
        with self._tx() as conn:
            conn.execute(
                stmt,
                {
                    "worker_id": worker_id,
                    "hostname": hostname,
                    "pid": pid,
                    "git_sha": git_sha[:40],
                    "current_job_id": current_job_id,
                },
            )

    def remove(self, worker_id: str) -> None:
        with self._tx() as conn:
            conn.execute(
                text("DELETE FROM worker_heartbeat WHERE worker_id = :w"), {"w": worker_id}
            )

    def count_active(self, window_seconds: float = 30) -> int:
        stmt = text(
            """
            SELECT count(*) FROM worker_heartbeat
            WHERE last_seen_at > now() - make_interval(secs => :window)
            """
        )
        with self._tx() as conn:
            value: int = conn.execute(stmt, {"window": window_seconds}).scalar_one()
        return int(value)
