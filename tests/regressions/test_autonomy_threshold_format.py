"""Regression: the auto-clear threshold is compared as a STRING, so its spelling is load-bearing.

`orchestrator.run_split` gates CLEARED on `score_s >= threshold`, where `score_s` comes from
`render_score` (`f"{score:.6f}"`) and `threshold` is a raw config string. That comparison is
lexicographic. A threshold written in any other decimal spelling silently fails OPEN — every
score passes ADR-11 gate #5 — so `AutonomyConfig` now refuses anything that is not exactly the
shape `render_score` emits.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from residual_zero.config import AutonomyConfig, load_solver_config
from residual_zero.models import render_score

SOURCE = "artifacts/dev/curve_a3.json"

# Every one of these compares >= some rendered score it must be strictly above.
FAILS_OPEN = [
    ".5",           # '0' > '.' so "0.000000" >= ".5" is True
    " 1.000000",    # ' ' < '0' so every score sorts above it
    "1.0",          # short prefix: shorter string loses, so "1.000000" >= "1.0"
    "1",
    "0.90",
]


@pytest.mark.parametrize("threshold", FAILS_OPEN)
def test_malformed_threshold_is_refused_at_config_load(threshold: str) -> None:
    with pytest.raises(ValidationError):
        AutonomyConfig(threshold=threshold, threshold_source=SOURCE)


@pytest.mark.parametrize("threshold", ["1.000000", "0.000000", "0.123456"])
def test_rendered_thresholds_are_accepted(threshold: str) -> None:
    assert AutonomyConfig(threshold=threshold, threshold_source=SOURCE).threshold == threshold


def test_the_shipped_threshold_is_a_rendered_score() -> None:
    """config/solver.yaml must hold a value render_score could have produced."""
    threshold = load_solver_config().autonomy.derived_threshold
    assert threshold == render_score(float(threshold))


def test_string_comparison_orders_like_the_numbers_for_every_rendered_score() -> None:
    """The gate's `score_s >= threshold` must agree with numeric >= across the score range."""
    threshold = load_solver_config().autonomy.derived_threshold
    for numerator in range(0, 1001):
        score = numerator / 1000.0
        rendered = render_score(score)
        assert (rendered >= threshold) == (float(rendered) >= float(threshold)), rendered
