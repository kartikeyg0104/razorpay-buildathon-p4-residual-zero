"""Wilson, per-seed range, kappa. No pooled-plus-spread API."""

from __future__ import annotations

from fractions import Fraction

from eval.stats import ProportionEstimate, cohens_kappa, pooled_with_per_seed, wilson_interval


def test_wilson_contains_pooled():
    for suc, n in ((0, 10), (10, 10), (0, 50), (1, 50), (3, 7)):
        lo, hi = wilson_interval(suc, n)
        p = suc / n
        assert lo - 1e-12 <= p <= hi + 1e-12


def test_pooled_lies_within_per_seed_range():
    est = pooled_with_per_seed(((1, 10), (2, 10), (0, 10)))
    assert est.seed_min <= est.pooled <= est.seed_max


def test_no_api_returns_pooled_plus_seed_spread():
    names = set(ProportionEstimate.model_fields)
    assert "pooled_plus_spread" not in names
    assert not hasattr(ProportionEstimate, "plus_minus")
    est = pooled_with_per_seed(((0, 5), (1, 5)))
    assert "wilson_lo" in ProportionEstimate.model_fields
    assert "seed_min" in ProportionEstimate.model_fields
    # Structurally unavailable: no method combining the two.
    assert not any("spread" in n for n in dir(est) if not n.startswith("_"))


def test_kappa_on_hand_worked_example():
    # 6 items, 3 categories. Hand: 4 agreements, pe = 0.5, kappa = 0.5? Let's compute:
    # A: C C F F G G
    # B: C F C F G G
    # agree on 4 of 6 (positions 1,4,5,6) -> Po=4/6=2/3
    # CA: C2 F2 G2; CB: C2 F2 G2; Pe = 3*(1/3*1/3)=1/3
    # k = (2/3 - 1/3) / (1 - 1/3) = (1/3)/(2/3) = 0.5
    a = ["CLEARED", "CLEARED", "FLAGGED", "FLAGGED", "GAVE_UP", "GAVE_UP"]
    b = ["CLEARED", "FLAGGED", "CLEARED", "FLAGGED", "GAVE_UP", "GAVE_UP"]
    assert abs(cohens_kappa(a, b) - 0.5) < 1e-9
