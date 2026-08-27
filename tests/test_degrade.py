"""F51: monotonic conservatism. On this corpus coverage is 0 at NORMAL, so no rung may clear."""

from __future__ import annotations

from residual_zero.runtime.degrade import Rung, monotonic_coverage, policy_for, step, load_degrade


def test_rung_policies_tighten():
    n = policy_for(Rung.NORMAL)
    assert n.allow_model and n.allow_search and n.allow_writes
    assert not policy_for(Rung.NO_MODEL).allow_model
    assert not policy_for(Rung.NO_SEARCH).allow_search
    assert not policy_for(Rung.READ_ONLY).allow_writes
    assert not policy_for(Rung.HALTED).process_credits


def test_step_does_not_relax():
    cfg = load_degrade()
    assert step(Rung.NO_SEARCH, "token_budget_exhausted", cfg) is Rung.NO_SEARCH
    assert step(Rung.NORMAL, "manual_halt", cfg) is Rung.HALTED


def test_monotonic_coverage_is_enforced():
    rows = [
        (Rung.NORMAL, 0, 239),
        (Rung.NO_MODEL, 0, 239),
        (Rung.NO_SEARCH, 0, 239),
        (Rung.READ_ONLY, 0, 239),
        (Rung.HALTED, 0, 239),
    ]
    assert monotonic_coverage(rows) is True
    rising = [
        (Rung.NORMAL, 0, 239),
        (Rung.NO_MODEL, 1, 239),
    ]
    assert monotonic_coverage(rising) is False
