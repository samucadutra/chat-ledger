from __future__ import annotations

import json
import re
from collections import Counter

from chatledger_core.domain.generator.params import Profile
from chatledger_core.domain.generator.rates import (
    PROFILE_RATES,
    REASON_CODES,
    AnomalyType,
    exact_count,
    split_pair,
)
from generator_support import Rendered

TS = re.compile(r"^\d{10}\.\d{6}$")


def _expected(profile: Profile, regular: int, replies: int, files: int, bots: int, day_files: int):  # type: ignore[no-untyped-def]
    rates = PROFILE_RATES[profile]
    miss_e, miss_d = split_pair(exact_count(rates["target_missing"], regular))
    miss_ts, bad_ts = split_pair(exact_count(rates["ts_defect"], regular))
    return {
        "orphan_reply": exact_count(rates["orphan_reply"], replies),
        "edit": exact_count(rates["edit"], regular),
        "delete": exact_count(rates["delete"], regular),
        "edit_after_delete": exact_count(rates["edit_after_delete"], regular),
        "edit_target_missing": miss_e,
        "delete_target_missing": miss_d,
        "unknown_subtype": exact_count(rates["unknown_subtype"], regular),
        "missing_ts": miss_ts,
        "invalid_ts": bad_ts,
        "schema_violation": exact_count(rates["schema_violation"], regular),
        "malformed_json": exact_count(rates["malformed_json"], day_files),
        "empty_file": exact_count(rates["empty_file"], day_files),
        "unresolved_user": exact_count(rates["unresolved_user"], regular),
        "unresolved_file": exact_count(rates["unresolved_file"], files),
        "bot_no_identity": exact_count(rates["bot_no_identity"], bots),
        "ts_out_of_range": exact_count(rates["ts_out_of_range"], regular),
    }


def _check_counts(result: Rendered, profile: Profile) -> None:
    counts = Counter(a[0] for a in result.anomalies)
    regular = 100_000
    day_files = len(result.files) - counts["empty_file"]
    expected = _expected(profile, regular, 20_000, 4_000, 2_000, day_files)
    for kind, want in expected.items():
        assert abs(counts.get(kind, 0) - want) <= 1, (kind, counts.get(kind, 0), want)


def test_exact_counts_default(medium_default: Rendered) -> None:
    _check_counts(medium_default, Profile.DEFAULT)


def test_exact_counts_stress(medium_stress: Rendered, medium_default: Rendered) -> None:
    _check_counts(medium_stress, Profile.STRESS)
    default = Counter(a[0] for a in medium_default.anomalies)
    stress = Counter(a[0] for a in medium_stress.anomalies)
    assert all(stress[k] >= default[k] for k in default)


def test_pair_split_gives_extra_to_first_code(small_stress: Rendered) -> None:
    counts = Counter(a[0] for a in small_stress.anomalies)
    assert counts["edit_target_missing"] - counts["delete_target_missing"] in (0, 1)
    assert counts["missing_ts"] - counts["invalid_ts"] in (0, 1)


def test_reason_codes_are_prd_codes() -> None:
    assert {
        "orphan_reply": "F_ORPHAN_REPLY",
        "unresolved_user": "F_UNRESOLVED_USER",
        "empty_file": "X_EMPTY_FILE",
        "invalid_ts": "Q_INVALID_TS",
    }.items() <= {t.value: c for t, c in REASON_CODES.items()}.items()


def test_locations_resolve(small_stress: Rendered) -> None:
    """Every entry points at the injected record (or an event referencing it)."""
    for kind, conv_id, message_ts, source_file, index in small_stress.anomalies:
        assert small_stress.owner[source_file] == conv_id
        data = small_stress.files[source_file]
        if kind == "malformed_json":
            assert index is None and message_ts is None
            try:
                json.loads(data)
            except json.JSONDecodeError:
                continue
            raise AssertionError("malformed file parses")
        if kind == "empty_file":
            assert data == b"[]" and index is None and message_ts is None
            continue
        record = json.loads(data)[index]
        if kind == "missing_ts":
            assert message_ts is None and "ts" not in record
        elif message_ts is not None:
            assert record.get("ts") == message_ts or message_ts in json.dumps(record)


def test_anomaly_effects_on_records(small_stress: Rendered) -> None:
    by_kind: dict[str, list[dict]] = {}  # type: ignore[type-arg]
    for kind, _, _, source_file, index in small_stress.anomalies:
        if index is not None:
            by_kind.setdefault(kind, []).append(json.loads(small_stress.files[source_file])[index])
    users = {u.id for u in small_stress.workspace.users}
    assert all(r.get("subtype") == "x_custom_subtype" for r in by_kind["unknown_subtype"])
    assert all(not TS.match(r["ts"]) for r in by_kind["invalid_ts"])
    assert all(not isinstance(r["text"], str) for r in by_kind["schema_violation"])
    assert all(r["user"] not in users for r in by_kind["unresolved_user"])
    assert all(set(r["files"][0]) == {"id"} for r in by_kind["unresolved_file"])
    assert all("bot_id" not in r for r in by_kind["bot_no_identity"])
    assert all(r["subtype"] == "message_changed" for r in by_kind["edit"])
    assert all(r["subtype"] == "message_deleted" for r in by_kind["delete"])
    assert all(r["subtype"] == "message_changed" for r in by_kind["edit_after_delete"])


def test_orphan_replies_have_absent_parents(small_stress: Rendered) -> None:
    present: dict[str, set[str]] = {}
    for conv_id, _, rec in small_stress.records():
        if "ts" in rec:
            present.setdefault(conv_id, set()).add(rec["ts"])
    orphans = [a for a in small_stress.anomalies if a[0] == "orphan_reply"]
    assert orphans
    for _, conv_id, ts, source_file, index in orphans:
        record = json.loads(small_stress.files[source_file])[index]
        assert record["ts"] == ts and record["thread_ts"] not in present[conv_id]


def test_malformed_files_keep_a_complete_record(small_stress: Rendered) -> None:
    for kind, _, _, source_file, _ in small_stress.anomalies:
        if kind == "malformed_json":
            data = small_stress.files[source_file]
            assert data.startswith(b"[{") and not data.endswith(b"]")


def test_every_type_present_at_stress(medium_stress: Rendered) -> None:
    kinds = {a[0] for a in medium_stress.anomalies}
    assert kinds == {t.value for t in AnomalyType} - {"duplicate_source"}


def test_event_follows_its_target(small_stress: Rendered) -> None:
    for kind, _, message_ts, source_file, index in small_stress.anomalies:
        if kind in ("edit", "delete") and index is not None:
            records = json.loads(small_stress.files[source_file])
            event = records[index]
            target_index = next(i for i, r in enumerate(records) if r.get("ts") == message_ts)
            assert target_index < index and event["ts"] > message_ts
