"""Class-23 credits are the uniqueness detector's existence proof."""

from __future__ import annotations

from pathlib import Path

from eval.loader import load_split
from eval.truth_loader import load_truth
from residual_zero.candidates import build_pool
from residual_zero.config import load_solver_config
from residual_zero.models import Uniqueness
from residual_zero.solver import solve_search


def test_every_class23_credit_is_ambiguous(cp2_data: Path):
    """Every class-23 credit in dev returns AMBIGUOUS with alternates >= 2 and empty members."""
    items, credits = load_split("dev", data_root=cp2_data)
    recs = load_truth("dev", data_root=cp2_data)
    by_id = {c.id: c for c in credits}
    cfg = load_solver_config()
    n = 0
    for rec in recs:
        if 23 not in rec.corruption_classes:
            continue
        credit = by_id[rec.bank_credit_id]
        result = solve_search(build_pool(credit, items, cfg), credit.amount_paise, cfg)
        assert result.uniqueness == Uniqueness.AMBIGUOUS, credit.id
        assert result.alternates >= 2, credit.id
        assert result.member_ids == (), credit.id
        n += 1
    assert n >= 1


def test_no_class23_credit_is_ever_cleared(cp2_data: Path):
    """No class-23 credit is UNIQUE over the full pool, so none can auto-clear."""
    items, credits = load_split("dev", data_root=cp2_data)
    recs = load_truth("dev", data_root=cp2_data)
    by_id = {c.id: c for c in credits}
    cfg = load_solver_config()
    for rec in recs:
        if 23 not in rec.corruption_classes:
            continue
        credit = by_id[rec.bank_credit_id]
        result = solve_search(build_pool(credit, items, cfg), credit.amount_paise, cfg)
        assert result.uniqueness != Uniqueness.UNIQUE
        assert result.member_ids == ()
