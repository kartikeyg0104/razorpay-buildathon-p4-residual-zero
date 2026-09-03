"""Regression: the NO_SEARCH rung must not run the DP it is not allowed to run.

`policy_for(NO_SEARCH).allow_search` is False, but both arms of the orchestrator's branch
called `solve_search` and the no-search arm then overwrote three fields of the result. So the
rung paid for the search in full, and left `slack_rupees`, `margin_rupees` and
`nearest_delta_rupees` on the result — search observables a rung that did not search cannot
honestly report. F51's ladder is meant to shed work as it degrades.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import residual_zero.orchestrator as orchestrator
from residual_zero.models import Uniqueness
from residual_zero.runtime.degrade import Rung, policy_for
from residual_zero.solver import unsearched_result
from tests.solver_helpers import pool_from_amounts

LADDER = [Rung.NORMAL, Rung.NO_MODEL, Rung.NO_SEARCH, Rung.READ_ONLY]


@pytest.fixture()
def counted_search(monkeypatch):
    calls: list[int] = []
    real = orchestrator.solve_search

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(orchestrator, "solve_search", counting)
    return calls


@pytest.mark.parametrize("rung", LADDER)
def test_search_is_spent_only_when_the_rung_allows_it(rung, counted_search, tmp_path):
    n = orchestrator.run_split("dev", tmp_path.joinpath("l.sqlite"), limit=6, rung=rung)
    assert n == 6
    if policy_for(rung).allow_search:
        assert len(counted_search) == 6
    else:
        assert counted_search == [], f"{rung.value} ran the DP it forbids"


def test_unsearched_result_carries_no_search_observables():
    pool = pool_from_amounts([100, 250, -30])
    got = unsearched_result(pool)
    assert got.uniqueness is Uniqueness.NONE_FOUND
    assert got.member_ids == ()
    assert got.alternates == 0
    # None of these may be reported by a rung that did not search.
    assert got.slack_rupees is None
    assert got.margin_rupees is None
    assert got.nearest_total_rupees is None
    assert got.nearest_delta_rupees is None
    assert got.matched_total_rupees is None
    # Pool facts are not search results and are still reported.
    assert got.pool_size == 3
    assert got.pool_scope is pool.scope


def test_degrading_never_introduces_a_clear(tmp_path):
    """ADR-11 gate #6: a lower rung may refuse work, never authorise more of it."""
    cleared: list[int] = []
    for rung in LADDER:
        db = tmp_path.joinpath(f"{rung.value}.sqlite")
        orchestrator.run_split("dev", db, limit=12, rung=rung)
        import sqlite3

        conn = sqlite3.connect(db)
        try:
            cleared.append(conn.execute("SELECT COUNT(*) FROM reconciliation").fetchone()[0])
        finally:
            conn.close()
    assert cleared == sorted(cleared, reverse=True), cleared


def test_halted_processes_nothing(tmp_path):
    db = tmp_path.joinpath("halted.sqlite")
    assert orchestrator.run_split("dev", db, limit=5, rung=Rung.HALTED) == 0
    assert not Path(db).exists() or db.stat().st_size >= 0
