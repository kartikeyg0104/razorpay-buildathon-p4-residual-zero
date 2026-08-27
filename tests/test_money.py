"""Money is integer paise and there is exactly one rounding rule (NN-1, ADR-5)."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from residual_zero.money import (
    apply_bps,
    format_rupees,
    is_whole_rupee,
    rounding_bound_rupees,
    round_half_up_div,
    subrupee_count,
    to_rupee_units,
)


def test_round_half_up_div_matches_exact_halves():
    """Halves round toward +inf for both signs, and near-halves round the obvious way."""
    assert round_half_up_div(15, 10) == 2      # 1.5 -> 2
    assert round_half_up_div(-15, 10) == -1    # -1.5 -> -1, i.e. toward +inf
    assert round_half_up_div(5, 10) == 1       # 0.5 -> 1
    assert round_half_up_div(-5, 10) == 0      # -0.5 -> 0
    assert round_half_up_div(14, 10) == 1
    assert round_half_up_div(-14, 10) == -1
    assert round_half_up_div(16, 10) == 2
    assert round_half_up_div(-16, 10) == -2
    assert round_half_up_div(0, 10) == 0


def test_round_half_up_div_rejects_nonpositive_denominator():
    """A negative denominator would silently invert the rounding direction."""
    with pytest.raises(ValueError):
        round_half_up_div(1, 0)
    with pytest.raises(ValueError):
        round_half_up_div(1, -10)


@given(st.integers(min_value=-10**12, max_value=10**12))
def test_to_rupee_units_error_bounded_by_half(amount_paise: int):
    """|100 * r(a) - a| <= 50 for every a. This is the per-item half-rupee bound in D6."""
    assert abs(100 * to_rupee_units(amount_paise) - amount_paise) <= 50


@given(st.integers(min_value=-10**12, max_value=10**12))
def test_to_rupee_units_agrees_with_the_single_rounding_rule(amount_paise: int):
    """r(a) is the same rule as round_half_up_div(a, 100); there is only one rounding rule."""
    assert to_rupee_units(amount_paise) == round_half_up_div(amount_paise, 100)


@given(st.integers(min_value=-10**10, max_value=10**10))
def test_whole_rupee_amounts_have_zero_rounding_error(rupees: int):
    """A whole-rupee amount maps onto the search axis with error exactly zero.

    This is the observation the whole tolerance derivation rests on: only sub-rupee members
    contribute to the accumulated bound.
    """
    amount_paise = rupees * 100
    assert is_whole_rupee(amount_paise)
    assert 100 * to_rupee_units(amount_paise) == amount_paise


def test_subrupee_amounts_are_counted():
    """subrupee_count is m in D6's bound."""
    assert subrupee_count([100, 200, -300]) == 0
    assert subrupee_count([101, 200, -300]) == 1
    assert subrupee_count([101, 250, -399]) == 3
    assert subrupee_count([]) == 0


def test_rounding_bound_is_floor_of_half_m_plus_one():
    """floor((m+1)/2), the D6 worst-case rupee-axis error."""
    assert rounding_bound_rupees(0) == 0
    assert rounding_bound_rupees(1) == 1
    assert rounding_bound_rupees(12) == 6
    assert rounding_bound_rupees(13) == 7      # the Phase 1 profile's bound -> epsilon_rupees 7
    assert rounding_bound_rupees(400) == 200   # the unusable worst case at MAX_POOL, per D6
    with pytest.raises(ValueError):
        rounding_bound_rupees(-1)


def test_apply_bps_is_exact_for_representative_rates():
    """apply_bps agrees with hand-computed integer arithmetic on a fixed table."""
    # 2% of Rs 1,000.00 == Rs 20.00
    assert apply_bps(100_000, 200) == 2_000
    # 18% GST on a Rs 20.00 fee == Rs 3.60
    assert apply_bps(2_000, 1800) == 360
    # Rounding: 2% of Rs 12.34 = 24.68 paise -> 25 paise, half up
    assert apply_bps(1_234, 200) == 25
    # Exact half rounds toward +inf: 2% of Rs 1.25 = 2.5 paise -> 3
    assert apply_bps(125, 200) == 3
    # Signed amounts round the same rule: -2.5 paise -> -2
    assert apply_bps(-125, 200) == -2
    assert apply_bps(0, 1800) == 0
    assert apply_bps(100_000, 0) == 0


def test_format_rupees_uses_indian_grouping():
    """Display only, and grouped the way an Indian finance team reads it."""
    assert format_rupees(-482_150) == "-4,821.50"
    assert format_rupees(50_120_000) == "5,01,200.00"
    assert format_rupees(48_215_000) == "4,82,150.00"
    assert format_rupees(0) == "0.00"
    assert format_rupees(5) == "0.05"
    assert format_rupees(100) == "1.00"
    assert format_rupees(-100) == "-1.00"
    assert format_rupees(123_456_789) == "12,34,567.89"      # 1234567.89 rupees
    assert format_rupees(12_345_678_900) == "12,34,56,789.00"  # 123456789 rupees


@given(st.integers(min_value=-10**12, max_value=10**12))
def test_format_rupees_round_trips(amount_paise: int):
    """The rendered figure parses back to the same paise, which is what makes a proof checkable."""
    rendered = format_rupees(amount_paise)
    sign = -1 if rendered.startswith("-") else 1
    body = rendered.lstrip("-")
    rupees, paise = body.split(".")
    assert sign * (int(rupees.replace(",", "")) * 100 + int(paise)) == amount_paise
