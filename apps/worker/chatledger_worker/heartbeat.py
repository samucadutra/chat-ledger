"""Heartbeat thread: upserts ``worker_heartbeat`` every interval."""

from __future__ import annotations

import threading
from collections.abc import Callable
from uuid import UUID

from chatledger_core.infra.heartbeat.pg_heartbeat import PgHeartbeat
from chatledger_core.infra.logging import get_logger

_log = get_logger("chatledger_worker.heartbeat")


class HeartbeatThread(threading.Thread):
    def __init__(
        self,
        heartbeat: PgHeartbeat,
        *,
        worker_id: str,
        hostname: str,
        pid: int,
        git_sha: str,
        interval_seconds: float,
        current_job: Callable[[], UUID | None] = lambda: None,
    ) -> None:
        super().__init__(name="heartbeat", daemon=True)
        self._heartbeat = heartbeat
        self._worker_id = worker_id
        self._hostname = hostname
        self._pid = pid
        self._git_sha = git_sha
        self._interval = interval_seconds
        self._current_job = current_job
        self._stop_event = threading.Event()

    def beat_once(self) -> bool:
        try:
            self._heartbeat.beat(
                self._worker_id,
                hostname=self._hostname,
                pid=self._pid,
                git_sha=self._git_sha,
                current_job_id=self._current_job(),
            )
            return True
        except Exception as exc:  # keep beating through transient DB outages
            _log.warning("heartbeat.failed", error=str(exc))
            return False

    def run(self) -> None:
        while not self._stop_event.is_set():
            self.beat_once()
            self._stop_event.wait(self._interval)

    def stop(self, *, remove: bool = True) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=self._interval + 5)
        if remove:
            try:
                self._heartbeat.remove(self._worker_id)
            except Exception as exc:
                _log.warning("heartbeat.remove_failed", error=str(exc))
