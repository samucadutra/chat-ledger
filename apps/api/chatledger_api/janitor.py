"""Stale upload sweeper: deletes abandoned ``tmp/*.part`` files in a daemon thread."""

from __future__ import annotations

import threading
from pathlib import Path

from chatledger_core.infra.blobstore.staging import sweep_stale
from chatledger_core.infra.logging import get_logger

_log = get_logger("chatledger_api.janitor")


class Janitor:
    def __init__(self, tmp_dir: Path, interval_seconds: float, stale_seconds: float) -> None:
        self._tmp_dir = tmp_dir
        self._interval = interval_seconds
        self._stale = stale_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> int:
        try:
            removed = sweep_stale(self._tmp_dir, self._stale)
        except OSError:
            _log.warning("janitor.sweep_failed", tmp_dir=str(self._tmp_dir), exc_info=True)
            return 0
        if removed:
            _log.info("janitor.swept", removed=removed)
        return removed

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self.run_once()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="upload-janitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
