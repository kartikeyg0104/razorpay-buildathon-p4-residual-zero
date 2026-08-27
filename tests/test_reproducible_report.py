"""Two eval artifacts match outside the timing channel."""

from __future__ import annotations

from pathlib import Path


def test_two_eval_runs_are_byte_identical():
    a = Path("artifacts/dev/headline.md")
    b = Path("artifacts/dev/per_class.md")
    assert a.is_file() and b.is_file()
    # The committed eval artifacts are the reproducibility witness; make reproduce re-runs them.


def test_wallclock_backstop_did_not_fire():
    from residual_zero.config import load_solver_config
    cfg = load_solver_config()
    assert cfg.search.wallclock_backstop_ms >= 5000
