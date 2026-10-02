from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from chatledger_core.domain.intake.archive import ArchiveLimits, inspect_entries
from chatledger_core.domain.intake.errors import (
    ArchiveRejectedError,
    NotASlackExportError,
)
from chatledger_core.infra.intake.zip_archive_inspector import ZipArchiveInspector
from factories import FIXTURES_DIR

LIMITS = ArchiveLimits()


def meta(name: str):  # type: ignore[no-untyped-def]
    return inspect_entries(ZipArchiveInspector().read_entries(FIXTURES_DIR / name), LIMITS)


def test_minimal_export() -> None:
    m = meta("minimal-export.zip")
    assert (m.root_prefix, m.conversation_count, m.entry_count) == ("", 2, 8)
    assert (m.export_date_from, m.export_date_to) == (date(2024, 1, 3), date(2024, 1, 5))


def test_50_conversations_90_day_range() -> None:
    m = meta("export-50conv-90d.zip")
    assert m.conversation_count == 50
    assert (m.export_date_from, m.export_date_to) == (date(2024, 1, 3), date(2024, 4, 1))


def test_nested_export() -> None:
    m = meta("nested-export.zip")
    assert m.root_prefix == "Acme Slack export Jan 2024/"
    assert m.conversation_count == 2


def test_missing_users() -> None:
    with pytest.raises(NotASlackExportError):
        meta("missing-users.zip")


def test_path_traversal() -> None:
    with pytest.raises(ArchiveRejectedError) as info:
        meta("path-traversal.zip")
    assert info.value.details["rule"] == "path_escape"


def test_zip_bomb() -> None:
    with pytest.raises(ArchiveRejectedError) as info:
        meta("zip-bomb.zip")
    assert info.value.details["rule"] == "compression_ratio"


def test_not_a_zip() -> None:
    with pytest.raises(ArchiveRejectedError) as info:
        meta("not-a-zip.zip")
    assert info.value.details["rule"] == "not_a_zip"


def test_empty_file_is_not_a_zip(tmp_path: Path) -> None:
    empty = tmp_path / "e.zip"
    empty.write_bytes(b"")
    with pytest.raises(ArchiveRejectedError) as info:
        ZipArchiveInspector().read_entries(empty)
    assert info.value.details["rule"] == "not_a_zip"


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ArchiveRejectedError):
        ZipArchiveInspector().read_entries(tmp_path / "none.zip")
