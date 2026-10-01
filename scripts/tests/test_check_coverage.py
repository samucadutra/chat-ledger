import json
from pathlib import Path

import pytest

import check_coverage


def _report(files: dict[str, tuple[int, int]]) -> dict[str, object]:
    return {
        "files": {
            path: {"summary": {"num_statements": total, "covered_lines": covered}}
            for path, (total, covered) in files.items()
        }
    }


def _write(tmp_path: Path, files: dict[str, tuple[int, int]]) -> str:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(_report(files)))
    return str(path)


def test_passes_when_all_segments_at_or_above_80(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _write(
        tmp_path,
        {
            "packages/core/chatledger_core/parsing/a.py": (10, 8),
            "packages/core/chatledger_core/model/b.py": (10, 10),
            "packages/core/chatledger_core/gates/c.py": (5, 5),
        },
    )
    assert check_coverage.main([report]) == 0
    out = capsys.readouterr().out
    for seg in ("parsing", "model", "gates"):
        assert f"Coverage gate: {seg}" in out


def test_fails_naming_segment_below_80(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _write(
        tmp_path,
        {
            "packages/core/chatledger_core/parsing/a.py": (10, 5),
            "packages/core/chatledger_core/model/b.py": (10, 10),
        },
    )
    assert check_coverage.main([report]) == 1
    out = capsys.readouterr().out
    assert "Coverage gate failed: parsing 50.0% < 80%" in out
    assert "Coverage gate: model 100.0%" in out


def test_segment_with_zero_statements_passes(tmp_path: Path) -> None:
    report = _write(tmp_path, {"packages/core/chatledger_core/gates/__init__.py": (0, 0)})
    assert check_coverage.main([report]) == 0


def test_segment_matching_is_by_path_component_not_substring() -> None:
    results = {
        r.segment: r
        for r in check_coverage.aggregate(
            _report(
                {
                    "apps/x/models/a.py": (10, 0),
                    "apps/x/parsing_utils/b.py": (10, 0),
                    "apps/x/model/c.py": (4, 4),
                }
            )
        )
    }
    assert results["model"].statements == 4
    assert results["parsing"].statements == 0
    assert results["model"].percent == 100.0


def test_aggregates_across_layers(tmp_path: Path) -> None:
    results = check_coverage.aggregate(
        _report(
            {
                "packages/core/chatledger_core/domain/gates/a.py": (10, 10),
                "packages/core/chatledger_core/infra/gates/b.py": (10, 0),
            }
        )
    )
    gates = next(r for r in results if r.segment == "gates")
    assert gates.statements == 20
    assert gates.covered == 10
    assert not gates.passes(80.0)


def test_custom_threshold(tmp_path: Path) -> None:
    report = _write(tmp_path, {"a/parsing/x.py": (10, 5)})
    assert check_coverage.main([report, "--threshold", "50"]) == 0
