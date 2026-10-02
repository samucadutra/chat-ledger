from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from chatledger_core.domain.generator.ground_truth import (
    GroundTruthMeta,
    Overlap,
    build_document,
    canonical_chunks,
    sort_key,
)
from chatledger_core.domain.generator.overlap import build_overlap, window_day_count
from chatledger_core.domain.generator.params import validate_params
from chatledger_core.infra.generator.disk import DiskProbe
from chatledger_core.infra.generator.ground_truth_writer import GroundTruthWriter
from chatledger_core.infra.generator.zip_export_writer import ZipExportWriter
from chatledger_core.usecase.generator.generate_export import GenerateExport, OverlapSpec


def _generate(tmp_path: Path, seed: int, tag: str, overlap: OverlapSpec | None = None, **kw):  # type: ignore[no-untyped-def]
    params = validate_params(
        seed=seed,
        preset=kw.pop("preset", "small"),
        profile=kw.pop("profile", "default"),
        **kw,
    )
    result = GenerateExport(DiskProbe()).execute(
        params,
        zip_sink=ZipExportWriter(tmp_path / f"{tag}.zip"),
        ground_truth_sink=GroundTruthWriter(tmp_path / f"{tag}.json"),
        disk_path=str(tmp_path),
        overlap=overlap,
    )
    return (
        result,
        zipfile.ZipFile(tmp_path / f"{tag}.zip"),
        json.loads((tmp_path / f"{tag}.json").read_text()),
    )


def test_window_days() -> None:
    assert window_day_count(90, 30) == 27
    assert window_day_count(90, 50) == 45
    assert window_day_count(90, 1) == 1
    params = validate_params(seed=43, preset="small", profile="default")
    assert build_overlap(params, 42, 30).total_days == 57
    assert build_overlap(params, 42, 50).total_days == 75


def test_redelivery_shares_workspace_and_window_bytes(tmp_path: Path) -> None:
    _, base, _ = _generate(tmp_path, 42, "base")
    result, redelivery, truth = _generate(tmp_path, 43, "redel", OverlapSpec(42, 30))
    base_names = set(base.namelist())
    shared = [n for n in redelivery.namelist() if n in base_names and "/" in n]
    assert shared
    assert all(base.read(n) == redelivery.read(n) for n in shared)
    for root in ("users.json", "channels.json", "groups.json", "dms.json", "mpims.json"):
        assert base.read(root) == redelivery.read(root)
    dates = sorted({n.split("/")[1][:10] for n in redelivery.namelist() if "/" in n})
    assert (dates[0], dates[-1], len(dates)) == ("2025-12-05", "2026-01-30", 57)
    base_dates = {n.split("/")[1][:10] for n in base_names if "/" in n}
    new_days = [d for d in dates if d > "2025-12-31"]
    assert len(new_days) == 30 and not set(new_days) & base_dates
    assert truth["overlap"] == {"base_seed": 42, "days_pct": 30}
    assert truth["seed"] == 43 and result.message_records == truth["totals"]["message_records"]


def test_duplicate_source_entries_cover_every_window_record(tmp_path: Path) -> None:
    _, base, _ = _generate(tmp_path, 42, "base")
    _, redelivery, truth = _generate(tmp_path, 43, "redel", OverlapSpec(42, 30))
    duplicates = [a for a in truth["anomalies"] if a["anomaly_type"] == "duplicate_source"]
    assert all(a["expected_reason_code"] == "X_DUPLICATE_SOURCE" for a in duplicates)
    in_window = 0
    for name in redelivery.namelist():
        if "/" not in name or name.split("/")[1][:10] > "2025-12-31" or name not in base.namelist():
            continue
        if name.split("/")[1][:10] < "2025-12-05":
            continue
        try:
            in_window += len(json.loads(redelivery.read(name)))
        except json.JSONDecodeError:
            in_window += 0
    listed = {(a["source_file"], a["record_index"]) for a in duplicates}
    assert len(listed) == len(duplicates)
    assert in_window <= len(duplicates)  # truncated files add their complete records only
    sample = duplicates[0]
    record = json.loads(redelivery.read(sample["source_file"]))[sample["record_index"]]
    assert record.get("ts") == sample["message_ts"]


def test_percentage_widens_window(tmp_path: Path) -> None:
    _, redelivery, _ = _generate(tmp_path, 43, "r50", OverlapSpec(42, 50))
    dates = sorted({n.split("/")[1][:10] for n in redelivery.namelist() if "/" in n})
    assert len(dates) == 75


def test_ground_truth_document_is_canonical_and_sorted() -> None:
    meta = GroundTruthMeta("1.0.0", 42, "small", "default", 10_000, 50, 10_000)
    anomalies = [
        ("edit", "C2", "1.1", "a/x.json", 3),
        ("empty_file", "C1", None, "a/y.json", None),
        ("edit", "C1", "1.0", "a/x.json", 1),
        ("delete", "C1", "1.0", "a/x.json", 2),
    ]
    document = build_document(meta, anomalies)
    assert document.endswith(b"\n")
    parsed = json.loads(document)
    assert document == json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    keys = [(a["conversation_id"], a["message_ts"], a["anomaly_type"]) for a in parsed["anomalies"]]
    assert keys == [
        ("C1", None, "empty_file"),
        ("C1", "1.0", "delete"),
        ("C1", "1.0", "edit"),
        ("C2", "1.1", "edit"),
    ]
    assert parsed["totals"]["anomalies_by_type"] == {"delete": 1, "edit": 2, "empty_file": 1}
    assert parsed["totals"]["message_records"] == 10_000
    assert parsed["overlap"] is None
    assert sorted(anomalies, key=sort_key)[0][0] == "empty_file"


def test_empty_and_overlap_documents() -> None:
    meta = GroundTruthMeta("1.0.0", 1, "small", "clean", 10_000, 50, 10_000, Overlap(7, 30))
    parsed = json.loads(b"".join(canonical_chunks(meta, [])))
    assert parsed["anomalies"] == [] and parsed["totals"]["anomalies"] == 0
    assert parsed["overlap"] == {"base_seed": 7, "days_pct": 30}


def test_pipeline_surfaces_progress_and_abort(tmp_path: Path) -> None:
    from chatledger_core.usecase.generator.generate_export import GenerationAborted

    params = validate_params(
        seed=5, preset="custom", profile="clean", messages=3_000, conversations=10
    )
    seen: list[int] = []
    GenerateExport(DiskProbe()).execute(
        params,
        zip_sink=ZipExportWriter(tmp_path / "p.zip"),
        ground_truth_sink=GroundTruthWriter(tmp_path / "p.json"),
        disk_path=str(tmp_path),
        on_progress=seen.append,
    )
    assert seen == sorted(seen) and seen[-1] == 3_000
    with pytest.raises(GenerationAborted):
        GenerateExport(DiskProbe()).execute(
            params,
            zip_sink=ZipExportWriter(tmp_path / "q.zip"),
            ground_truth_sink=GroundTruthWriter(tmp_path / "q.json"),
            disk_path=str(tmp_path),
            should_abort=lambda: True,
        )
