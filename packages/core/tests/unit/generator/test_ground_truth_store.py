from __future__ import annotations

import stat
from pathlib import Path

from chatledger_core.infra.blobstore.fs_blob_store import FsBlobStore

DIGEST = "ab" + "0" * 62


def test_put_is_idempotent_read_only_and_beside_the_blob(tmp_path: Path) -> None:
    store = FsBlobStore(tmp_path)
    staged = tmp_path / "tmp" / "gt.part"
    staged.parent.mkdir()
    staged.write_text("one")
    target = store.put_ground_truth(DIGEST, staged)
    assert target == store.path_for(DIGEST).with_name(f"{DIGEST}.ground-truth.json")
    assert target.read_text() == "one"
    assert stat.S_IMODE(target.stat().st_mode) == 0o444
    assert not staged.exists()
    again = tmp_path / "tmp" / "gt2.part"
    again.write_text("two")
    assert store.put_ground_truth(DIGEST, again) == target
    assert target.read_text() == "one"
    assert not again.exists()


def test_remove_only_when_no_blob(tmp_path: Path) -> None:
    store = FsBlobStore(tmp_path)
    staged = tmp_path / "gt.part"
    staged.write_text("x")
    target = store.put_ground_truth(DIGEST, staged)
    store.path_for(DIGEST).write_bytes(b"zip")
    assert store.remove_ground_truth_if_unreferenced(DIGEST) is False
    assert target.exists()
    store.path_for(DIGEST).unlink()
    assert store.remove_ground_truth_if_unreferenced(DIGEST) is True
    assert not target.exists()
    assert store.remove_ground_truth_if_unreferenced(DIGEST) is False
