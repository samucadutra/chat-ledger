"""Generator parameters, presets and validation (spec A4-A6)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from chatledger_core.domain.generator.errors import GenerationParamsInvalidError

SEED_MAX = 2_147_483_647
MESSAGES_MIN = 1_000
MESSAGES_MAX = 1_000_000
CONVERSATIONS_MIN = 1
CONVERSATIONS_MAX = 5_000

SEED_MESSAGE = "Seed must be an integer between 0 and 2,147,483,647"
MESSAGES_MESSAGE = "Messages must be between 1,000 and 1,000,000"
CONVERSATIONS_MESSAGE = "Conversations must be between 1 and 5,000"
CONVERSATIONS_CAP_MESSAGE = "Conversations must not exceed messages / 2"
PRESET_MESSAGE = "Preset must be one of small, medium, large, custom"
PROFILE_MESSAGE = "Profile must be one of clean, default, stress"
SIZES_NOT_ALLOWED_MESSAGE = "Messages and conversations are only valid with the custom preset"
SIZES_REQUIRED_MESSAGE = "Messages and conversations are required with the custom preset"


class Preset(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    CUSTOM = "custom"


class Profile(StrEnum):
    CLEAN = "clean"
    DEFAULT = "default"
    STRESS = "stress"


@dataclass(frozen=True)
class PresetSpec:
    messages: int
    conversations: int
    users: int
    days: int


PRESETS: dict[Preset, PresetSpec] = {
    Preset.SMALL: PresetSpec(10_000, 50, 40, 90),
    Preset.MEDIUM: PresetSpec(100_000, 500, 300, 365),
    Preset.LARGE: PresetSpec(1_000_000, 5_000, 2_000, 730),
}

CUSTOM_DAYS = 365
CUSTOM_USERS_MIN = 10
CUSTOM_USERS_MAX = 2_000

PROFILE_DESCRIPTIONS: dict[Profile, str] = {
    Profile.CLEAN: "No injected anomalies",
    Profile.DEFAULT: "Realistic mix of edits, deletions and rare defects",
    Profile.STRESS: "High defect rates to exercise every gate",
}


@dataclass(frozen=True)
class GenerationParams:
    seed: int
    preset: Preset
    profile: Profile
    messages: int
    conversations: int
    users: int
    days: int

    @property
    def filename(self) -> str:
        return f"slack-export-{self.seed}-{self.preset.value}-{self.profile.value}.zip"

    @property
    def ground_truth_filename(self) -> str:
        return f"ground-truth-{self.seed}.json"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_params(
    *,
    seed: object,
    preset: object,
    profile: object,
    messages: object = None,
    conversations: object = None,
) -> GenerationParams:
    """Validate raw input and resolve the effective sizes (raises on invalid input)."""
    if not _is_int(seed) or not 0 <= seed <= SEED_MAX:  # type: ignore[operator]
        raise GenerationParamsInvalidError(SEED_MESSAGE, "seed")
    assert isinstance(seed, int)
    try:
        preset_value = Preset(str(preset))
    except ValueError:
        raise GenerationParamsInvalidError(PRESET_MESSAGE, "preset") from None
    try:
        profile_value = Profile(str(profile))
    except ValueError:
        raise GenerationParamsInvalidError(PROFILE_MESSAGE, "profile") from None

    if preset_value is not Preset.CUSTOM:
        if messages is not None:
            raise GenerationParamsInvalidError(SIZES_NOT_ALLOWED_MESSAGE, "messages")
        if conversations is not None:
            raise GenerationParamsInvalidError(SIZES_NOT_ALLOWED_MESSAGE, "conversations")
        spec = PRESETS[preset_value]
        return GenerationParams(
            seed,
            preset_value,
            profile_value,
            spec.messages,
            spec.conversations,
            spec.users,
            spec.days,
        )

    if messages is None:
        raise GenerationParamsInvalidError(SIZES_REQUIRED_MESSAGE, "messages")
    if conversations is None:
        raise GenerationParamsInvalidError(SIZES_REQUIRED_MESSAGE, "conversations")
    if not _is_int(messages) or not MESSAGES_MIN <= messages <= MESSAGES_MAX:  # type: ignore[operator]
        raise GenerationParamsInvalidError(MESSAGES_MESSAGE, "messages")
    if not _is_int(conversations) or not (
        CONVERSATIONS_MIN <= conversations <= CONVERSATIONS_MAX  # type: ignore[operator]
    ):
        raise GenerationParamsInvalidError(CONVERSATIONS_MESSAGE, "conversations")
    assert isinstance(messages, int)
    assert isinstance(conversations, int)
    if conversations * 2 > messages:
        raise GenerationParamsInvalidError(CONVERSATIONS_CAP_MESSAGE, "conversations")
    users = min(CUSTOM_USERS_MAX, max(CUSTOM_USERS_MIN, messages // 250))
    return GenerationParams(
        seed, preset_value, profile_value, messages, conversations, users, CUSTOM_DAYS
    )


def params_for_effective(
    *, seed: int, preset: str, profile: str, messages: int, conversations: int
) -> GenerationParams:
    """Rebuild parameters from stored effective values (already validated)."""
    preset_value = Preset(preset)
    if preset_value is Preset.CUSTOM:
        return validate_params(
            seed=seed,
            preset=preset,
            profile=profile,
            messages=messages,
            conversations=conversations,
        )
    return validate_params(seed=seed, preset=preset, profile=profile)
