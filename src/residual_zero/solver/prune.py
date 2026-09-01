"""Mathematically safe candidate elimination. Never a heuristic."""

from __future__ import annotations

from typing import Sequence


def prune_indices(
    amounts_rupees: Sequence[int],
    target_rupees: int,
    epsilon_rupees: int,
) -> tuple[int, ...]:
    """Indices that can appear in some subset whose sum lies in [target-eps, target+eps].

    Item ``i`` with amount ``a`` is dropped only when every subset that contains it
    is bounded outside the window: after taking ``a``, the remaining positives and
    negatives cannot reach ``[target-eps, target+eps]``. That bound is conservative
    (gaps inside the interval are ignored), so a feasible item is never removed.

    Repeated until a fixpoint so each drop tightens the residual bounds.
    """
    if epsilon_rupees < 0:
        raise ValueError("epsilon must be non-negative")
    n = len(amounts_rupees)
    if n == 0:
        return ()
    amounts = tuple(int(a) for a in amounts_rupees)
    keep = list(range(n))
    lo_w = target_rupees - epsilon_rupees
    hi_w = target_rupees + epsilon_rupees
    changed = True
    while changed:
        changed = False
        pos = 0
        neg = 0
        for i in keep:
            a = amounts[i]
            if a > 0:
                pos += a
            elif a < 0:
                neg += a
        nxt: list[int] = []
        for i in keep:
            a = amounts[i]
            others_pos = pos - a if a > 0 else pos
            others_neg = neg - a if a < 0 else neg
            reach_lo = a + others_neg
            reach_hi = a + others_pos
            if reach_hi < lo_w or reach_lo > hi_w:
                changed = True
                continue
            nxt.append(i)
        keep = nxt
    return tuple(keep)


def distinct_amount_count(amounts_rupees: Sequence[int]) -> int:
    return len(set(int(a) for a in amounts_rupees))
