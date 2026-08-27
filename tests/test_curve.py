"""Risk-coverage curve: monotone, derived threshold, observable inputs."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from residual_zero.config import load_solver_config
from residual_zero.ordering import TERM_NAMES, ordering_score

from eval.curve import CurvePoint, ScoredCredit, risk_coverage_curve, threshold_at_error_budget


def test_curve_is_monotone_in_threshold():
    credits = [
        ScoredCredit("a", ("x",), "0.900000", True, ("x",)),
        ScoredCredit("b", ("y",), "0.500000", True, ("z",)),
        ScoredCredit("c", ("w",), "0.100000", True, ("w",)),
    ]
    curve = risk_coverage_curve(credits)
    # Descending threshold: coverage must be non-decreasing.
    for i in range(len(curve) - 1):
        if curve[i].threshold >= curve[i + 1].threshold:
            assert curve[i].coverage <= curve[i + 1].coverage


def test_threshold_is_derived_not_configured():
    credits = [
        ScoredCredit("a", ("x",), "0.900000", True, ("x",)),
        ScoredCredit("b", ("y",), "0.400000", True, ("WRONG",)),
    ]
    curve = risk_coverage_curve(credits)
    t_strict, _ = threshold_at_error_budget(curve, Fraction(0, 1))
    t_loose, _ = threshold_at_error_budget(curve, Fraction(1, 1))
    assert t_strict != t_loose or t_strict == "1.000000"
    cfg = load_solver_config()
    # Hand-set threshold without a source is rejected by the loader; current config is TBD or sourced.
    if cfg.autonomy.threshold is not None:
        assert cfg.autonomy.threshold_source is not None
    raw = Path("config/solver.yaml").read_text(encoding="utf-8")
    assert "threshold_source" in raw


def test_curve_inputs_are_observable():
    assert TERM_NAMES == ("slack", "margin", "pool", "tier", "cross_window", "size")
    assert "confidence" not in ordering_score.__code__.co_varnames
