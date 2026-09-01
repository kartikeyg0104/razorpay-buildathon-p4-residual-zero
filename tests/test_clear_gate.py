"""Auto-clear decision table. Residual-zero is not CLEARED."""

from __future__ import annotations

from residual_zero.console.clear_gate import THESIS, auto_clear_decision, illegal_clear_transition


def test_ambiguous_residual_zero_refuses():
    got = auto_clear_decision(residual_paise=0, uniqueness="AMBIGUOUS", pool_scope="FULL")
    assert got["residual"] == "PASS"
    assert got["uniqueness_gate"] == "FAIL"
    assert got["final"] == "REFUSE"
    assert got["writes_cleared"] is False
    assert got["eval_would_clear"] is False
    assert "Multiple valid" in got["reason"]
    # The thesis states the discipline, not one particular wording of it. Pinning an exact
    # word here made a copy edit look like a safety regression (test rot, 2026-09).
    thesis = THESIS.casefold()
    assert "uniqueness" in thesis
    assert "clear only when" in thesis


def test_none_found_refuses():
    got = auto_clear_decision(residual_paise=1, uniqueness="NONE_FOUND")
    assert got["residual"] == "FAIL"
    assert got["final"] == "REFUSE"
    assert "No exact financial explanation" in got["reason"]


def test_unique_still_refused_on_console_overlay():
    got = auto_clear_decision(
        residual_paise=0,
        uniqueness="UNIQUE",
        pool_scope="FULL",
        ordering_score="1.000000",
        disposition="FLAGGED",
    )
    assert got["uniqueness_gate"] == "PASS"
    assert got["eval_would_clear"] is True
    assert got["eval_label"] == "ELIGIBLE"
    assert got["console_clears"] is False
    assert got["final"] == "REFUSE"
    assert got["overlay_writes_cleared"] is False


def test_illegal_transitions():
    for src in ("AMBIGUOUS", "NONE_FOUND", "BUDGET_EXCEEDED", "EVIDENCE_ONLY", "VERIFIED"):
        assert illegal_clear_transition(src, "CLEARED", "AI") is True
        assert illegal_clear_transition(src, "CLEARED", "OVERLAY") is True
    assert illegal_clear_transition("AMBIGUOUS", "FLAGGED", "HUMAN") is False
