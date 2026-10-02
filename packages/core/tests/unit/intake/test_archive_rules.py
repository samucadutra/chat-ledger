from __future__ import annotations

from datetime import date

import pytest

from chatledger_core.domain.intake.archive import ArchiveEntry, ArchiveLimits, inspect_entries
from chatledger_core.domain.intake.errors import ArchiveRejectedError, NotASlackExportError

LIMITS = ArchiveLimits()


def e(name: str, size: int = 10, packed: int = 10) -> ArchiveEntry:
    return ArchiveEntry(name, size, packed, is_dir=name.endswith("/"))


def root_markers() -> list[ArchiveEntry]:
    return [e("users.json"), e("channels.json")]


def test_markers_at_root() -> None:
    meta = inspect_entries(root_markers(), LIMITS)
    assert meta.root_prefix == ""
    assert meta.entry_count == 2


def test_markers_in_single_top_folder() -> None:
    meta = inspect_entries([e("Acme/users.json"), e("Acme/channels.json")], LIMITS)
    assert meta.root_prefix == "Acme/"


def test_markers_split_across_folders_rejected() -> None:
    with pytest.raises(NotASlackExportError):
        inspect_entries([e("A/users.json"), e("B/channels.json")], LIMITS)


def test_two_complete_folders_are_ambiguous() -> None:
    entries = [e(f"{d}/{f}.json") for d in ("A", "B") for f in ("users", "channels")]
    with pytest.raises(NotASlackExportError):
        inspect_entries(entries, LIMITS)


def test_nested_two_levels_rejected() -> None:
    with pytest.raises(NotASlackExportError):
        inspect_entries([e("A/B/users.json"), e("A/B/channels.json")], LIMITS)


def test_missing_users_json() -> None:
    with pytest.raises(NotASlackExportError):
        inspect_entries([e("channels.json"), e("general/2024-01-03.json")], LIMITS)


def test_macosx_entries_ignored() -> None:
    entries = [
        *root_markers(),
        e("__MACOSX/._users.json"),
        e("__MACOSX/users.json"),
        e(".DS_Store"),
        e("general/.DS_Store"),
        e("general/2024-01-03.json"),
    ]
    meta = inspect_entries(entries, LIMITS)
    assert meta.entry_count == 3
    assert meta.conversation_count == 1


def test_macosx_markers_do_not_satisfy_check() -> None:
    with pytest.raises(NotASlackExportError):
        inspect_entries([e("__MACOSX/users.json"), e("__MACOSX/channels.json")], LIMITS)


@pytest.mark.parametrize(
    "name",
    [
        "../evil.json",
        "a/../../evil.json",
        "/etc/passwd",
        "C:\\evil.json",
        "c:/evil.json",
        "a\\..\\b",
    ],
)
def test_path_escape(name: str) -> None:
    with pytest.raises(ArchiveRejectedError) as info:
        inspect_entries([*root_markers(), e(name)], LIMITS)
    assert info.value.details["rule"] == "path_escape"
    assert info.value.message == "Archive rejected: entry path escapes archive"
    assert info.value.code == "ARCHIVE_REJECTED"


def test_backslash_normalised() -> None:
    entries = [e("users.json"), e("channels.json"), e("general\\2024-01-03.json")]
    meta = inspect_entries(entries, LIMITS)
    assert meta.conversation_count == 1
    assert meta.export_date_from == date(2024, 1, 3)


def test_dotdot_inside_a_name_is_fine() -> None:
    meta = inspect_entries([*root_markers(), e("general/notes..txt")], LIMITS)
    assert meta.entry_count == 3


def test_entry_count_limit() -> None:
    ok = [e("users.json"), e("channels.json")] + [e(f"x/{i}.bin") for i in range(199_998)]
    assert inspect_entries(ok, LIMITS).entry_count == 200_000
    with pytest.raises(ArchiveRejectedError) as info:
        inspect_entries([*ok, e("x/extra.bin")], LIMITS)
    assert info.value.details["rule"] == "entry_count"


def test_uncompressed_total_limit() -> None:
    gib = 1024**3
    entries = [*root_markers(), e("a.bin", 10 * gib, 10 * gib), e("b.bin", 10 * gib + 1, 10 * gib)]
    with pytest.raises(ArchiveRejectedError) as info:
        inspect_entries(entries, LIMITS)
    assert info.value.details["rule"] == "uncompressed_size"


def test_uncompressed_total_exactly_at_limit_passes() -> None:
    gib = 1024**3
    entries = [*root_markers(), e("a.bin", 10 * gib, 10 * gib), e("b.bin", 10 * gib - 20, 10 * gib)]
    assert inspect_entries(entries, LIMITS).entry_count == 4


def test_ratio_over_limit_large_entry() -> None:
    entries = [*root_markers(), e("pad.bin", 50 * 1024 * 1024, 40 * 1024)]
    with pytest.raises(ArchiveRejectedError) as info:
        inspect_entries(entries, LIMITS)
    assert info.value.details["rule"] == "compression_ratio"
    assert info.value.message == "Archive rejected: compression ratio above 100:1"


def test_ratio_ignored_below_threshold() -> None:
    entries = [*root_markers(), e("small.json", 900 * 1024, 2 * 1024)]
    assert inspect_entries(entries, LIMITS).entry_count == 3


def test_ratio_with_zero_compressed_size() -> None:
    entries = [*root_markers(), e("pad.bin", 2 * 1024 * 1024, 0)]
    with pytest.raises(ArchiveRejectedError):
        inspect_entries(entries, LIMITS)


def test_rule_order_first_failure_wins() -> None:
    entries = [e("../evil.json"), e("pad.bin", 50 * 1024 * 1024, 1024)]
    with pytest.raises(ArchiveRejectedError) as info:
        inspect_entries(entries, LIMITS)
    assert info.value.details["rule"] == "path_escape"


def test_rules_run_before_markers() -> None:
    with pytest.raises(ArchiveRejectedError):
        inspect_entries([e("pad.bin", 50 * 1024 * 1024, 1024)], LIMITS)


def test_conversation_count_and_dates() -> None:
    entries = [
        *root_markers(),
        e("general/2024-01-03.json"),
        e("general/2024-01-04.json"),
        e("random/2024-01-10.json"),
        e("dm-alice/2024-01-05.json"),
    ]
    meta = inspect_entries(entries, LIMITS)
    assert meta.conversation_count == 3
    assert meta.export_date_from == date(2024, 1, 3)
    assert meta.export_date_to == date(2024, 1, 10)


def test_invalid_calendar_date_ignored() -> None:
    entries = [*root_markers(), e("general/2024-01-03.json"), e("general/2024-02-30.json")]
    meta = inspect_entries(entries, LIMITS)
    assert meta.export_date_to == date(2024, 1, 3)
    assert meta.entry_count == 4


def test_folder_with_only_invalid_dates_is_not_a_conversation() -> None:
    meta = inspect_entries([*root_markers(), e("general/2024-02-30.json")], LIMITS)
    assert meta.conversation_count == 0
    assert meta.export_date_from is None


def test_no_day_files_yields_null_dates() -> None:
    meta = inspect_entries(root_markers(), LIMITS)
    assert meta.export_date_from is None
    assert meta.export_date_to is None
    assert meta.conversation_count == 0


def test_nested_export_counts_only_under_root_prefix() -> None:
    entries = [
        e("Acme/users.json"),
        e("Acme/channels.json"),
        e("Acme/general/2024-01-03.json"),
        e("other/2024-05-05.json"),
        e("Acme/general/deep/2024-06-06.json"),
    ]
    meta = inspect_entries(entries, LIMITS)
    assert meta.conversation_count == 1
    assert meta.export_date_to == date(2024, 1, 3)


def test_directory_entries_are_counted_but_not_files() -> None:
    meta = inspect_entries([*root_markers(), e("general/")], LIMITS)
    assert meta.entry_count == 3
    assert meta.conversation_count == 0
