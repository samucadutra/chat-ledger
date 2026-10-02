"""Anomaly target selection for one conversation segment (spec decision "Anomaly selection").

Counts per conversation come from the plan quotas; targets are sampled without replacement
with the conversation's own PRNG. Each base record carries at most one anomaly.
"""

from __future__ import annotations

import random
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field

from chatledger_core.domain.generator.plan import Quotas
from chatledger_core.domain.generator.rates import AnomalyType

_EVENT_KINDS = (AnomalyType.EDIT, AnomalyType.DELETE, AnomalyType.EDIT_AFTER_DELETE)
_TS_KINDS = (AnomalyType.MISSING_TS, AnomalyType.INVALID_TS, AnomalyType.TS_OUT_OF_RANGE)
_PLAIN_KINDS = (
    AnomalyType.UNKNOWN_SUBTYPE,
    AnomalyType.SCHEMA_VIOLATION,
    AnomalyType.UNRESOLVED_USER,
)


@dataclass(frozen=True)
class EventPlan:
    """An edit/delete event to inject; ``target`` is ``None`` for unknown-target events."""

    kind: AnomalyType
    target: int | None
    day: int  # index into the segment's active-day list


@dataclass
class AnomalyPlan:
    records: dict[int, AnomalyType] = field(default_factory=dict)
    events: list[EventPlan] = field(default_factory=list)
    malformed_days: set[int] = field(default_factory=set)
    empty_days: list[int] = field(default_factory=list)  # relative day indices without a file


def select_anomalies(
    rng: random.Random,
    quotas: Quotas,
    *,
    messages: int,
    day_start: Sequence[int],
    active_days: Sequence[int],
    day_count: int,
    replies: Sequence[int],
    parents: set[int],
    bots: set[int],
    file_records: Sequence[int],
) -> AnomalyPlan:
    plan = AnomalyPlan()
    wanted = quotas.anomalies
    if not wanted:
        return plan
    taken = plan.records

    def day_of(index: int) -> int:
        return bisect_right(day_start, index) - 1

    def from_pool(kind: AnomalyType, pool: Sequence[int]) -> None:
        available = [g for g in pool if g not in taken]
        for g in rng.sample(available, min(wanted.get(kind, 0), len(available))):
            taken[g] = kind

    from_pool(AnomalyType.ORPHAN_REPLY, replies)
    from_pool(AnomalyType.UNRESOLVED_FILE, file_records)
    from_pool(AnomalyType.BOT_NO_IDENTITY, sorted(bots))

    permutation = list(range(messages))
    rng.shuffle(permutation)
    targeted: dict[int, AnomalyType] = {}  # edit/delete targets: events, not record mutations

    def from_permutation(
        kind: AnomalyType, excluded: set[int], into: dict[int, AnomalyType]
    ) -> None:
        need = wanted.get(kind, 0)
        for g in permutation:
            if need <= 0:
                break
            if g in taken or g in targeted or g in excluded:
                continue
            into[g] = kind
            need -= 1

    for kind in _EVENT_KINDS:
        from_permutation(kind, set(), targeted)
    for kind in _PLAIN_KINDS:
        from_permutation(kind, bots if kind is AnomalyType.UNRESOLVED_USER else set(), taken)
    for kind in _TS_KINDS:
        from_permutation(kind, parents, taken)

    for g, kind in sorted(targeted.items()):
        plan.events.append(EventPlan(kind, g, day_of(g)))

    for kind in (AnomalyType.EDIT_TARGET_MISSING, AnomalyType.DELETE_TARGET_MISSING):
        for _ in range(wanted.get(kind, 0)):
            plan.events.append(EventPlan(kind, None, rng.randrange(len(active_days))))

    dirty = {day_of(g) for g in taken} | {day_of(g) for g in targeted}
    dirty |= {e.day for e in plan.events}
    clean = [d for d in range(len(active_days)) if d not in dirty]
    wanted_malformed = min(wanted.get(AnomalyType.MALFORMED_JSON, 0), len(clean))
    plan.malformed_days = set(rng.sample(clean, wanted_malformed))
    active_set = set(active_days)
    free = [d for d in range(day_count) if d not in active_set]
    plan.empty_days = sorted(
        rng.sample(free, min(wanted.get(AnomalyType.EMPTY_FILE, 0), len(free)))
    )
    return plan
