from __future__ import annotations

import pytest

from chatledger_core.domain.generator.errors import GenerationParamsInvalidError
from chatledger_core.domain.generator.params import (
    CONVERSATIONS_CAP_MESSAGE,
    MESSAGES_MESSAGE,
    SEED_MESSAGE,
    Preset,
    Profile,
    validate_params,
)


def test_preset_tables() -> None:
    small = validate_params(seed=1, preset="small", profile="clean")
    medium = validate_params(seed=1, preset="medium", profile="default")
    large = validate_params(seed=1, preset="large", profile="stress")
    assert (small.messages, small.conversations, small.users, small.days) == (10_000, 50, 40, 90)
    assert (medium.messages, medium.conversations, medium.users, medium.days) == (
        100_000,
        500,
        300,
        365,
    )
    assert (large.messages, large.conversations, large.users, large.days) == (
        1_000_000,
        5_000,
        2_000,
        730,
    )
    assert small.preset is Preset.SMALL and large.profile is Profile.STRESS


def test_custom_users_and_days() -> None:
    low = validate_params(
        seed=1, preset="custom", profile="clean", messages=1_000, conversations=10
    )
    high = validate_params(
        seed=1, preset="custom", profile="clean", messages=1_000_000, conversations=10
    )
    assert (low.users, low.days) == (10, 365)
    assert high.users == 2_000


def test_filenames() -> None:
    p = validate_params(seed=42, preset="small", profile="default")
    assert p.filename == "slack-export-42-small-default.zip"
    assert p.ground_truth_filename == "ground-truth-42.json"


@pytest.mark.parametrize("field", ["messages", "conversations"])
def test_custom_requires_sizes(field: str) -> None:
    kwargs = {"messages": 2000, "conversations": 20}
    del kwargs[field]
    with pytest.raises(GenerationParamsInvalidError) as exc:
        validate_params(seed=1, preset="custom", profile="clean", **kwargs)
    assert exc.value.details["field"] == field


@pytest.mark.parametrize(
    ("messages", "ok"), [(999, False), (1_000, True), (1_000_000, True), (1_000_001, False)]
)
def test_messages_range(messages: int, ok: bool) -> None:
    def call() -> object:
        return validate_params(
            seed=1, preset="custom", profile="clean", messages=messages, conversations=5
        )

    if ok:
        call()
    else:
        with pytest.raises(GenerationParamsInvalidError) as exc:
            call()
        assert exc.value.message == MESSAGES_MESSAGE
        assert exc.value.code == "GENERATION_PARAMS_INVALID"


def test_conversations_cap_and_range() -> None:
    with pytest.raises(GenerationParamsInvalidError) as exc:
        validate_params(seed=1, preset="custom", profile="clean", messages=2000, conversations=1001)
    assert exc.value.message == CONVERSATIONS_CAP_MESSAGE
    validate_params(seed=1, preset="custom", profile="clean", messages=2000, conversations=1000)
    with pytest.raises(GenerationParamsInvalidError) as exc:
        validate_params(seed=1, preset="custom", profile="clean", messages=2000, conversations=0)
    assert exc.value.message == "Conversations must be between 1 and 5,000"


def test_messages_checked_before_conversations() -> None:
    with pytest.raises(GenerationParamsInvalidError) as exc:
        validate_params(
            seed=1, preset="custom", profile="clean", messages=2_000_000, conversations=9_999
        )
    assert exc.value.message == MESSAGES_MESSAGE


@pytest.mark.parametrize("extra", [{"messages": 5000}, {"conversations": 10}])
def test_non_custom_rejects_sizes(extra: dict[str, int]) -> None:
    with pytest.raises(GenerationParamsInvalidError):
        validate_params(seed=1, preset="small", profile="clean", **extra)


@pytest.mark.parametrize(
    ("seed", "ok"),
    [
        (-1, False),
        (0, True),
        (2_147_483_647, True),
        (2_147_483_648, False),
        (True, False),
        ("7", False),
    ],
)
def test_seed_range(seed: object, ok: bool) -> None:
    if ok:
        validate_params(seed=seed, preset="small", profile="clean")
    else:
        with pytest.raises(GenerationParamsInvalidError) as exc:
            validate_params(seed=seed, preset="small", profile="clean")
        assert exc.value.message == SEED_MESSAGE


def test_unknown_preset_and_profile() -> None:
    with pytest.raises(GenerationParamsInvalidError) as exc:
        validate_params(seed=1, preset="huge", profile="clean")
    assert exc.value.details["field"] == "preset"
    with pytest.raises(GenerationParamsInvalidError) as exc:
        validate_params(seed=1, preset="small", profile="wild")
    assert exc.value.details["field"] == "profile"
