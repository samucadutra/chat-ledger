from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest

from chatledger_core.domain.intake.errors import FileTooLargeError
from chatledger_core.infra.blobstore.staging import StagingWriter, sweep_stale


def test_streams_and_hashes(tmp_path: Path) -> None:
    writer = StagingWriter(tmp_path / "tmp", max_bytes=1000, chunk_bytes=4)
    for part in (b"ab", b"cdef", b"g"):
        writer.write(part)
    staged = writer.finish()
    assert staged.path.read_bytes() == b"abcdefg"
    assert staged.size == 7
    assert staged.sha256 == hashlib.sha256(b"abcdefg").hexdigest()
    assert staged.path.suffix == ".part"
    assert staged.path.parent == tmp_path / "tmp"


def test_empty_upload(tmp_path: Path) -> None:
    staged = StagingWriter(tmp_path, 10, 4).finish()
    assert staged.size == 0
    assert staged.sha256 == hashlib.sha256(b"").hexdigest()


def test_exactly_at_limit_ok_one_over_rejected(tmp_path: Path) -> None:
    ok = StagingWriter(tmp_path, 5, 2)
    ok.write(b"12345")
    assert ok.finish().size == 5
    over = StagingWriter(tmp_path, 5, 2)
    over.write(b"12345")
    with pytest.raises(FileTooLargeError) as info:
        over.write(b"6")
    assert info.value.code == "FILE_TOO_LARGE"
    assert info.value.http_status == 413
    assert not over.path.exists()


def test_discard_removes_file(tmp_path: Path) -> None:
    writer = StagingWriter(tmp_path, 100, 4)
    writer.write(b"abcdefgh")
    writer.discard()
    assert list(tmp_path.iterdir()) == []
    writer.discard()  # idempotent


def test_write_after_close_raises(tmp_path: Path) -> None:
    writer = StagingWriter(tmp_path, 100, 4)
    writer.finish()
    with pytest.raises(ValueError, match="closed"):
        writer.write(b"x")
    with pytest.raises(ValueError, match="closed"):
        writer.finish()


def test_sweep_stale_removes_old_parts_only(tmp_path: Path) -> None:
    old = tmp_path / "old.part"
    new = tmp_path / "new.part"
    other = tmp_path / "keep.txt"
    for p in (old, new, other):
        p.write_bytes(b"x")
    ancient = time.time() - 3600
    os.utime(old, (ancient, ancient))
    os.utime(other, (ancient, ancient))
    assert sweep_stale(tmp_path, 600) == 1
    assert not old.exists()
    assert new.exists()
    assert other.exists()


def test_sweep_stale_missing_dir(tmp_path: Path) -> None:
    assert sweep_stale(tmp_path / "nope", 1) == 0
