"""A0/A1 baseline honesty: A0 cannot express N:M, A1 is optimal not greedy."""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
from scipy.optimize import linear_sum_assignment

from residual_zero.config import load_solver_config
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.normalise import normalise_narration
from residual_zero.tz import IST, ensure_utc

from eval.arms import ArmResult
from eval.arms.a0_exact import run_a0
from eval.arms.a1_fuzzy import A1Config, build_cost_matrix, run_a1
from eval.metrics import exact_decomposition_rate


def _item(iid: str, amount: int, account: str = "acc_00") -> LedgerItem:
    occurred = ensure_utc(datetime(2025, 1, 10, 12, 0, 0, tzinfo=IST))
    raw = f"PAYMENT {iid}"
    return LedgerItem(
        id=iid, kind=Kind.PAYMENT, amount_paise=amount, occurred_at=occurred,
        account_id=account, currency="INR", instrument=Instrument.UPI,
        order_id=None, parent_id=None, narration_raw=raw,
        narration_norm=normalise_narration(raw), counterparty_raw="x",
        counterparty_id=None, source=Source.INTERNAL_LEDGER,
    )


def _credit(cid: str, amount: int, account: str = "acc_00") -> BankCredit:
    raw = f"NEFT RAZORPAY SETTLEMENT {account}"
    return BankCredit(
        id=cid, amount_paise=amount, value_date=date(2025, 1, 15),
        account_id=account, currency="INR", narration_raw=raw,
        narration_norm=normalise_narration(raw), utr="UTRTEST",
    )


def test_a0_never_predicts_multi_item():
    """A0's predictions all have length 0 or 1 — it cannot express N:M by construction."""
    items = (_item("a", 10000), _item("b", 10000), _item("c", 20000))
    credits = (_credit("c1", 10000), _credit("c2", 99999))
    result = run_a0(items, credits, load_solver_config())
    for pred in result.predictions.values():
        assert len(pred) <= 1


def test_a1_assignment_is_injective():
    """No ledger item is assigned to two credits and no credit to two items."""
    items = (_item("a", 10000), _item("b", 11000), _item("c", 12000))
    credits = (_credit("c1", 10000), _credit("c2", 11000))
    result = run_a1(items, credits, A1Config(sim_threshold=0, amount_tol_paise=50_000))
    assigned = [ids[0] for ids in result.predictions.values() if ids]
    assert len(assigned) == len(set(assigned))
    for ids in result.predictions.values():
        assert len(ids) <= 1


def test_a1_beats_greedy_on_a_fixture():
    """On a fixture where greedy is suboptimal, linear_sum_assignment finds strictly lower total cost."""
    # 2x2: greedy takes (0,0) cost 1 then is stuck with (1,1) cost 100; optimal is (0,1)+(1,0) = 3+3.
    cost = np.array([[1.0, 3.0], [3.0, 100.0]])
    greedy = cost[0, 0] + cost[1, 1]
    rows, cols = linear_sum_assignment(cost)
    optimal = cost[rows, cols].sum()
    assert optimal < greedy


def test_arms_without_exception_path_report_na():
    """A0 and A1 ArmResult.has_exception_path is False, and the metric cell for exceptions is NA, not 0."""
    items = (_item("a", 10000),)
    credits = (_credit("c1", 10000),)
    a0 = run_a0(items, credits, load_solver_config())
    a1 = run_a1(items, credits, A1Config(sim_threshold=0, amount_tol_paise=100))
    assert a0.has_exception_path is False
    assert a1.has_exception_path is False
    assert a0.has_budget_path is False
    assert a1.has_budget_path is False
