"""Worker composition root: wires adapters, registry, heartbeat and signals."""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
from types import FrameType

from chatledger_core.config import Settings, get_settings
from chatledger_core.infra.db.engine import make_engine
from chatledger_core.infra.git_sha import resolve_git_sha
from chatledger_core.infra.heartbeat.pg_heartbeat import PgHeartbeat
from chatledger_core.infra.logging import bind_context, configure_logging, get_logger
from chatledger_core.infra.queue.pg_job_queue import PgJobQueue
from chatledger_worker.handlers import default_registry
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
        default_registry(),
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
