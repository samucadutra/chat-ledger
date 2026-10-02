"""Overlapping re-delivery (spec A17-A18).

The re-delivery reproduces the base export's workspace (same team, users, conversations and
sub-seeds, so the day files of the overlap window are byte-identical) and extends it by 30 days
of new records drawn from the new seed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from chatledger_core.domain.generator.apportion import apportion
from chatledger_core.domain.generator.params import GenerationParams
from chatledger_core.domain.generator.plan import (
    SegmentPlan,
    Workspace,
    build_segments,
    build_workspace,
)
from chatledger_core.domain.generator.rates import AnomalyType

NEW_DAYS = 30
DEFAULT_DAYS_PCT = 30
DAYS_PCT_MIN = 1
DAYS_PCT_MAX = 100


def window_day_count(days: int, days_pct: int) -> int:
    """``round_half_up(days x pct / 100)``, at least one day."""
    return max(1, (days * days_pct + 50) // 100)


@dataclass
class OverlapPlan:
    base: Workspace
    new_segments: list[SegmentPlan]
    window_start: int  # first window day (absolute index); the window runs to ``days - 1``
    window_days: int
    days_pct: int
    base_seed: int

    @property
    def total_days(self) -> int:
        return self.window_days + NEW_DAYS


def build_overlap(params: GenerationParams, base_seed: int, days_pct: int) -> OverlapPlan:
    """Plan a re-delivery of the export with ``base_seed`` and the invocation's parameters."""
    base = build_workspace(replace(params, seed=base_seed))
    window_days = window_day_count(params.days, days_pct)
    total_new = (params.messages * NEW_DAYS + params.days // 2) // params.days
    base_counts = [seg.messages for seg in base.segments]
    counts = apportion(total_new, base_counts)
    rng = random.Random(params.seed * 1_000_003 + 17)
    sub_seeds = [rng.getrandbits(62) for _ in base.conversations]
    new_segments = build_segments(
        base.conversations,
        counts,
        sub_seeds,
        params.profile,
        day_offset=params.days,
        day_count=NEW_DAYS,
        membership=False,
    )
    return OverlapPlan(
        base=base,
        new_segments=new_segments,
        window_start=params.days - window_days,
        window_days=window_days,
        days_pct=days_pct,
        base_seed=base_seed,
    )


def duplicate_records(
    conversation_id: str, source_file: str, record_ts: list[str | None]
) -> list[tuple[str, str, str | None, str, int | None]]:
    """One ``duplicate_source`` entry per record of a day file inside the overlap window."""
    kind = AnomalyType.DUPLICATE_SOURCE.value
    return [(kind, conversation_id, ts, source_file, index) for index, ts in enumerate(record_ts)]
