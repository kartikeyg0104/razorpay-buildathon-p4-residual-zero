"""Regression: there is ONE auto-clear threshold, and the console reads it from config.

`console/clear_gate.py` held `THRESHOLD = "1.000000"`, a second hardcoded copy of
`autonomy.threshold` in config/solver.yaml. It was the default argument of
`auto_clear_decision`, which the credit page, the mixed desk and the AI finance tools all
call without passing one. A derived threshold that moved in config would have left every one
of those surfaces rendering — and applying — a gate the orchestrator no longer enforced.
"""

from __future__ import annotations

import itertools

import pytest

from residual_zero.config import load_solver_config
from residual_zero.console import clear_gate
from residual_zero.console.clear_gate import auto_clear_decision, derived_threshold


def test_the_console_threshold_is_the_config_threshold():
    assert derived_threshold() == load_solver_config().autonomy.derived_threshold


def test_no_hardcoded_threshold_literal_remains_in_the_gate_module():
    src = clear_gate.__file__
    with open(src, encoding="utf-8") as handle:
        text = handle.read()
    assert 'THRESHOLD = "' not in text
    assert '"1.000000"' not in text


def test_gate_fails_closed_when_no_threshold_is_derived(monkeypatch):
    """No derived threshold means auto-clear must not proceed (ThresholdNotDerivedError)."""
    monkeypatch.setattr(clear_gate, "derived_threshold", lambda: None)
    got = auto_clear_decision(
        residual_paise=0, uniqueness="UNIQUE", pool_scope="FULL", ordering_score="1.000000",
    )
    assert got["eval_would_clear"] is False
    assert got["writes_cleared"] is False


def test_overlay_never_writes_cleared_on_any_input():
    """Exhaustive refuse table: 4 residuals x 4 uniqueness x 2 scopes x 4 scores."""
    residuals = (0, 1, -1, None)
    uniqueness = ("UNIQUE", "AMBIGUOUS", "NONE_FOUND", "BUDGET_EXCEEDED")
    scopes = ("FULL", "REDUCED")
    scores = (None, "1.000000", "0.999999", "0.000000")
    threshold = derived_threshold()
    for residual, uniq, scope, score in itertools.product(residuals, uniqueness, scopes, scores):
        got = auto_clear_decision(
            residual_paise=residual, uniqueness=uniq, pool_scope=scope, ordering_score=score,
        )
        assert got["writes_cleared"] is False
        if got["eval_would_clear"]:
            # Only the one legal cell may say the eval would have cleared it.
            assert residual == 0 and uniq == "UNIQUE" and scope == "FULL"
            assert score is None or score >= threshold


@pytest.mark.parametrize("uniq", ["AMBIGUOUS", "NONE_FOUND", "BUDGET_EXCEEDED"])
def test_residual_zero_is_never_enough_on_its_own(uniq):
    """A zero residual without uniqueness is not a clear — the product's whole thesis."""
    got = auto_clear_decision(residual_paise=0, uniqueness=uniq, pool_scope="FULL")
    assert got["final"] == "REFUSE"
    assert got["eval_would_clear"] is False
    assert got["writes_cleared"] is False
