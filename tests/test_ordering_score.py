"""Ordering score: six observables, geometric mean, unresolved annihilates, monotone, byte-stable."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

from residual_zero.config import load_solver_config
from residual_zero.models import PoolScope, ResolutionTier, Uniqueness, render_score
from residual_zero.ordering import TERM_NAMES, ordering_score, score_terms
from residual_zero.semantic.tiers import Resolution
from residual_zero.solver.enumerate import SolveResult


def _solve(**kwargs) -> SolveResult:
    base = dict(
        uniqueness=Uniqueness.UNIQUE,
        matched_total_rupees=100,
        member_ids=("a",),
        alternates=1,
        nearest_total_rupees=100,
        nearest_delta_rupees=0,
        pool_scope=PoolScope.FULL,
        pool_size=10,
        axis_width=50,
        slack_rupees=0,
        margin_rupees=8,
    )
    base.update(kwargs)
    return SolveResult(**base)


def _res(*tiers: ResolutionTier) -> tuple[Resolution, ...]:
    return tuple(Resolution("e", t, None if t != ResolutionTier.FUZZY else 90) for t in tiers)


def test_unresolved_entity_annihilates_the_score():
    cfg = load_solver_config()
    score = ordering_score(_solve(), _res(ResolutionTier.UNRESOLVED), 0, 4, cfg)
    assert score == 0.0
    assert render_score(score) == "0.000000"


def test_each_term_is_monotone():
    cfg = load_solver_config()
    base = ordering_score(_solve(), _res(ResolutionTier.EXACT_NORM), 0, 4, cfg)
    worse = [
        ordering_score(_solve(slack_rupees=7), _res(ResolutionTier.EXACT_NORM), 0, 4, cfg),
        ordering_score(_solve(margin_rupees=0), _res(ResolutionTier.EXACT_NORM), 0, 4, cfg),
        ordering_score(_solve(pool_size=400), _res(ResolutionTier.EXACT_NORM), 0, 4, cfg),
        ordering_score(_solve(), _res(ResolutionTier.FUZZY), 0, 4, cfg),
        ordering_score(_solve(), _res(ResolutionTier.EXACT_NORM), 4, 4, cfg),
        ordering_score(_solve(), _res(ResolutionTier.EXACT_NORM), 0, 120, cfg),
    ]
    for w in worse:
        assert w <= base


def test_score_renders_identically_across_processes():
    cfg = load_solver_config()
    score = ordering_score(_solve(), _res(ResolutionTier.EXACT_NORM), 0, 4, cfg)
    rendered = render_score(score)
    script = (
        "from residual_zero.config import load_solver_config;"
        "from residual_zero.models import PoolScope, ResolutionTier, Uniqueness, render_score;"
        "from residual_zero.ordering import ordering_score;"
        "from residual_zero.semantic.tiers import Resolution;"
        "from residual_zero.solver.enumerate import SolveResult;"
        "s=SolveResult(uniqueness=Uniqueness.UNIQUE,matched_total_rupees=100,member_ids=('a',),"
        "alternates=1,nearest_total_rupees=100,nearest_delta_rupees=0,pool_scope=PoolScope.FULL,"
        "pool_size=10,axis_width=50,slack_rupees=0,margin_rupees=8);"
        "print(render_score(ordering_score(s,(Resolution('e',ResolutionTier.EXACT_NORM,None),),0,4,load_solver_config())))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = "src:."
    other = subprocess.check_output(
        [sys.executable, "-c", script], cwd=Path(".").resolve(), env=env
    )
    assert other.decode().strip() == rendered


def test_no_model_confidence_input():
    cfg = load_solver_config()
    assert tuple(cfg.ordering_score.terms) == TERM_NAMES
    sig = inspect.signature(ordering_score)
    assert "confidence" not in sig.parameters
    terms = score_terms(_solve(), _res(ResolutionTier.EXACT_NORM), 0, 4, cfg)
    assert tuple(terms) == TERM_NAMES
    assert "confidence" not in terms
