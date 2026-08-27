"""F35 day-ordered replay."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.normalise import normalise_narration
from residual_zero.stream.carry_forward import replay
from residual_zero.tz import IST, ensure_utc


def test_replay_counts_unsolvable_on_arrival(tmp_path: Path):
    item = LedgerItem(
        id="i1", kind=Kind.PAYMENT, amount_paise=100_00,
        occurred_at=ensure_utc(datetime(2025, 1, 8, 10, 0, tzinfo=IST)),
        account_id="acc_00", currency="INR", instrument=Instrument.UPI,
        order_id=None, parent_id=None, narration_raw="p",
        narration_norm=normalise_narration("p"), counterparty_raw="x",
        counterparty_id=None, source=Source.INTERNAL_LEDGER,
    )
    credit = BankCredit(
        id="c1", amount_paise=100_00, value_date=date(2025, 1, 10),
        account_id="acc_00", currency="INR", narration_raw="n",
        narration_norm=normalise_narration("n"), utr=None,
    )
    report = replay(
        (credit,), (item,),
        db_path=tmp_path.joinpath("stream.sqlite"),
        widened_days_before=35,
        solvable=set(),
    )
    assert report.n_credits == 1
    assert report.unsolvable_on_arrival == 1
    assert report.eventually_resolved == 0
    cleared = replay(
        (credit,), (item,),
        db_path=tmp_path.joinpath("stream2.sqlite"),
        widened_days_before=35,
        solvable={"c1"},
    )
    assert cleared.eventually_resolved == 1
    assert cleared.unsolvable_on_arrival == 0
