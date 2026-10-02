from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tracemalloc
import zipfile
from pathlib import Path

import pytest

from chatledger_core.domain.generator.errors import InsufficientDiskSpaceError
from chatledger_core.domain.generator.params import validate_params
from chatledger_core.domain.intake.archive import ArchiveLimits, inspect_entries
from chatledger_core.infra.generator.disk import DiskProbe
from chatledger_core.infra.generator.ground_truth_writer import GroundTruthWriter
from chatledger_core.infra.generator.zip_export_writer import ZipExportWriter
from chatledger_core.infra.intake.zip_archive_inspector import ZipArchiveInspector
from chatledger_core.usecase.generator.generate_export import GenerateExport

SCRIPT = """
import hashlib, sys, pathlib
from chatledger_core.domain.generator.params import validate_params
from chatledger_core.infra.generator.disk import DiskProbe
from chatledger_core.infra.generator.ground_truth_writer import GroundTruthWriter
from chatledger_core.infra.generator.zip_export_writer import ZipExportWriter
from chatledger_core.usecase.generator.generate_export import GenerateExport
out = pathlib.Path(sys.argv[1])
p = validate_params(seed=42, preset="small", profile="default")
r = GenerateExport(DiskProbe()).execute(
    p, zip_sink=ZipExportWriter(out / "z.zip"), ground_truth_sink=GroundTruthWriter(out / "g.json"),
    disk_path=str(out))
print(r.zip_sha256, r.ground_truth_sha256)
"""


def run(tmp_path: Path, seed: int = 42, tag: str = "a", **params: object):  # type: ignore[no-untyped-def]
    p = validate_params(
        seed=seed,
        preset=params.pop("preset", "small"),
        profile=params.pop("profile", "default"),
        **params,  # type: ignore[arg-type]
    )
    result = GenerateExport(DiskProbe()).execute(
        p,
        zip_sink=ZipExportWriter(tmp_path / f"{tag}.zip"),
        ground_truth_sink=GroundTruthWriter(tmp_path / f"{tag}.json"),
        disk_path=str(tmp_path),
    )
    return result, tmp_path / f"{tag}.zip", tmp_path / f"{tag}.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_zip_sorted_fixed_metadata(tmp_path: Path) -> None:
    result, zip_path, _ = run(tmp_path)
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        assert names == sorted(names)
        assert {i.date_time for i in infos} == {(1980, 1, 1, 0, 0, 0)}
        assert len({i.external_attr for i in infos}) == 1
        assert len({i.create_system for i in infos}) == 1
        assert archive.testzip() is None
    assert result.zip_sha256 == sha(zip_path)
    assert result.zip_size == zip_path.stat().st_size


def test_hashes_match_files_on_disk(tmp_path: Path) -> None:
    result, _zip_path, gt_path = run(tmp_path)
    assert result.ground_truth_sha256 == sha(gt_path)
    assert result.ground_truth_size == gt_path.stat().st_size


def test_same_seed_same_bytes_and_other_seed_differs(tmp_path: Path) -> None:
    a, za, ga = run(tmp_path, tag="a")
    b, zb, gb = run(tmp_path, tag="b")
    c, _zc, _gc = run(tmp_path, seed=43, tag="c")
    assert a.zip_sha256 == b.zip_sha256 and a.ground_truth_sha256 == b.ground_truth_sha256
    assert sha(za) == sha(zb) and sha(ga) == sha(gb)
    assert c.zip_sha256 != a.zip_sha256 and c.ground_truth_sha256 != a.ground_truth_sha256


def test_output_does_not_depend_on_environment(tmp_path: Path) -> None:
    results = []
    for tz, hashseed, cwd in (("UTC", "0", tmp_path), ("Asia/Tokyo", "7", Path("/"))):
        out = tmp_path / tz.replace("/", "_")
        out.mkdir()
        env = {**os.environ, "TZ": tz, "PYTHONHASHSEED": hashseed, "LANG": "pt_BR.UTF-8"}
        proc = subprocess.run(
            [sys.executable, "-c", SCRIPT, str(out)],
            env=env,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        results.append(proc.stdout.strip())
    assert results[0] == results[1]


def test_zip_passes_f02_inspection(tmp_path: Path) -> None:
    _, zip_path, _ = run(tmp_path)
    metadata = inspect_entries(ZipArchiveInspector().read_entries(zip_path), ArchiveLimits())
    assert metadata.conversation_count == 50
    assert metadata.root_prefix == ""
    assert (metadata.export_date_to - metadata.export_date_from).days + 1 == 90  # type: ignore[operator]


def test_disk_space_check(tmp_path: Path) -> None:
    params = validate_params(seed=42, preset="small", profile="default")
    usecase = GenerateExport(DiskProbe(override_bytes=1_000_000))
    with pytest.raises(InsufficientDiskSpaceError) as exc:
        usecase.execute(
            params,
            zip_sink=ZipExportWriter(tmp_path / "x.zip"),
            ground_truth_sink=GroundTruthWriter(tmp_path / "x.json"),
            disk_path=str(tmp_path),
        )
    assert exc.value.message == "Not enough disk space: need ~0.0 GB, 0.0 GB free."
    assert exc.value.code == "INSUFFICIENT_DISK_SPACE"
    assert not (tmp_path / "x.json").exists()
    big = validate_params(seed=1, preset="large", profile="clean")
    with pytest.raises(InsufficientDiskSpaceError) as exc2:
        usecase.check_disk(big.messages, str(tmp_path))
    assert exc2.value.message.startswith("Not enough disk space: need ~0.5 GB, 0.0 GB free")


def test_disk_probe_uses_nearest_existing_parent(tmp_path: Path) -> None:
    assert DiskProbe().free_bytes(str(tmp_path / "missing" / "deeper")) > 0


def test_memory_bound_streaming(tmp_path: Path) -> None:
    tracemalloc.start()
    run(tmp_path, preset="custom", profile="default", messages=100_000, conversations=200)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 80 * 1024 * 1024
