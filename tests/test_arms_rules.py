"""A2 uses the same pools as A3 and has no uniqueness check."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from eval.arms.a2_rules import run_a2
from eval.loader import load_split
from residual_zero.candidates import build_pool
from residual_zero.config import load_fees, load_solver_config, load_tax_rates
from residual_zero.models import BankCredit, Disposition, Instrument, Kind, LedgerItem, Source
from residual_zero.normalise import normalise_narration
from residual_zero.tz import IST, ensure_utc


def test_a2_uses_the_same_pool_as_a3(cp2_data: Path):
    items, credits = load_split("dev", data_root=cp2_data)
    cfg = load_solver_config()
    credit = credits[0]
    a2_pool = build_pool(credit, items, cfg)
    a3_pool = build_pool(credit, items, cfg)
    assert a2_pool.item_ids == a3_pool.item_ids
    assert a2_pool.amounts_paise == a3_pool.amounts_paise


def test_a2_has_no_uniqueness_check():
    """On a class-23 shape (100 == 60+40) A2 clears something the uniqueness check would refuse."""
    def item(iid: str, amount: int) -> LedgerItem:
        raw = f"PAYMENT {iid}"
        return LedgerItem(
            id=iid, kind=Kind.PAYMENT, amount_paise=amount,
            occurred_at=ensure_utc(datetime(2025, 1, 12, 10, 0, tzinfo=IST)),
            account_id="acc_00", currency="INR", instrument=Instrument.UPI,
            order_id=None, parent_id=None, narration_raw=raw,
            narration_norm=normalise_narration(raw), counterparty_raw="x",
            counterparty_id=None, source=Source.INTERNAL_LEDGER,
        )
    items = (item("a", 100_00), item("b", 60_00), item("c", 40_00))
    credit = BankCredit(
        id="c23", amount_paise=100_00, value_date=date(2025, 1, 15),
        account_id="acc_00", currency="INR", narration_raw="NEFT",
        narration_norm=normalise_narration("NEFT"), utr="U",
    )
    result = run_a2(items, (credit,), load_tax_rates(), load_fees(), load_solver_config())
    assert result.dispositions["c23"] == Disposition.CLEARED
    assert result.predictions["c23"]
