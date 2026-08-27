"""Candidate windows, deterministic sort, never-truncate, bounded split."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from residual_zero.candidates import build_pool, split_pool
from residual_zero.config import load_solver_config
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, PoolScope, Source
from residual_zero.normalise import normalise_narration
from residual_zero.tz import IST, ensure_utc


def _item(iid: str, kind: Kind, amount: int, occurred: datetime, account: str = "acc_00") -> LedgerItem:
    raw = f"{kind.value} {iid}"
    return LedgerItem(
        id=iid, kind=kind, amount_paise=amount, occurred_at=ensure_utc(occurred),
        account_id=account, currency="INR", instrument=Instrument.UPI,
        order_id=None, parent_id=None, narration_raw=raw,
        narration_norm=normalise_narration(raw), counterparty_raw="x",
        counterparty_id=None, source=Source.INTERNAL_LEDGER,
    )


def _credit(cid: str = "c1", amount: int = 10000, day: date = date(2025, 1, 15)) -> BankCredit:
    raw = "NEFT RAZORPAY SETTLEMENT"
    return BankCredit(
        id=cid, amount_paise=amount, value_date=day,
        account_id="acc_00", currency="INR", narration_raw=raw,
        narration_norm=normalise_narration(raw), utr="UTRTEST",
    )


def test_window_asymmetry():
    """Only the five widened kinds appear from before D-5; a PAYMENT at D-10 is excluded."""
    value = date(2025, 1, 15)
    payment_in = _item("p_in", Kind.PAYMENT, 50000, datetime(2025, 1, 12, 10, 0, tzinfo=IST))
    payment_out = _item("p_out", Kind.PAYMENT, 40000, datetime(2025, 1, 5, 10, 0, tzinfo=IST))
    refund_wide = _item("r_wide", Kind.REFUND, -20000, datetime(2025, 1, 5, 10, 0, tzinfo=IST))
    cfg = load_solver_config()
    pool = build_pool(_credit(day=value), (payment_in, payment_out, refund_wide), cfg)
    assert "p_in" in pool.item_ids
    assert "p_out" not in pool.item_ids
    assert "r_wide" in pool.item_ids


def test_deterministic_sort():
    value = date(2025, 1, 15)
    a = _item("b", Kind.PAYMENT, 10000, datetime(2025, 1, 12, 10, 0, tzinfo=IST))
    b = _item("a", Kind.PAYMENT, 20000, datetime(2025, 1, 12, 10, 0, tzinfo=IST))
    c = _item("c", Kind.PAYMENT, 30000, datetime(2025, 1, 13, 10, 0, tzinfo=IST))
    cfg = load_solver_config()
    credit = _credit(day=value)
    first = build_pool(credit, (c, a, b), cfg)
    second = build_pool(credit, (b, c, a), cfg)
    assert first.item_ids == second.item_ids
    assert first.item_ids == ("a", "b", "c") or (
        first.occurred_on[0] <= first.occurred_on[1] <= first.occurred_on[2]
    )


def test_over_cap_pool_is_never_truncated():
    value = date(2025, 1, 15)
    items = tuple(
        _item(f"p{i:03d}", Kind.PAYMENT, 1000 + i, datetime(2025, 1, 12, 10, 0, tzinfo=IST))
        for i in range(30)
    )
    cfg = load_solver_config()
    pool = build_pool(_credit(day=value), items, cfg)
    assert len(pool.item_ids) == 30
    assert pool.scope == PoolScope.FULL


def test_split_is_deterministic_and_bounded():
    value = date(2025, 1, 15)
    items = tuple(
        _item(
            f"p{i:03d}", Kind.PAYMENT, 1000 + i,
            datetime(2025, 1, 15, 10, 0, tzinfo=IST) - timedelta(days=i + 1),
        )
        for i in range(8)
    )
    cfg = load_solver_config()
    credit = _credit(day=value)
    pool = build_pool(credit, items, cfg)
    first = split_pool(pool, credit, cfg)
    second = split_pool(pool, credit, cfg)
    assert first == second
    assert len(first) <= cfg.sub_window_split.max_attempts
    assert all(sub.scope == PoolScope.REDUCED for sub in first)
    assert all(sub.sub_window is not None for sub in first)
