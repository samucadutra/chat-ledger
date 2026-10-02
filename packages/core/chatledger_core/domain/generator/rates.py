"""Anomaly profile rate table (PRD F03) and exact-count arithmetic."""

from __future__ import annotations

from enum import StrEnum

from chatledger_core.domain.generator.params import Profile

RATE_DENOMINATOR = 100_000


class AnomalyType(StrEnum):
    ORPHAN_REPLY = "orphan_reply"
    EDIT = "edit"
    DELETE = "delete"
    EDIT_AFTER_DELETE = "edit_after_delete"
    EDIT_TARGET_MISSING = "edit_target_missing"
    DELETE_TARGET_MISSING = "delete_target_missing"
    UNKNOWN_SUBTYPE = "unknown_subtype"
    MISSING_TS = "missing_ts"
    INVALID_TS = "invalid_ts"
    SCHEMA_VIOLATION = "schema_violation"
    MALFORMED_JSON = "malformed_json"
    EMPTY_FILE = "empty_file"
    UNRESOLVED_USER = "unresolved_user"
    UNRESOLVED_FILE = "unresolved_file"
    BOT_NO_IDENTITY = "bot_no_identity"
    TS_OUT_OF_RANGE = "ts_out_of_range"
    DUPLICATE_SOURCE = "duplicate_source"


REASON_CODES: dict[AnomalyType, str] = {
    AnomalyType.ORPHAN_REPLY: "F_ORPHAN_REPLY",
    AnomalyType.EDIT: "X_EDIT_EVENT",
    AnomalyType.DELETE: "X_DELETE_EVENT",
    AnomalyType.EDIT_AFTER_DELETE: "F_EDIT_AFTER_DELETE",
    AnomalyType.EDIT_TARGET_MISSING: "Q_EDIT_TARGET_MISSING",
    AnomalyType.DELETE_TARGET_MISSING: "Q_DELETE_TARGET_MISSING",
    AnomalyType.UNKNOWN_SUBTYPE: "Q_UNKNOWN_SUBTYPE",
    AnomalyType.MISSING_TS: "Q_MISSING_TS",
    AnomalyType.INVALID_TS: "Q_INVALID_TS",
    AnomalyType.SCHEMA_VIOLATION: "Q_SCHEMA_VIOLATION",
    AnomalyType.MALFORMED_JSON: "Q_MALFORMED_JSON",
    AnomalyType.EMPTY_FILE: "X_EMPTY_FILE",
    AnomalyType.UNRESOLVED_USER: "F_UNRESOLVED_USER",
    AnomalyType.UNRESOLVED_FILE: "F_UNRESOLVED_FILE",
    AnomalyType.BOT_NO_IDENTITY: "F_BOT_NO_IDENTITY",
    AnomalyType.TS_OUT_OF_RANGE: "F_TS_OUT_OF_RANGE",
    AnomalyType.DUPLICATE_SOURCE: "X_DUPLICATE_SOURCE",
}

# Rate keys are the rows of the PRD table; values are numerators over RATE_DENOMINATOR
# (0.05% -> 50). Bases: orphan -> replies; unresolved_file -> file refs; bot_no_identity ->
# bot messages; malformed/empty -> day files; every other row -> base messages.
PROFILE_RATES: dict[Profile, dict[str, int]] = {
    Profile.CLEAN: {},
    Profile.DEFAULT: {
        "orphan_reply": 300,
        "edit": 3_000,
        "delete": 1_000,
        "edit_after_delete": 50,
        "target_missing": 20,
        "unknown_subtype": 50,
        "ts_defect": 10,
        "schema_violation": 20,
        "malformed_json": 50,
        "empty_file": 500,
        "unresolved_user": 200,
        "unresolved_file": 2_000,
        "bot_no_identity": 100,
        "ts_out_of_range": 10,
    },
    Profile.STRESS: {
        "orphan_reply": 3_000,
        "edit": 3_000,
        "delete": 1_000,
        "edit_after_delete": 500,
        "target_missing": 300,
        "unknown_subtype": 1_000,
        "ts_defect": 300,
        "schema_violation": 300,
        "malformed_json": 500,
        "empty_file": 500,
        "unresolved_user": 2_000,
        "unresolved_file": 10_000,
        "bot_no_identity": 2_000,
        "ts_out_of_range": 200,
    },
}


def exact_count(rate_numerator: int, base: int) -> int:
    """``round_half_up(rate x base)`` in exact integer arithmetic."""
    return (rate_numerator * base + RATE_DENOMINATOR // 2) // RATE_DENOMINATOR


def percent_count(percent: int, base: int) -> int:
    """``round_half_up(percent% of base)``."""
    return (percent * base + 50) // 100


def split_pair(total: int) -> tuple[int, int]:
    """Split a combined row 50/50; an odd count gives the extra record to the first code."""
    return (total + 1) // 2, total // 2


def anomaly_totals(
    profile: Profile, *, messages: int, replies: int, files: int, bots: int, day_files: int
) -> dict[AnomalyType, int]:
    """Exact injected count per type for a segment, from the profile table."""
    rates = PROFILE_RATES[profile]
    if not rates:
        return {}
    edit_missing, delete_missing = split_pair(exact_count(rates["target_missing"], messages))
    missing_ts, invalid_ts = split_pair(exact_count(rates["ts_defect"], messages))
    return {
        AnomalyType.ORPHAN_REPLY: exact_count(rates["orphan_reply"], replies),
        AnomalyType.EDIT: exact_count(rates["edit"], messages),
        AnomalyType.DELETE: exact_count(rates["delete"], messages),
        AnomalyType.EDIT_AFTER_DELETE: exact_count(rates["edit_after_delete"], messages),
        AnomalyType.EDIT_TARGET_MISSING: edit_missing,
        AnomalyType.DELETE_TARGET_MISSING: delete_missing,
        AnomalyType.UNKNOWN_SUBTYPE: exact_count(rates["unknown_subtype"], messages),
        AnomalyType.MISSING_TS: missing_ts,
        AnomalyType.INVALID_TS: invalid_ts,
        AnomalyType.SCHEMA_VIOLATION: exact_count(rates["schema_violation"], messages),
        AnomalyType.MALFORMED_JSON: exact_count(rates["malformed_json"], day_files),
        AnomalyType.EMPTY_FILE: exact_count(rates["empty_file"], day_files),
        AnomalyType.UNRESOLVED_USER: exact_count(rates["unresolved_user"], messages),
        AnomalyType.UNRESOLVED_FILE: exact_count(rates["unresolved_file"], files),
        AnomalyType.BOT_NO_IDENTITY: exact_count(rates["bot_no_identity"], bots),
        AnomalyType.TS_OUT_OF_RANGE: exact_count(rates["ts_out_of_range"], messages),
    }
