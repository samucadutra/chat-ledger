"""Seeded workspace plan: users, conversations, volumes, quotas and the fixed calendar.

Everything here is drawn from one ``random.Random(seed)`` in a fixed order before any
conversation is rendered (spec decision "Determinism"). Per-feature and per-anomaly counts are
apportioned across conversations so the global totals are exact.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from chatledger_core.domain.generator.apportion import apportion
from chatledger_core.domain.generator.params import GenerationParams, Profile
from chatledger_core.domain.generator.rates import AnomalyType, anomaly_totals, percent_count
from chatledger_core.domain.generator.vocab import (
    ADJECTIVES,
    BOT_NAMES,
    FIRST_NAMES,
    LAST_NAMES,
    NOUNS,
)

GENERATOR_VERSION = "1.0.0"
END_DATE = date(2025, 12, 31)
_EPOCH_ORDINAL = date(1970, 1, 1).toordinal()
MESSAGES_PER_DAY_FILE = 8
ZIPF_EXPONENT = 1.1
BOT_COUNT = 8

TYPE_MIX = (60, 15, 20, 5)  # public, private, dm, mpim


class ConvKind(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    DM = "dm"
    MPIM = "mpim"


@dataclass(frozen=True)
class User:
    id: str
    name: str
    real_name: str
    deleted: bool


@dataclass(frozen=True)
class Bot:
    id: str
    name: str
    app_id: str


@dataclass(frozen=True)
class Conversation:
    id: str
    kind: ConvKind
    name: str
    folder: str
    members: tuple[str, ...]
    rank: int
    created: int


@dataclass
class Quotas:
    replies: int = 0
    broadcasts: int = 0
    bots: int = 0
    reactions: int = 0
    files: int = 0
    mentions: int = 0
    links: int = 0
    anomalies: dict[AnomalyType, int] = field(default_factory=dict)


@dataclass
class SegmentPlan:
    """What one conversation renders for one period (the base period or a new period)."""

    conv: Conversation
    messages: int
    active_days: int
    day_offset: int
    day_count: int
    sub_seed: int
    quotas: Quotas
    membership: bool
    force_ends: bool


@dataclass
class Workspace:
    params: GenerationParams
    team_id: str
    users: list[User]
    bots: list[Bot]
    conversations: list[Conversation]  # in rank order
    segments: list[SegmentPlan]  # base period, same order

    @property
    def user_ids(self) -> list[str]:
        return [u.id for u in self.users]

    @property
    def days(self) -> int:
        return self.params.days


def day_date(days: int, index: int) -> date:
    """Calendar date of day ``index``; the base period always ends on ``END_DATE``.

    Indices beyond ``days - 1`` continue past ``END_DATE`` (re-delivery extension).
    """
    return date.fromordinal(END_DATE.toordinal() - (days - 1 - index))


def day_epoch(days: int, index: int) -> int:
    return (END_DATE.toordinal() - (days - 1 - index) - _EPOCH_ORDINAL) * 86400


def team_id_for(seed: int) -> str:
    return "T" + hashlib.sha256(f"chatledger-team:{seed}".encode()).hexdigest()[:8].upper()


def active_day_count(messages: int, day_count: int, is_largest: bool) -> int:
    if messages <= 0:
        return 0
    count = min(day_count, -(-messages // MESSAGES_PER_DAY_FILE))
    if is_largest:
        count = max(count, min(2, messages, day_count))
    return count


def zipf_counts(total: int, conversations: int) -> list[int]:
    weights = [round(1e12 * rank**-ZIPF_EXPONENT) for rank in range(1, conversations + 1)]
    counts = apportion(total, weights)
    for i, value in enumerate(counts):
        if value == 0:  # at least one message each: take it from the current largest
            biggest = max(range(len(counts)), key=lambda j: (counts[j], -j))
            counts[biggest] -= 1
            counts[i] = 1
    return counts


def plan_quotas(
    counts: Sequence[int],
    active: Sequence[int],
    day_count: int,
    profile: Profile,
    *,
    is_largest: Sequence[bool],
) -> list[Quotas]:
    """Exact per-conversation quotas whose sums equal the global targets."""
    size = len(counts)
    total = sum(counts)
    quotas = [Quotas() for _ in range(size)]
    replies = apportion(
        percent_count(20, total),
        counts,
        [max(0, n - d) for n, d in zip(counts, active, strict=True)],
    )
    broadcasts = apportion(percent_count(3, sum(replies)), replies, replies)
    bots = apportion(
        percent_count(2, total),
        counts,
        [max(0, n - d - r) for n, d, r in zip(counts, active, replies, strict=True)],
    )
    reactions = apportion(percent_count(8, total), counts, list(counts))
    files = apportion(percent_count(4, total), counts, list(counts))
    mentions = apportion(percent_count(15, total), counts, list(counts))
    links = apportion(percent_count(10, total), counts, list(counts))
    for i in range(size):
        q = quotas[i]
        q.replies, q.broadcasts, q.bots = replies[i], broadcasts[i], bots[i]
        q.reactions, q.files, q.mentions, q.links = reactions[i], files[i], mentions[i], links[i]

    totals = anomaly_totals(
        profile,
        messages=total,
        replies=sum(replies),
        files=sum(files),
        bots=sum(bots),
        day_files=sum(active),
    )
    if not totals:
        return quotas

    def spread(kind: AnomalyType, weights: Sequence[int], caps: Sequence[int]) -> list[int]:
        values = apportion(totals[kind], weights, caps)
        for i, value in enumerate(values):
            if value:
                quotas[i].anomalies[kind] = value
        return values

    spread(AnomalyType.ORPHAN_REPLY, replies, replies)
    spread(AnomalyType.UNRESOLVED_FILE, files, files)
    spread(AnomalyType.BOT_NO_IDENTITY, bots, bots)
    spread(AnomalyType.MALFORMED_JSON, active, [d // 2 for d in active])
    spread(AnomalyType.EMPTY_FILE, active, [max(0, day_count - d) for d in active])
    spread(AnomalyType.EDIT_TARGET_MISSING, counts, list(counts))
    spread(AnomalyType.DELETE_TARGET_MISSING, counts, list(counts))

    # Record-targeting types share a per-conversation budget so they never exhaust a conversation.
    budget = [n // 2 for n in counts]
    plain = [max(0, n - r) // 3 for n, r in zip(counts, replies, strict=True)]
    for kind in (
        AnomalyType.EDIT,
        AnomalyType.DELETE,
        AnomalyType.EDIT_AFTER_DELETE,
        AnomalyType.UNKNOWN_SUBTYPE,
        AnomalyType.SCHEMA_VIOLATION,
        AnomalyType.UNRESOLVED_USER,
        AnomalyType.MISSING_TS,
        AnomalyType.INVALID_TS,
        AnomalyType.TS_OUT_OF_RANGE,
    ):
        is_ts = kind in (
            AnomalyType.MISSING_TS,
            AnomalyType.INVALID_TS,
            AnomalyType.TS_OUT_OF_RANGE,
        )
        caps = [min(b, p) if is_ts else b for b, p in zip(budget, plain, strict=True)]
        values = spread(kind, counts, caps)
        budget = [b - v for b, v in zip(budget, values, strict=True)]
    return quotas


def _unique(rng: random.Random, taken: set[str], make: str) -> str:
    candidate = make
    n = 1
    while candidate in taken:
        n += 1
        candidate = f"{make}-{n}"
    taken.add(candidate)
    return candidate


def build_segments(
    conversations: Sequence[Conversation],
    counts: Sequence[int],
    sub_seeds: Sequence[int],
    profile: Profile,
    *,
    day_offset: int,
    day_count: int,
    membership: bool,
) -> list[SegmentPlan]:
    largest = [conv.rank == 1 for conv in conversations]
    active = [
        active_day_count(n, day_count, is_largest)
        for n, is_largest in zip(counts, largest, strict=True)
    ]
    quotas = plan_quotas(counts, active, day_count, profile, is_largest=largest)
    return [
        SegmentPlan(
            conv=conv,
            messages=counts[i],
            active_days=active[i],
            day_offset=day_offset,
            day_count=day_count,
            sub_seed=sub_seeds[i],
            quotas=quotas[i],
            membership=membership and conv.kind in (ConvKind.PUBLIC, ConvKind.PRIVATE),
            force_ends=largest[i] and counts[i] >= 2 and day_count >= 2,
        )
        for i, conv in enumerate(conversations)
    ]


def build_workspace(params: GenerationParams) -> Workspace:
    rng = random.Random(params.seed)
    user_count = params.users

    # Users (about 2% deleted, still listed).
    taken_names: set[str] = set()
    deleted = set(rng.sample(range(user_count), percent_count(2, user_count)))
    users: list[User] = []
    for i in range(user_count):
        first = FIRST_NAMES[rng.randrange(len(FIRST_NAMES))]
        last = LAST_NAMES[rng.randrange(len(LAST_NAMES))]
        name = _unique(rng, taken_names, f"{first}.{last}".lower())
        users.append(User(f"U{i + 1:08X}", name, f"{first} {last}", i in deleted))
    bots = [
        Bot(f"B{i + 1:08X}", BOT_NAMES[i % len(BOT_NAMES)], f"A{i + 1:08X}")
        for i in range(BOT_COUNT)
    ]

    # Conversation type mix, then rank order (rank 1 is a public channel).
    kind_counts = apportion(params.conversations, TYPE_MIX)
    kinds_in_order = (ConvKind.PUBLIC, ConvKind.PRIVATE, ConvKind.DM, ConvKind.MPIM)
    slots = [kind for kind, c in zip(kinds_in_order, kind_counts, strict=True) for _ in range(c)]
    rng.shuffle(slots)
    first_public = slots.index(ConvKind.PUBLIC)
    slots[0], slots[first_public] = slots[first_public], slots[0]

    counts = zipf_counts(params.messages, params.conversations)
    start_epoch = day_epoch(params.days, 0)
    taken_ids: set[str] = set()
    taken_channel_names: set[str] = set()
    conversations: list[Conversation] = []
    sub_seeds: list[int] = []
    prefix = {ConvKind.PUBLIC: "C", ConvKind.PRIVATE: "G", ConvKind.DM: "D", ConvKind.MPIM: "G"}
    for rank, kind in enumerate(slots, start=1):
        conv_id = prefix[kind] + f"{rng.getrandbits(32):08X}"
        while conv_id in taken_ids:
            conv_id = prefix[kind] + f"{rng.getrandbits(32):08X}"
        taken_ids.add(conv_id)
        if kind in (ConvKind.PUBLIC, ConvKind.PRIVATE):
            adjective = ADJECTIVES[rng.randrange(len(ADJECTIVES))]
            noun = NOUNS[rng.randrange(len(NOUNS))]
            base = (
                f"{adjective}-{noun}" if kind is ConvKind.PUBLIC else f"{noun}-{adjective}-private"
            )
            name = _unique(rng, taken_channel_names, base)
            size = rng.randint(3, min(user_count, 40 if rank == 1 else 12))
            member_idx = sorted(rng.sample(range(user_count), size))
            folder = name
        elif kind is ConvKind.DM:
            member_idx = sorted(rng.sample(range(user_count), 2))
            name = conv_id
            folder = conv_id
        else:
            member_idx = sorted(rng.sample(range(user_count), rng.randint(3, 5)))
            name = "mpdm-" + "--".join(users[i].name for i in member_idx) + "-1"
            folder = conv_id
        created = start_epoch - rng.randrange(30 * 86400, 400 * 86400)
        conversations.append(
            Conversation(
                id=conv_id,
                kind=kind,
                name=name,
                folder=folder,
                members=tuple(users[i].id for i in member_idx),
                rank=rank,
                created=created,
            )
        )
        sub_seeds.append(rng.getrandbits(62))

    segments = build_segments(
        conversations,
        counts,
        sub_seeds,
        params.profile,
        day_offset=0,
        day_count=params.days,
        membership=True,
    )
    return Workspace(
        params=params,
        team_id=team_id_for(params.seed),
        users=users,
        bots=bots,
        conversations=conversations,
        segments=segments,
    )
