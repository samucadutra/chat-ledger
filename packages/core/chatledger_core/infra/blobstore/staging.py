"""Streaming upload staging: hash while writing, bounded size, stale-file sweep."""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from chatledger_core.domain.intake.errors import FileTooLargeError

PART_SUFFIX = ".part"


@dataclass(frozen=True)
class StagedFile:
    path: Path
    sha256: str
    size: int


class StagingWriter:
    """Writes an upload to ``<tmp_dir>/<uuid>.part`` while computing its SHA-256.

    Incoming data is coalesced into writes of at least ``chunk_bytes``. Writing more
    than ``max_bytes`` raises :class:`FileTooLargeError` and discards the file.
    """

    def __init__(self, tmp_dir: Path, max_bytes: int, chunk_bytes: int) -> None:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        self.path = tmp_dir / f"{uuid.uuid4().hex}{PART_SUFFIX}"
        self._max_bytes = max_bytes
        self._chunk_bytes = chunk_bytes
        self._hash = hashlib.sha256()
        self._size = 0
        self._buffer = bytearray()
        self._fh: BinaryIO | None = self.path.open("wb")

    @property
    def size(self) -> int:
        return self._size

    def write(self, chunk: bytes | bytearray | memoryview) -> None:
        if self._fh is None:
            raise ValueError("staging writer is closed")
        self._size += len(chunk)
        if self._size > self._max_bytes:
            self.discard()
            raise FileTooLargeError(self._max_bytes)
        self._buffer += chunk
        if len(self._buffer) >= self._chunk_bytes:
            self._flush()

    def _flush(self) -> None:
        if self._fh is None or not self._buffer:
            return
        self._hash.update(self._buffer)
        self._fh.write(self._buffer)
        self._buffer.clear()

    def finish(self) -> StagedFile:
        if self._fh is None:
            raise ValueError("staging writer is closed")
        self._flush()
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._fh.close()
        self._fh = None
        return StagedFile(self.path, self._hash.hexdigest(), self._size)

    def discard(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        self._buffer.clear()
        self.path.unlink(missing_ok=True)


def sweep_stale(tmp_dir: Path, older_than_seconds: float, *, now: float | None = None) -> int:
    """Delete ``*.part`` files whose mtime is older than the threshold; return the count."""
    if not tmp_dir.is_dir():
        return 0
    cutoff = (time.time() if now is None else now) - older_than_seconds
    removed = 0
    for entry in tmp_dir.iterdir():
        if entry.suffix != PART_SUFFIX or not entry.is_file():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except FileNotFoundError:
            continue
    return removed
