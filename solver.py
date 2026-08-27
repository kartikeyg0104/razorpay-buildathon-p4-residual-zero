"""
Residual Zero — signed subset-sum solver with tolerance and uniqueness detection.

Reference implementation for the Track 04 build spec, §5.6.

Technique: bitset dynamic program over a shifted integer axis, using Python's
arbitrary-precision ints as the bitset. Handles signed amounts (inflows positive,
deductions negative) uniformly, detects whether a decomposition is UNIQUE, and
enumerates solutions in O(k * n) after the DP rather than by exponential search.

Validated against brute-force enumeration on 1,100 randomised signed instances
(reachability + uniqueness + tolerance). See test_solver.py.

All amounts are integers. Run the search at RUPEE granularity; re-verify the
returned subset at PAISE granularity in verify.py. At paise the axis is ~100x
wider and per-credit solve time goes from tens of milliseconds to seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class Uniqueness(str, Enum):
    UNIQUE = "UNIQUE"            # exactly one decomposition -> may auto-clear
    AMBIGUOUS = "AMBIGUOUS"      # two or more -> refuse, route to exception
    NONE_FOUND = "NONE_FOUND"    # nothing within tolerance -> diagnose near-miss
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


@dataclass(frozen=True)
class SolveResult:
    uniqueness: Uniqueness
    matched_total: int | None          # the reachable sum actually hit
    members: tuple[int, ...]           # indices into `amounts`, empty unless UNIQUE
    alternates: int                    # solutions found, capped at `cap`
    nearest_total: int | None          # for NONE_FOUND: closest reachable sum
    nearest_delta: int | None          # nearest_total - target; drives diagnosis


def solve(
    amounts: Sequence[int],
    target: int,
    tol: int = 0,
    cap: int = 2,
    max_pool: int = 400,
) -> SolveResult:
    """
    Find the subset of `amounts` whose signed sum equals `target` within `tol`.

    Returns UNIQUE only when exactly one such subset exists. Refusing on
    ambiguity is a correctness feature, not a limitation: a credit explainable
    by two different sets of transactions has not been reconciled.
    """
    n = len(amounts)
    if n > max_pool:
        return SolveResult(Uniqueness.BUDGET_EXCEEDED, None, (), 0, None, None)

    NEG = sum(a for a in amounts if a < 0)   # non-positive
    POS = sum(a for a in amounts if a > 0)   # non-negative

    def _in_range(s: int) -> bool:
        return NEG <= s <= POS

    # Bounds guard. Without it, a target outside [NEG, POS] produces a negative
    # shift count and a crash instead of a clean NONE_FOUND. This fires the first
    # time a corrupted credit exceeds its candidate pool's total.
    if target + tol < NEG or target - tol > POS:
        return SolveResult(Uniqueness.NONE_FOUND, None, (), 0, None, None)

    # Reachability DP. Bit k of `reach` means "sum NEG + k is reachable".
    # Empty subset has sum 0, i.e. bit index -NEG.
    reach = 1 << (-NEG)
    snapshots = [reach]
    for a in amounts:
        reach |= (reach << a) if a >= 0 else (reach >> -a)
        snapshots.append(reach)

    def _bit(mask: int, s: int) -> bool:
        return _in_range(s) and bool((mask >> (s - NEG)) & 1)

    hits = [t for t in range(target - tol, target + tol + 1) if _bit(reach, t)]

    if not hits:
        nearest = _nearest_reachable(reach, target, NEG, POS)
        return SolveResult(
            Uniqueness.NONE_FOUND, None, (), 0,
            nearest, None if nearest is None else nearest - target,
        )

    # Prefer the exact target when it is reachable, else the closest hit.
    matched = target if target in hits else min(hits, key=lambda t: abs(t - target))

    solutions: list[tuple[int, ...]] = []

    def _backtrack(i: int, s: int, chosen: list[int]) -> None:
        if len(solutions) >= cap:
            return
        if i == 0:
            if s == 0:
                solutions.append(tuple(reversed(chosen)))
            return
        a = amounts[i - 1]
        # Every branch we take is guaranteed to terminate in a real solution,
        # because reachability was precomputed. Enumeration is O(k * n).
        if _bit(snapshots[i - 1], s - a):
            _backtrack(i - 1, s - a, chosen + [i - 1])
        if len(solutions) >= cap:
            return
        if _bit(snapshots[i - 1], s):
            _backtrack(i - 1, s, chosen)

    _backtrack(n, matched, [])

    if len(solutions) == 1:
        return SolveResult(Uniqueness.UNIQUE, matched, solutions[0], 1, None, None)
    return SolveResult(Uniqueness.AMBIGUOUS, matched, (), len(solutions), None, None)


def _nearest_reachable(reach: int, target: int, NEG: int, POS: int) -> int | None:
    """Closest reachable sum to `target`. Its delta is the primary diagnostic
    signal for the exception engine (§5.10): a delta that is a clean percentage
    of pool gross implicates withholding or an un-itemised fee; a delta equal to
    one pool member implicates a missing or duplicated record; a delta under
    100 paise implicates rounding."""
    span = max(target - NEG, POS - target)
    for d in range(1, span + 1):
        for cand in (target - d, target + d):
            if NEG <= cand <= POS and (reach >> (cand - NEG)) & 1:
                return cand
    return None
