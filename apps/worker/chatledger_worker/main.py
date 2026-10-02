"""Worker composition root: wires adapters, registry, heartbeat and signals."""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
from types import FrameType

from sqlalchemy import Engine

from chatledger_core.config import Settings, get_settings
from chatledger_core.domain.intake.archive import ArchiveLimits
from chatledger_core.infra.blobstore.fs_blob_store import FsBlobStore
from chatledger_core.infra.db.engine import make_engine
from chatledger_core.infra.generator.disk import DiskProbe
from chatledger_core.infra.generator.ground_truth_writer import GroundTruthWriter
from chatledger_core.infra.generator.pg_generation_repository import PgGenerationRepository
from chatledger_core.infra.generator.zip_export_writer import ZipExportWriter
from chatledger_core.infra.git_sha import resolve_git_sha
from chatledger_core.infra.heartbeat.pg_heartbeat import PgHeartbeat
from chatledger_core.infra.intake.pg_unit_of_work import PgIntakeUnitOfWork
from chatledger_core.infra.intake.zip_archive_inspector import ZipArchiveInspector
from chatledger_core.infra.logging import bind_context, configure_logging, get_logger
from chatledger_core.infra.queue.pg_job_queue import PgJobQueue
from chatledger_core.usecase.generator.generate_export import GenerateExport
from chatledger_core.usecase.generator.run_generation import RunGeneration
from chatledger_core.usecase.intake.register_collection import RegisterCollection
from chatledger_worker.handlers import default_registry
from chatledger_worker.handlers.generate import KIND as GENERATE_KIND
from chatledger_worker.handlers.generate import make_generate_handler
from chatledger_worker.heartbeat import HeartbeatThread
from chatledger_worker.loop import JobLoop, LoopConfig


def worker_identity() -> tuple[str, str, int]:
    hostname = socket.gethostname()
    pid = os.getpid()
    return f"{hostname}-{pid}", hostname, pid


def build_queue(settings: Settings) -> PgJobQueue:
    return PgJobQueue(
        make_engine(settings.database_url),
        lease_seconds=settings.job_lease_seconds,
        max_attempts=settings.job_max_attempts,
        retry_backoff_seconds=settings.job_retry_backoff_seconds,
        stale_owner_seconds=settings.worker_active_window_seconds,
    )


def build_run_generation(settings: Settings, engine: Engine) -> RunGeneration:
    blob_store = FsBlobStore(settings.blob_root)

    def uow_factory() -> PgIntakeUnitOfWork:
        return PgIntakeUnitOfWork(engine)

    register = RegisterCollection(
        uow_factory,
        blob_store,
        ZipArchiveInspector(),
        ArchiveLimits(
            max_entries=settings.archive_max_entries,
            max_uncompressed_bytes=settings.archive_max_uncompressed_bytes,
            max_ratio=settings.archive_max_ratio,
            ratio_min_entry_bytes=settings.archive_ratio_min_entry_bytes,
        ),
        settings.max_collections_per_matter,
    )
    return RunGeneration(
        uow_factory=uow_factory,
        generations=PgGenerationRepository(engine),
        register_collection=register,
        blob_store=blob_store,
        generate_export=GenerateExport(
            DiskProbe(settings.generator_free_space_override_bytes),
            bytes_per_message=settings.generator_bytes_per_message,
            headroom=settings.generator_disk_headroom,
        ),
        tmp_dir=blob_store.tmp_dir,
        zip_sink_factory=ZipExportWriter,
        truth_sink_factory=GroundTruthWriter,
        progress_every=settings.generator_progress_every,
        fail_always=settings.generator_test_fail_always,
        pause_ms_per_conversation=settings.generator_test_delay_ms_per_conversation,
    )


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, service="worker")
    log = get_logger("chatledger_worker")
    worker_id, hostname, pid = worker_identity()
    git_sha = resolve_git_sha(settings.git_sha, settings.git_sha_file)
    bind_context(worker_id=worker_id, git_sha=git_sha)

    engine = make_engine(settings.database_url)
    queue = PgJobQueue(
        engine,
        lease_seconds=settings.job_lease_seconds,
        max_attempts=settings.job_max_attempts,
        retry_backoff_seconds=settings.job_retry_backoff_seconds,
        # Recover jobs of crashed workers once their heartbeat goes stale.
        stale_owner_seconds=settings.worker_active_window_seconds,
    )
    stop_event = threading.Event()
    loop = JobLoop(
        queue,
        default_registry(
            {GENERATE_KIND: make_generate_handler(build_run_generation(settings, engine))}
        ),
        worker_id=worker_id,
        config=LoopConfig(
            lease_renew_seconds=settings.job_lease_renew_seconds,
            sweep_interval_seconds=settings.job_sweep_interval_seconds,
            poll_interval_seconds=settings.job_poll_interval_seconds,
        ),
        stop_event=stop_event,
    )
    heartbeat = HeartbeatThread(
        PgHeartbeat(engine),
        worker_id=worker_id,
        hostname=hostname,
        pid=pid,
        git_sha=git_sha,
        interval_seconds=settings.heartbeat_interval_seconds,
        current_job=lambda: loop.current_job_id,
    )

    def _on_signal(signum: int, _frame: FrameType | None) -> None:
        log.info("worker.stop_requested", signal=signal.Signals(signum).name)
        stop_event.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    heartbeat.start()
    try:
        loop.run()
    finally:
        heartbeat.stop(remove=True)
        engine.dispose()
    log.info("worker.exit", code=0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
