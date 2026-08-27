"""F39/F41/F42 detector unit tests on constructed ledgers."""

from __future__ import annotations

from datetime import date, datetime

from residual_zero.controller.disputes import track
from residual_zero.controller.leakage import sweep
from residual_zero.controller.reserve import subledger
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.normalise import normalise_narration
from residual_zero.tz import IST, ensure_utc


def _item(iid: str, kind: Kind, amount: int, day: date, parent: str | None = None) -> LedgerItem:
    raw = f"{kind.value} {iid}"
    return LedgerItem(
        id=iid, kind=kind, amount_paise=amount,
        occurred_at=ensure_utc(datetime(day.year, day.month, day.day, 10, 0, tzinfo=IST)),
        account_id="acc_00", currency="INR", instrument=Instrument.UPI,
        order_id="o1", parent_id=parent, narration_raw=raw,
        narration_norm=normalise_narration(raw), counterparty_raw="x",
        counterparty_id=None, source=Source.INTERNAL_LEDGER,
    )


def test_overdue_reserve_and_identity():
    hold = _item("h1", Kind.RESERVE_HOLD, -500, date(2025, 1, 1))
    report = subledger((hold,), as_of=date(2025, 3, 1), lag_days=30)
    assert report.identity_holds
    assert report.outstanding_paise == 500
    assert report.overdue_count == 1
    leak = sweep((hold,), (), as_of=date(2025, 3, 1), reserve_lag_days=30)
    assert leak.rupees_identified_paise == 500
    assert leak.evidence[0].kind == "overdue_reserve"


def test_duplicate_refund_and_chargeback_window():
    refund_a = _item("r1", Kind.REFUND, -100, date(2025, 1, 10), parent="p1")
    refund_b = _item("r2", Kind.REFUND, -100, date(2025, 1, 11), parent="p1")
    cb = _item("cb1", Kind.CHARGEBACK, -200, date(2025, 2, 1))
    leak = sweep((refund_a, refund_b, cb), (), as_of=date(2025, 2, 10), reserve_lag_days=30)
    kinds = {e.kind for e in leak.evidence}
    assert "duplicate_refund" in kinds
    assert "chargeback_unrepresented" in kinds


def test_dispute_deadline_window():
    cb = _item("cb1", Kind.CHARGEBACK, -200, date(2025, 1, 1))
    rep = _item("rp1", Kind.REPRESENTMENT, 200, date(2025, 1, 10), parent="cb1")
    with_rep = track((cb, rep), as_of=date(2025, 1, 12))
    assert with_rep.reconstructed_end_to_end == 1
    open_only = track((cb,), as_of=date(2025, 2, 10))
    assert open_only.open_inside_7_days == 1
    assert open_only.reconstructed_end_to_end == 0
