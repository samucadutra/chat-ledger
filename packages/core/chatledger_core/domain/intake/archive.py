"""Pure archive inspection: safety rules, Slack export markers and metadata (spec A4-A7)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from chatledger_core.domain.intake.errors import ArchiveRejectedError, NotASlackExportError


class ArchiveRule(StrEnum):
    NOT_A_ZIP = "not_a_zip"
    PATH_ESCAPE = "path_escape"
    ENTRY_COUNT = "entry_count"
    UNCOMPRESSED_SIZE = "uncompressed_size"
    COMPRESSION_RATIO = "compression_ratio"


RULE_TEXT: dict[ArchiveRule, str] = {
    ArchiveRule.NOT_A_ZIP: "file is not a valid ZIP archive",
    ArchiveRule.PATH_ESCAPE: "entry path escapes archive",
    ArchiveRule.ENTRY_COUNT: "more than 200,000 entries",
    ArchiveRule.UNCOMPRESSED_SIZE: "uncompressed size above 20 GB",
    ArchiveRule.COMPRESSION_RATIO: "compression ratio above 100:1",
}


def rejected(rule: ArchiveRule) -> ArchiveRejectedError:
    return ArchiveRejectedError(rule.value, RULE_TEXT[rule])


@dataclass(frozen=True)
class ArchiveEntry:
    name: str
    file_size: int
    compress_size: int
    is_dir: bool = False


@dataclass(frozen=True)
class ArchiveLimits:
    max_entries: int = 200_000
    max_uncompressed_bytes: int = 21_474_836_480
    max_ratio: int = 100
    ratio_min_entry_bytes: int = 1_048_576


@dataclass(frozen=True)
class ArchiveMetadata:
    entry_count: int
    conversation_count: int
    export_date_from: date | None
    export_date_to: date | None
    root_prefix: str


_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")
_DAY_FILE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.json$")
_USERS = "users.json"
_CHANNELS = "channels.json"


def _normalise(name: str) -> str:
    return name.replace("\\", "/")


def _is_ignored(name: str) -> bool:
    parts = name.split("/")
    return parts[0] == "__MACOSX" or parts[-1] == ".DS_Store"


def _is_unsafe(name: str) -> bool:
    return name.startswith("/") or bool(_DRIVE_LETTER.match(name)) or ".." in name.split("/")


def _parse_day(filename: str) -> date | None:
    match = _DAY_FILE.match(filename)
    if match is None:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _find_root_prefix(files: set[str]) -> str | None:
    if _USERS in files and _CHANNELS in files:
        return ""
    candidates: set[str] = set()
    for name in files:
        parts = name.split("/")
        if len(parts) == 2 and parts[1] == _USERS and f"{parts[0]}/{_CHANNELS}" in files:
            candidates.add(f"{parts[0]}/")
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def inspect_entries(entries: list[ArchiveEntry], limits: ArchiveLimits) -> ArchiveMetadata:
    """Apply the ordered rules (first failure wins) and derive collection metadata.

    Order: path safety, entry count, total uncompressed size, compression ratio,
    Slack markers. "Valid ZIP" is checked by the adapter that produced ``entries``.
    """
    normalised = [(_normalise(e.name), e) for e in entries]

    if any(_is_unsafe(name) for name, _ in normalised):
        raise rejected(ArchiveRule.PATH_ESCAPE)
    if len(normalised) > limits.max_entries:
        raise rejected(ArchiveRule.ENTRY_COUNT)
    if sum(e.file_size for _, e in normalised) > limits.max_uncompressed_bytes:
        raise rejected(ArchiveRule.UNCOMPRESSED_SIZE)
    for _, entry in normalised:
        if (
            entry.file_size > limits.ratio_min_entry_bytes
            and entry.file_size / max(entry.compress_size, 1) > limits.max_ratio
        ):
            raise rejected(ArchiveRule.COMPRESSION_RATIO)

    counted = [(name, e) for name, e in normalised if not _is_ignored(name)]
    files = {name for name, e in counted if not e.is_dir and not name.endswith("/")}
    root_prefix = _find_root_prefix(files)
    if root_prefix is None:
        raise NotASlackExportError

    folders: set[str] = set()
    days: list[date] = []
    for name in files:
        if not name.startswith(root_prefix):
            continue
        parts = name[len(root_prefix) :].split("/")
        if len(parts) != 2:
            continue
        day = _parse_day(parts[1])
        if day is not None:
            folders.add(parts[0])
            days.append(day)

    return ArchiveMetadata(
        entry_count=len(counted),
        conversation_count=len(folders),
        export_date_from=min(days) if days else None,
        export_date_to=max(days) if days else None,
        root_prefix=root_prefix,
    )
