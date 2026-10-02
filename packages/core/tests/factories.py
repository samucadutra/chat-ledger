"""Test factories shared by every Python test package (project convention, spec A6).

DB state for tests comes from these builders plus the fixtures in the root
``conftest.py`` — there are no SQL seed files.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from chatledger_core.domain.audit.audit_event import AuditEvent
from chatledger_core.domain.jobs.job import Job, JobState
from chatledger_core.infra.audit.pg_audit_log import PgAuditLog
from chatledger_core.infra.blobstore.fs_blob_store import FsBlobStore
from chatledger_core.infra.intake.pg_unit_of_work import PgIntakeUnitOfWork
from chatledger_core.infra.intake.zip_archive_inspector import ZipArchiveInspector
from chatledger_core.infra.queue.pg_job_queue import PgJobQueue, row_to_job
from chatledger_core.usecase.intake.register_collection import RegisterCollection

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "intake"

# Contract handle ``audit-seed``.
AUDIT_SEED: dict[str, Any] = {
    "action": "test.seeded",
    "entity_type": "test",
    "entity_id": "seed-1",
    "details": {"note": "seed"},
}


def make_audit_event(conn: Connection, **overrides: Any) -> AuditEvent:
    """Insert an audit event (defaults to the ``audit-seed`` handle)."""
    fields = {**AUDIT_SEED, **overrides}
    engine: Engine = conn.engine
    return PgAuditLog(engine, conn=conn).record(
        fields["action"], fields["entity_type"], fields["entity_id"], fields["details"]
    )


def make_job(
    conn: Connection,
    *,
    kind: str = "noop",
    payload: dict[str, Any] | None = None,
    state: JobState | str = JobState.QUEUED,
    priority: int = 100,
    attempts: int = 0,
    max_attempts: int = 3,
    lease_owner: str | None = None,
    lease_expires_at: datetime | None = None,
    run_after: datetime | None = None,
    group_key: str | None = None,
) -> Job:
    """Insert a job row with arbitrary state (bypasses the queue's transitions)."""
    state_value = JobState(state).value
    row = (
        conn.execute(
            text(
                """
                INSERT INTO job (kind, payload, state, priority, attempts, max_attempts,
                                 lease_owner, lease_expires_at, run_after, group_key, created_at)
                VALUES (:kind, CAST(:payload AS jsonb), :state, :priority, :attempts,
                        :max_attempts, :lease_owner, :lease_expires_at,
                        COALESCE(:run_after, now()), :group_key, clock_timestamp())
                RETURNING *
                """
            ),
            {
                "kind": kind,
                "payload": json.dumps(payload or {}),
                "state": state_value,
                "priority": priority,
                "attempts": attempts,
                "max_attempts": max_attempts,
                "lease_owner": lease_owner,
                "lease_expires_at": lease_expires_at,
                "run_after": run_after,
                "group_key": group_key,
            },
        )
        .mappings()
        .one()
    )
    return row_to_job(row)


def queue_for(engine: Engine, **overrides: Any) -> PgJobQueue:
    """Queue configured like ``.env.test`` (lease 5 s, 3 attempts, no backoff)."""
    params: dict[str, Any] = {"lease_seconds": 5, "max_attempts": 3, "retry_backoff_seconds": 0}
    params.update(overrides)
    return PgJobQueue(engine, **params)


# --------------------------------------------------------------------------- intake


def make_matter(engine: Engine, name: str = "Acme v. Beta", description: str | None = None) -> UUID:
    """Committed matter row (contract handles ``acme`` / ``beta`` / ``full``)."""
    with engine.begin() as conn:
        return conn.execute(  # type: ignore[no-any-return]
            text("INSERT INTO matter (name, description) VALUES (:n, :d) RETURNING id"),
            {"n": name, "d": description},
        ).scalar_one()


def make_register(
    engine: Engine, blob_root: Path, *, max_collections: int = 20
) -> tuple[RegisterCollection, FsBlobStore]:
    from chatledger_core.domain.intake.archive import ArchiveLimits

    store = FsBlobStore(blob_root)
    register = RegisterCollection(
        lambda: PgIntakeUnitOfWork(engine),
        store,
        ZipArchiveInspector(),
        ArchiveLimits(),
        max_collections,
    )
    return register, store


def stage_fixture(blob_root: Path, fixture: str, *, name: str | None = None) -> Path:
    """Copy a committed fixture into ``<blob_root>/tmp/`` as a staged file."""
    tmp = blob_root / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    target = tmp / (name or f"{uuid.uuid4().hex}.part")
    shutil.copyfile(FIXTURES_DIR / fixture, target)
    return target


def make_synthetic_collection(engine: Engine, matter_id: UUID, index: int) -> None:
    """Insert a blob + collection row directly (used to fill a matter to its cap)."""
    sha = f"{index:064x}"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO blob (sha256, size_bytes, storage_path) "
                "VALUES (:s, 10, :p) ON CONFLICT DO NOTHING"
            ),
            {"s": sha, "p": f"sha256/{sha[:2]}/{sha}.zip"},
        )
        conn.execute(
            text(
                "INSERT INTO collection (matter_id, blob_sha256, original_filename, size_bytes, "
                "source, entry_count, conversation_count, root_prefix) "
                "VALUES (:m, :s, :f, 10, 'upload', 2, 0, '')"
            ),
            {"m": matter_id, "s": sha, "f": f"filler-{index}.zip"},
        )


# --------------------------------------------------------------------------- generator


def make_generation_services(  # type: ignore[no-untyped-def]
    engine: Engine, blob_root: Path, *, max_collections: int = 20, **run_kwargs: Any
):
    """Real RunGeneration + repository + use cases wired like the composition roots."""
    from chatledger_core.infra.generator.disk import DiskProbe
    from chatledger_core.infra.generator.ground_truth_writer import GroundTruthWriter
    from chatledger_core.infra.generator.pg_generation_repository import PgGenerationRepository
    from chatledger_core.infra.generator.zip_export_writer import ZipExportWriter
    from chatledger_core.usecase.generator.generate_export import GenerateExport
    from chatledger_core.usecase.generator.request_generation import RequestGeneration
    from chatledger_core.usecase.generator.run_generation import RunGeneration

    register, store = make_register(engine, blob_root, max_collections=max_collections)
    repo = PgGenerationRepository(engine)
    probe = DiskProbe(run_kwargs.pop("free_space_override", None))
    run = RunGeneration(
        uow_factory=lambda: PgIntakeUnitOfWork(engine),
        generations=repo,
        register_collection=register,
        blob_store=store,
        generate_export=GenerateExport(probe),
        tmp_dir=store.tmp_dir,
        zip_sink_factory=ZipExportWriter,
        truth_sink_factory=GroundTruthWriter,
        **run_kwargs,
    )
    request = RequestGeneration(lambda: PgIntakeUnitOfWork(engine), repo, queue_for(engine))
    return run, request, repo, store
