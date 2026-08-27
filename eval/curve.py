"""§9.5 risk-coverage curve. Threshold is read off the curve, never hand-picked."""

from __future__ import annotations

from fractions import Fraction
from typing import NamedTuple, Sequence


class CurvePoint(NamedTuple):
    threshold: str
    coverage: Fraction
    error: Fraction | None
    n_cleared: int
    n_cleared_wrong: int


class ScoredCredit(NamedTuple):
    bank_credit_id: str
    member_ids: tuple[str, ...]
    score: str
    eligible: bool
    truth_ids: tuple[str, ...]


def risk_coverage_curve(credits: Sequence[ScoredCredit]) -> tuple[CurvePoint, ...]:
    """Order by ordering_score descending, sweep unique thresholds, coverage/error at each."""
    n = len(credits)
    if n == 0:
        return ()
    thresholds = sorted({c.score for c in credits}, reverse=True)
    # Also include a point that clears nothing.
    if "1.000001" not in thresholds:
        thresholds = ["1.000001"] + thresholds
    points: list[CurvePoint] = []
    for thr in thresholds:
        cleared = [c for c in credits if c.eligible and c.score >= thr]
        n_cleared = len(cleared)
        n_wrong = sum(1 for c in cleared if tuple(sorted(c.member_ids)) != tuple(sorted(c.truth_ids)))
        coverage = Fraction(n_cleared, n)
        error = Fraction(n_wrong, n_cleared) if n_cleared else None
        points.append(CurvePoint(thr, coverage, error, n_cleared, n_wrong))
    return tuple(points)


def threshold_at_error_budget(
    curve: Sequence[CurvePoint], error_budget: Fraction
) -> tuple[str, CurvePoint]:
    """Largest coverage whose error is <= budget. If nothing clears, the no-clear point."""
    if not curve:
        empty = CurvePoint("1.000000", Fraction(0, 1), None, 0, 0)
        return empty.threshold, empty
    feasible = [
        p for p in curve
        if p.n_cleared == 0 or (p.error is not None and p.error <= error_budget)
    ]
    if not feasible:
        # Strictest point (highest threshold).
        chosen = max(curve, key=lambda p: p.threshold)
        return chosen.threshold, chosen
    chosen = max(feasible, key=lambda p: (p.coverage, p.threshold))
    # Publish the six-decimal operating threshold. The sweep sentinel 1.000001 means "never".
    operating = "1.000000" if chosen.threshold == "1.000001" else chosen.threshold
    return operating, chosen
