from __future__ import annotations

import pytest

from chatledger_core.domain.generator.apportion import apportion
from chatledger_core.domain.generator.params import Profile
from chatledger_core.domain.generator.rates import (
    REASON_CODES,
    AnomalyType,
    anomaly_totals,
    exact_count,
    percent_count,
    split_pair,
)


@pytest.mark.parametrize(
    ("rate", "base", "expected"),
    [(300, 20_000, 60), (50, 10_000, 5), (10, 5_000, 1), (50, 1_000, 1), (49, 1_000, 0), (0, 9, 0)],
)
def test_exact_count_rounds_half_up(rate: int, base: int, expected: int) -> None:
    assert exact_count(rate, base) == expected


def test_percent_and_pair_split() -> None:
    assert percent_count(20, 10_000) == 2_000
    assert percent_count(3, 2_000) == 60
    assert percent_count(2, 25) == 1
    assert split_pair(5) == (3, 2)
    assert split_pair(4) == (2, 2)
    assert split_pair(0) == (0, 0)


def test_clean_profile_has_no_anomalies() -> None:
    assert (
        anomaly_totals(
            Profile.CLEAN, messages=10_000, replies=2_000, files=400, bots=200, day_files=900
        )
        == {}
    )


def test_default_and_stress_totals() -> None:
    kwargs = {
        "messages": 100_000,
        "replies": 20_000,
        "files": 4_000,
        "bots": 2_000,
        "day_files": 10_000,
    }
    default = anomaly_totals(Profile.DEFAULT, **kwargs)
    stress = anomaly_totals(Profile.STRESS, **kwargs)
    assert default[AnomalyType.ORPHAN_REPLY] == 60
    assert default[AnomalyType.EDIT] == 3_000
    assert default[AnomalyType.EDIT_TARGET_MISSING] == 10
    assert default[AnomalyType.DELETE_TARGET_MISSING] == 10
    assert default[AnomalyType.EMPTY_FILE] == 50
    assert default[AnomalyType.UNRESOLVED_FILE] == 80
    assert stress[AnomalyType.ORPHAN_REPLY] == 600
    assert stress[AnomalyType.UNRESOLVED_USER] == 2_000
    assert all(stress[k] >= default[k] for k in default)


def test_reason_codes_cover_every_type() -> None:
    assert set(REASON_CODES) == set(AnomalyType)
    assert REASON_CODES[AnomalyType.DUPLICATE_SOURCE] == "X_DUPLICATE_SOURCE"
    assert REASON_CODES[AnomalyType.EDIT_AFTER_DELETE] == "F_EDIT_AFTER_DELETE"
    assert REASON_CODES[AnomalyType.ORPHAN_REPLY] == "F_ORPHAN_REPLY"


def test_apportion_largest_remainder_and_caps() -> None:
    assert apportion(10, [1, 1, 1]) == [4, 3, 3]
    assert apportion(100, [60, 15, 20, 5]) == [60, 15, 20, 5]
    assert apportion(50, (60, 15, 20, 5)) == [30, 8, 10, 2]
    assert apportion(10, [1, 1], caps=[2, 100]) == [2, 8]
    assert apportion(10, [5, 5], caps=[1, 1]) == [1, 1]
    assert apportion(0, [1, 2]) == [0, 0]
    assert apportion(5, [0, 0]) == [0, 0]
