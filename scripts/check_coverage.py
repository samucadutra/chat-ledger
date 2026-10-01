"""Per-segment coverage gate.

Reads a coverage.py JSON report and aggregates covered/total statements per
gated path segment (``parsing``, ``model``, ``gates``). A file belongs to a
segment when one of its *directory components* equals the segment name, so
``model/`` matches but ``models/`` does not. Any segment with more than zero
statements and a coverage percentage below the threshold fails the gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

GATED_SEGMENTS: tuple[str, ...] = ("parsing", "model", "gates")
DEFAULT_THRESHOLD = 80.0


@dataclass(frozen=True)
class SegmentResult:
    segment: str
    statements: int
    covered: int

    @property
    def percent(self) -> float:
        if self.statements == 0:
            return 100.0
        return 100.0 * self.covered / self.statements

    def passes(self, threshold: float) -> bool:
        return self.statements == 0 or self.percent >= threshold


def _segments_of(path: str) -> tuple[str, ...]:
    return PurePosixPath(path.replace("\\", "/")).parent.parts


def aggregate(
    report: dict[str, Any], segments: tuple[str, ...] = GATED_SEGMENTS
) -> list[SegmentResult]:
    totals = {seg: [0, 0] for seg in segments}
    for path, data in report.get("files", {}).items():
        parts = _segments_of(path)
        summary = data.get("summary", {})
        for seg in segments:
            if seg in parts:
                totals[seg][0] += int(summary.get("num_statements", 0))
                totals[seg][1] += int(summary.get("covered_lines", 0))
    return [SegmentResult(seg, totals[seg][0], totals[seg][1]) for seg in segments]


def run(report_path: str, threshold: float) -> int:
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)
    failed = False
    for result in aggregate(report):
        if result.passes(threshold):
            print(
                f"Coverage gate: {result.segment} {result.percent:.1f}% "
                f"({result.covered}/{result.statements} statements) OK"
            )
        else:
            failed = True
            print(
                f"Coverage gate failed: {result.segment} {result.percent:.1f}% "
                f"< {threshold:.0f}% ({result.covered}/{result.statements} statements)"
            )
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", default="coverage.json")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args(argv)
    return run(args.report, args.threshold)


if __name__ == "__main__":
    sys.exit(main())
