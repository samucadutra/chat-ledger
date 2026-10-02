"""Ground-truth sink: streams canonical chunks to a file while hashing them."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path


class GroundTruthWriter:
    def __init__(self, path: Path) -> None:
        self._path = path

    def write(self, chunks: Iterable[bytes]) -> tuple[str, int]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with self._path.open("wb") as fh:
            for chunk in chunks:
                digest.update(chunk)
                size += len(chunk)
                fh.write(chunk)
        return digest.hexdigest(), size
