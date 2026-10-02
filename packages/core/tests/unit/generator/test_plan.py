from __future__ import annotations

import re
from collections import Counter

from chatledger_core.domain.generator.params import validate_params
from chatledger_core.domain.generator.plan import (
    END_DATE,
    ConvKind,
    build_workspace,
    day_date,
    day_epoch,
    team_id_for,
    zipf_counts,
)


def test_conversation_mix_largest_remainder() -> None:
    def mix(conversations: int) -> list[int]:
        params = validate_params(
            seed=3,
            preset="custom",
            profile="clean",
            messages=max(1_000, conversations * 20),
            conversations=conversations,
        )
        kinds = Counter(c.kind for c in build_workspace(params).conversations)
        return [kinds[k] for k in (ConvKind.PUBLIC, ConvKind.PRIVATE, ConvKind.DM, ConvKind.MPIM)]

    assert mix(50) == [30, 8, 10, 2]
    assert mix(500) == [300, 75, 100, 25]
    assert mix(1)[0] == 1


def test_zipf_allocation_small() -> None:
    counts = zipf_counts(10_000, 50)
    assert sum(counts) == 10_000
    assert min(counts) >= 1
    assert counts[0] / 10_000 > 0.05
    weights = [k**-1.1 for k in range(1, 51)]
    total = sum(weights)
    for k, value in enumerate(sorted(counts, reverse=True), start=1):
        assert abs(value - 10_000 * weights[k - 1] / total) <= 1


def test_zipf_every_conversation_has_a_message() -> None:
    counts = zipf_counts(2_000, 1_000)
    assert sum(counts) == 2_000 and min(counts) >= 1


def test_workspace_shape() -> None:
    ws = build_workspace(validate_params(seed=42, preset="small", profile="default"))
    assert len(ws.users) == 40 and len({u.id for u in ws.users}) == 40
    assert sum(u.deleted for u in ws.users) == 1  # round(2% of 40)
    assert ws.conversations[0].kind is ConvKind.PUBLIC and ws.conversations[0].rank == 1
    assert len({c.id for c in ws.conversations}) == 50
    assert len({c.folder for c in ws.conversations}) == 50
    assert re.fullmatch(r"T[0-9A-F]{8}", ws.team_id)
    assert ws.team_id == team_id_for(42)
    for conv in ws.conversations:
        if conv.kind is ConvKind.DM:
            assert len(conv.members) == 2
        assert set(conv.members) <= {u.id for u in ws.users}
    assert sum(s.messages for s in ws.segments) == 10_000


def test_plan_is_deterministic_and_seed_sensitive() -> None:
    a = build_workspace(validate_params(seed=7, preset="small", profile="default"))
    b = build_workspace(validate_params(seed=7, preset="small", profile="default"))
    c = build_workspace(validate_params(seed=8, preset="small", profile="default"))
    assert [s.sub_seed for s in a.segments] == [s.sub_seed for s in b.segments]
    assert [s.sub_seed for s in a.segments] != [s.sub_seed for s in c.segments]
    assert a.team_id != c.team_id


def test_day_file_density_below_entry_limit() -> None:
    ws = build_workspace(validate_params(seed=42, preset="large", profile="default"))
    assert sum(s.active_days for s in ws.segments) <= 150_000
    assert sum(s.messages for s in ws.segments) == 1_000_000


def test_quota_totals_are_exact() -> None:
    ws = build_workspace(validate_params(seed=42, preset="small", profile="default"))
    quotas = [s.quotas for s in ws.segments]
    assert sum(q.replies for q in quotas) == 2_000
    assert sum(q.broadcasts for q in quotas) == 60
    assert sum(q.bots for q in quotas) == 200
    assert sum(q.reactions for q in quotas) == 800
    assert sum(q.files for q in quotas) == 400
    assert sum(q.mentions for q in quotas) == 1_500
    assert sum(q.links for q in quotas) == 1_000


def test_fixed_calendar() -> None:
    assert day_date(90, 89) == END_DATE
    assert day_date(90, 0).isoformat() == "2025-10-03"
    assert day_date(90, 90).isoformat() == "2026-01-01"
    assert day_epoch(90, 89) - day_epoch(90, 88) == 86_400
    assert day_epoch(90, 89) == 1_767_139_200  # 2025-12-31T00:00:00Z
