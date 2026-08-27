"""Wilson intervals, per-seed range, Cohen's kappa. Floats live here, not on the money path."""

from __future__ import annotations

import math
from collections import Counter
from fractions import Fraction
from typing import Sequence

from pydantic import BaseModel, ConfigDict

_STRICT = ConfigDict(frozen=True, extra="forbid")


class ProportionEstimate(BaseModel):
    model_config = _STRICT

    pooled: Fraction
    wilson_lo: float
    wilson_hi: float
    per_seed: tuple[Fraction, ...]
    seed_min: Fraction
    seed_max: Fraction
    n: int


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval. Used because the most important number lives near 0 (§9.4)."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    rad = (z / denom) * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))
    return (max(0.0, centre - rad), min(1.0, centre + rad))


def pooled_with_per_seed(per_seed_counts: Sequence[tuple[int, int]]) -> ProportionEstimate:
    """Pool across seeds; Wilson on the pooled proportion; per-seed range carried separately."""
    suc = sum(s for s, _n in per_seed_counts)
    tot = sum(n for _s, n in per_seed_counts)
    pooled = Fraction(suc, tot) if tot else Fraction(0, 1)
    lo, hi = wilson_interval(suc, tot) if tot else (0.0, 1.0)
    per = tuple(Fraction(s, n) if n else Fraction(0, 1) for s, n in per_seed_counts)
    return ProportionEstimate(
        pooled=pooled,
        wilson_lo=lo,
        wilson_hi=hi,
        per_seed=per,
        seed_min=min(per) if per else Fraction(0, 1),
        seed_max=max(per) if per else Fraction(0, 1),
        n=tot,
    )


def cohens_kappa(rater_a: Sequence[str], rater_b: Sequence[str]) -> float:
    """Pairwise Cohen's kappa over the three-category disposition vocabulary (D18)."""
    if len(rater_a) != len(rater_b) or not rater_a:
        raise ValueError("kappa needs equal-length non-empty ratings")
    n = len(rater_a)
    agree = sum(1 for a, b in zip(rater_a, rater_b) if a == b)
    p_o = agree / n
    ca, cb = Counter(rater_a), Counter(rater_b)
    p_e = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def wilson_at_n50_example() -> tuple[float, float]:
    """§9.4 small-sample interval, computed rather than copied from the spec."""
    return wilson_interval(0, 50)
