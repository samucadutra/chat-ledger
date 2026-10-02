"""Deterministic ZIP sink: fixed timestamps and permissions, caller-ordered entries."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import BinaryIO

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_ATTR = 0o644 << 16
COMPRESS_LEVEL = 6


class _HashingWriter:
    """Write-only, non-seekable file wrapper that hashes every byte it forwards."""

    def __init__(self, fh: BinaryIO) -> None:
        self._fh = fh
        self.sha = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes | bytearray | memoryview) -> int:
        self.sha.update(data)
        self.size += len(data)
        return self._fh.write(data)

    def tell(self) -> int:
        return self.size

    def flush(self) -> None:
        self._fh.flush()


class ZipExportWriter:
    """Streams entries into ``path``; the file is created on the first entry (or on close)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fh: BinaryIO | None = None
        self._hash: _HashingWriter | None = None
        self._zip: zipfile.ZipFile | None = None

    def _open(self) -> zipfile.ZipFile:
        if self._zip is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self._path.open("wb")
            self._hash = _HashingWriter(self._fh)
            self._zip = zipfile.ZipFile(
                self._hash,  # type: ignore[call-overload]
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=COMPRESS_LEVEL,
            )
        return self._zip

    def add_entry(self, path: str, data: bytes) -> None:
        info = zipfile.ZipInfo(path, date_time=FIXED_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = FIXED_ATTR
        info.create_system = 3
        self._open().writestr(
            info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=COMPRESS_LEVEL
        )

    def close(self) -> tuple[str, int]:
        archive = self._open()
        archive.close()
        assert self._fh is not None
        assert self._hash is not None
        self._fh.flush()
        self._fh.close()
        self._fh = None
        self._zip = None
        return self._hash.sha.hexdigest(), self._hash.size

    def abort(self) -> None:
        """Release handles without finishing the archive (the caller removes the file)."""
        if self._zip is not None:
            self._zip.fp = None  # ZipFile.close() then does nothing
            self._zip = None
        if self._fh is not None:
            self._fh.close()
            self._fh = None
