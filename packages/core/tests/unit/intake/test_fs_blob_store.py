from __future__ import annotations

import hashlib
import stat
from pathlib import Path

import pytest

from chatledger_core.infra.blobstore.fs_blob_store import FsBlobStore


def staged(root: Path, data: bytes, name: str = "a.part") -> tuple[Path, str]:
    tmp = root / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / name
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def test_layout_and_mode(tmp_path: Path) -> None:
    store = FsBlobStore(tmp_path)
    path, digest = staged(tmp_path, b"payload")
    ref = store.put_from_staging(path, digest)
    target = tmp_path / "sha256" / digest[:2] / f"{digest}.zip"
    assert store.path_for(digest) == target
    assert target.read_bytes() == b"payload"
    assert stat.S_IMODE(target.stat().st_mode) == 0o444
    assert ref.storage_path == f"sha256/{digest[:2]}/{digest}.zip"
    assert ref.size_bytes == 7
    assert not path.exists()
    assert store.exists(digest)
    assert store.tmp_dir == tmp_path / "tmp"


def test_put_is_idempotent_and_discards_staging(tmp_path: Path) -> None:
    store = FsBlobStore(tmp_path)
    first, digest = staged(tmp_path, b"payload", "a.part")
    store.put_from_staging(first, digest)
    second, _ = staged(tmp_path, b"payload", "b.part")
    ref = store.put_from_staging(second, digest)
    assert not second.exists()
    assert ref.size_bytes == 7
    assert len(list((tmp_path / "sha256").rglob("*.zip"))) == 1


def test_size_mismatch_with_existing_blob_raises(tmp_path: Path) -> None:
    store = FsBlobStore(tmp_path)
    first, digest = staged(tmp_path, b"payload", "a.part")
    store.put_from_staging(first, digest)
    other, _ = staged(tmp_path, b"different-length", "b.part")
    with pytest.raises(OSError, match="unexpected size"):
        store.put_from_staging(other, digest)


def test_inspect_staged_hashes_or_trusts(tmp_path: Path) -> None:
    store = FsBlobStore(tmp_path)
    path, digest = staged(tmp_path, b"hello")
    assert store.inspect_staged(path) == (digest, 5)
    assert store.inspect_staged(path, "f" * 64) == ("f" * 64, 5)


def test_discard_staged_tolerates_missing(tmp_path: Path) -> None:
    store = FsBlobStore(tmp_path)
    path, _ = staged(tmp_path, b"x")
    store.discard_staged(path)
    store.discard_staged(path)
    assert not path.exists()


def test_exists_false_for_unknown(tmp_path: Path) -> None:
    assert not FsBlobStore(tmp_path).exists("0" * 64)


def test_put_from_other_filesystem_falls_back_to_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import errno
    import os

    store = FsBlobStore(tmp_path / "root")
    path, digest = staged(tmp_path / "elsewhere", b"cross-device")
    real_replace = os.replace
    calls: list[Path] = []

    def fake_replace(src: str | Path, dst: str | Path) -> None:
        calls.append(Path(src))
        if Path(src) == path:
            raise OSError(errno.EXDEV, "cross-device")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fake_replace)
    store.put_from_staging(path, digest)
    assert store.path_for(digest).read_bytes() == b"cross-device"
    assert not path.exists()
    assert len(calls) == 2


def test_other_os_errors_propagate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import errno
    import os

    store = FsBlobStore(tmp_path)
    path, digest = staged(tmp_path, b"x")

    def boom(src: str | Path, dst: str | Path) -> None:
        raise OSError(errno.EACCES, "denied")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="denied"):
        store.put_from_staging(path, digest)
