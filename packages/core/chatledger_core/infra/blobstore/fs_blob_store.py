"""Filesystem blob store: ``<root>/sha256/<2 hex>/<hex>.zip``, read-only, content addressed."""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import uuid
from pathlib import Path

from chatledger_core.domain.intake.collection import BlobRef

_HASH_BLOCK = 8 * 1024 * 1024


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class FsBlobStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def tmp_dir(self) -> Path:
        return self._root / "tmp"

    def relative_path(self, sha256: str) -> str:
        return f"sha256/{sha256[:2]}/{sha256}.zip"

    def path_for(self, sha256: str) -> Path:
        return self._root / self.relative_path(sha256)

    def exists(self, sha256: str) -> bool:
        return self.path_for(sha256).is_file()

    def inspect_staged(self, staged_path: Path, sha256: str | None = None) -> tuple[str, int]:
        size = staged_path.stat().st_size
        if sha256 is not None:
            return sha256, size
        digest = hashlib.sha256()
        with staged_path.open("rb") as fh:
            while block := fh.read(_HASH_BLOCK):
                digest.update(block)
        return digest.hexdigest(), size

    def discard_staged(self, staged_path: Path) -> None:
        staged_path.unlink(missing_ok=True)

    def put_from_staging(self, staged_path: Path, sha256: str) -> BlobRef:
        size = staged_path.stat().st_size
        target = self.path_for(sha256)
        ref = BlobRef(sha256=sha256, size_bytes=size, storage_path=self.relative_path(sha256))
        if target.exists():
            if target.stat().st_size != size:
                raise OSError(f"stored blob {sha256} has unexpected size {target.stat().st_size}")
            staged_path.unlink(missing_ok=True)
            return ref
        target.parent.mkdir(parents=True, exist_ok=True)
        source = staged_path
        try:
            os.replace(source, target)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            # Staged on another filesystem: copy into our tmp dir, then rename atomically.
            self.tmp_dir.mkdir(parents=True, exist_ok=True)
            local = self.tmp_dir / f"{uuid.uuid4().hex}.copy"
            shutil.copyfile(source, local)
            os.replace(local, target)
            source.unlink(missing_ok=True)
        os.chmod(target, 0o444)
        fd = os.open(target, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(target.parent)
        return ref
