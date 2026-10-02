from __future__ import annotations

import os
import time
from pathlib import Path

from chatledger_api.janitor import Janitor


def touch(path: Path, age_seconds: float) -> None:
    path.write_bytes(b"x")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def test_sweeps_parts_older_than_threshold(tmp_path: Path) -> None:
    touch(tmp_path / "old.part", 700)
    assert Janitor(tmp_path, 60, 600).run_once() == 1
    assert list(tmp_path.iterdir()) == []


def test_keeps_recent_parts(tmp_path: Path) -> None:
    touch(tmp_path / "fresh.part", 5)
    assert Janitor(tmp_path, 60, 600).run_once() == 0
    assert (tmp_path / "fresh.part").exists()


def test_ignores_non_part_files(tmp_path: Path) -> None:
    touch(tmp_path / "old.txt", 9999)
    assert Janitor(tmp_path, 60, 600).run_once() == 0
    assert (tmp_path / "old.txt").exists()


def test_missing_dir_is_fine(tmp_path: Path) -> None:
    assert Janitor(tmp_path / "none", 60, 600).run_once() == 0


def test_background_thread_sweeps_and_stops(tmp_path: Path) -> None:
    touch(tmp_path / "old.part", 700)
    janitor = Janitor(tmp_path, 0.05, 600)
    janitor.start()
    janitor.start()  # idempotent
    deadline = time.time() + 3
    while (tmp_path / "old.part").exists() and time.time() < deadline:
        time.sleep(0.02)
    janitor.stop()
    assert not (tmp_path / "old.part").exists()
    janitor.stop()
