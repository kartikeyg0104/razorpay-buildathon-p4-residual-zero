"""Observable ordering score. Weighted geometric mean of six terms. NEVER model confidence (NN-4)."""

from __future__ import annotations

import math
from typing import Sequence

from residual_zero.config import SolverConfig
from residual_zero.models import ResolutionTier, render_score
from residual_zero.semantic.tiers import Resolution
from residual_zero.solver.enumerate import SolveResult

TERM_NAMES = ("slack", "margin", "pool", "tier", "cross_window", "size")


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _s_tier(resolutions: Sequence[Resolution]) -> float:
    if not resolutions:
        return 1.0
    max_tier = max(r.tier for r in resolutions)
    if max_tier == ResolutionTier.UNRESOLVED:
        return 0.0
    if max_tier == ResolutionTier.MODEL:
        return 0.4
    if max_tier == ResolutionTier.FUZZY:
        return 0.7
    return 1.0


def score_terms(
    solve: SolveResult,
    resolutions: Sequence[Resolution],
    cross_window_members: int,
    member_count: int,
    cfg: SolverConfig,
) -> dict[str, float]:
    """The six observables, each in [0, 1], higher = safer. No confidence input."""
    epsilon = cfg.search.epsilon_rupees
    denom = (epsilon + 1) * 1.0
    slack = solve.slack_rupees
    if slack is None:
        slack = epsilon
    margin = solve.margin_rupees
    if margin is None:
        margin = 0
    s_slack = _clamp01(1.0 - min(1.0, abs(slack) / denom))
    s_margin = _clamp01(min(1.0, abs(margin) / denom))
    s_pool = _clamp01(1.0 - min(1.0, solve.pool_size / (cfg.search.max_pool * 1.0)))
    s_tier = _s_tier(resolutions)
    s_xwin = _clamp01(
        1.0 - min(1.0, cross_window_members / (max(1, member_count) * 1.0))
    )
    s_size = _clamp01(
        1.0 - min(1.0, member_count / (cfg.ordering_score.expected_max_members * 1.0))
    )
    return {
        "slack": s_slack,
        "margin": s_margin,
        "pool": s_pool,
        "tier": s_tier,
        "cross_window": s_xwin,
        "size": s_size,
    }


def ordering_score(
    solve: SolveResult,
    resolutions: Sequence[Resolution],
    cross_window_members: int,
    member_count: int,
    cfg: SolverConfig,
) -> float:
    """Unweighted geometric mean of six observable terms (D14). NEVER model confidence (NN-4).

    Rendered as a fixed six-decimal string everywhere it is compared or published.
    """
    terms = score_terms(solve, resolutions, cross_window_members, member_count, cfg)
    values = tuple(terms[name] for name in TERM_NAMES)
    if any(v <= 0.0 for v in values):
        return 0.0
    return math.prod(values) ** (1.0 / 6.0)


def render_ordering_score(score: float) -> str:
    return render_score(score)
