"""Largest-remainder apportionment with per-slot caps (integer arithmetic only)."""

from __future__ import annotations

from collections.abc import Sequence


def apportion(total: int, weights: Sequence[int], caps: Sequence[int] | None = None) -> list[int]:
    """Split ``total`` over slots proportionally to ``weights`` (largest remainder).

    ``caps`` bound each slot; capped slots are filled first and the rest is re-apportioned
    over the remaining slots. The sum equals ``min(total, sum(caps))``. Ties go to the lower
    index, so the result is a pure function of the inputs.
    """
    n = len(weights)
    result = [0] * n
    room = list(caps) if caps is not None else [max(total, 0)] * n
    active = [i for i in range(n) if room[i] > 0 and weights[i] > 0]
    remaining = min(max(total, 0), sum(room[i] for i in active))
    while remaining > 0 and active:
        weight_sum = sum(weights[i] for i in active)
        quotients = {}
        remainders = {}
        for i in active:
            quotients[i], remainders[i] = divmod(remaining * weights[i], weight_sum)
        capped = [i for i in active if quotients[i] >= room[i] - result[i]]
        if capped:
            for i in capped:
                take = room[i] - result[i]
                result[i] += take
                remaining -= take
            active = [i for i in active if i not in capped]
            continue
        for i in active:
            result[i] += quotients[i]
        leftover = remaining - sum(quotients.values())
        for i in sorted(active, key=lambda idx: (-remainders[idx], idx))[:leftover]:
            result[i] += 1
        remaining = 0
    return result
