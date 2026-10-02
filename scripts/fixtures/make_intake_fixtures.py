"""Deterministic generator for the F02 intake fixtures (spec A12, fixed seed 20261001).

``--small``  rebuilds the committed ZIPs in ``tests/fixtures/intake/``.
``--large``  writes the large, gitignored files in ``tests/fixtures/intake/generated/``.

Every ZIP is byte-stable: entries are written in sorted order with a fixed timestamp.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import zipfile
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

SEED = 20261001
FIXED_TIME = (2024, 1, 1, 0, 0, 0)
ROOT = Path(__file__).resolve().parents[2]
SMALL_DIR = ROOT / "tests" / "fixtures" / "intake"
LARGE_DIR = SMALL_DIR / "generated"

LARGE_PADDING_BYTES = 1_610_612_736  # 1.5 GiB of stored random data
OVERSIZE_BYTES = 2_147_483_649  # 2 GiB + 1
MANY_ENTRIES = 200_001
BOMB_PADDING_BYTES = 52_428_800
BLOCK = 8 * 1024 * 1024

Entries = dict[str, bytes]


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, indent=1).encode() + b"\n"


def _messages(rng: random.Random, day: date, count: int = 3) -> bytes:
    stamp = (day - date(1970, 1, 1)).days * 86400 + 9 * 3600
    return _json(
        [
            {
                "type": "message",
                "user": f"U{rng.randint(1, 2):03d}",
                "text": f"message {i} on {day.isoformat()}",
                "ts": f"{stamp + i * 60}.{i:06d}",
            }
            for i in range(count)
        ]
    )


def _users() -> bytes:
    return _json(
        [
            {"id": "U001", "name": "alice", "real_name": "Alice Example"},
            {"id": "U002", "name": "bob", "real_name": "Bob Example"},
        ]
    )


def _channels(names: Iterable[str]) -> bytes:
    return _json([{"id": f"C{i:03d}", "name": n} for i, n in enumerate(names, start=1)])


def minimal_entries() -> Entries:
    rng = random.Random(SEED)
    entries: Entries = {"users.json": _users(), "channels.json": _channels(["general", "random"])}
    for folder in ("general", "random"):
        for day in (date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)):
            entries[f"{folder}/{day.isoformat()}.json"] = _messages(rng, day)
    return entries


def export_50conv_entries() -> Entries:
    rng = random.Random(SEED + 1)
    names = [f"channel-{i:02d}" for i in range(50)]
    entries: Entries = {"users.json": _users(), "channels.json": _channels(names)}
    first, last = date(2024, 1, 3), date(2024, 4, 1)
    span = (last - first).days
    for i, name in enumerate(names):
        days = {first + timedelta(days=rng.randint(0, span)) for _ in range(3)}
        if i == 0:
            days.add(first)
        if i == 49:
            days.add(last)
        for day in sorted(days):
            entries[f"{name}/{day.isoformat()}.json"] = _messages(rng, day, 2)
    return entries


def prefixed(entries: Entries, prefix: str) -> Entries:
    return {f"{prefix}{name}": data for name, data in entries.items()}


def build_zip(entries: Entries, *, compress: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = compress
            info.external_attr = 0o644 << 16
            zf.writestr(info, entries[name])
    return buf.getvalue()


def small_fixtures() -> dict[str, bytes]:
    minimal = minimal_entries()
    missing_users = {
        "channels.json": _channels(["general"]),
        "general/2024-01-03.json": minimal["general/2024-01-03.json"],
    }
    path_traversal = {**minimal, "../evil.json": b"{}\n"}
    bomb = {**minimal, "padding.bin": bytes(BOMB_PADDING_BYTES)}
    junk = random.Random(SEED + 2).randbytes(1016)
    return {
        "minimal-export.zip": build_zip(minimal),
        "export-50conv-90d.zip": build_zip(export_50conv_entries()),
        "nested-export.zip": build_zip(prefixed(minimal, "Acme Slack export Jan 2024/")),
        "missing-users.zip": build_zip(missing_users),
        "path-traversal.zip": build_zip(path_traversal),
        "zip-bomb.zip": build_zip(bomb),
        "not-a-zip.zip": b"NOTAZIP\n" + junk.replace(b"PK", b"pk"),
    }


def write_small(out_dir: Path = SMALL_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in small_fixtures().items():
        path = out_dir / name
        path.write_bytes(data)
        written.append(path)
    return written


def write_large_export(path: Path, padding_bytes: int = LARGE_PADDING_BYTES) -> None:
    """A valid export plus a stored (uncompressed) random ``padding.bin``."""
    rng = random.Random(SEED + 3)
    with zipfile.ZipFile(path, "w") as zf:
        entries = minimal_entries()
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, entries[name])
        pad = zipfile.ZipInfo("padding.bin", date_time=FIXED_TIME)
        pad.compress_type = zipfile.ZIP_STORED
        pad.external_attr = 0o644 << 16
        with zf.open(pad, "w", force_zip64=True) as dest:
            remaining = padding_bytes
            while remaining > 0:
                block = min(BLOCK, remaining)
                dest.write(rng.randbytes(block))
                remaining -= block


def write_oversize(path: Path, size: int = OVERSIZE_BYTES) -> None:
    """A sparse file of exactly ``size`` bytes (content is irrelevant: it is refused by size)."""
    with path.open("wb") as fh:
        fh.truncate(size)


def write_many_entries(path: Path, total: int = MANY_ENTRIES) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        names = ["channels.json", "users.json"] + [f"bulk/e{i:06d}.json" for i in range(total - 2)]
        for name in sorted(names):
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, b"[]\n")


def write_large(out_dir: Path = LARGE_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "large-export-1_5gb.zip": write_large_export,
        "oversize-2gb-plus-1.zip": write_oversize,
        "many-entries-200001.zip": write_many_entries,
    }
    written = []
    for name, writer in targets.items():
        path = out_dir / name
        writer(path)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--small", action="store_true", help="rebuild the committed fixtures")
    parser.add_argument("--large", action="store_true", help="write the generated large fixtures")
    args = parser.parse_args(argv)
    if not (args.small or args.large):
        parser.error("pass --small and/or --large")
    if args.small:
        for path in write_small():
            print(path.relative_to(ROOT))
    if args.large:
        for path in write_large():
            print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
