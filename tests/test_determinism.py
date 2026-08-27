"""F34: 1/4/8 workers produce byte-identical canonical payloads."""

from __future__ import annotations

from datetime import date, datetime, timezone

from residual_zero.config import load_solver_config
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.runtime.pool import canonical_payload, map_reduce, partition_ids

_AWARE = datetime(2025, 1, 9, 6, 0, tzinfo=timezone.utc)


def _item(item_id: str, amount: int, account: str = "acc_01") -> LedgerItem:
    return LedgerItem(
        id=item_id,
        kind=Kind.PAYMENT,
        amount_paise=amount,
        occurred_at=_AWARE,
        account_id=account,
        currency="INR",
        instrument=Instrument.UPI,
        narration_raw="pay",
        narration_norm="pay",
        source=Source.INTERNAL_LEDGER,
    )


def _credit(credit_id: str, amount: int, day: date, account: str = "acc_01") -> BankCredit:
    return BankCredit(
        id=credit_id,
        amount_paise=amount,
        value_date=day,
        account_id=account,
        currency="INR",
        narration_raw="neft",
        narration_norm="neft",
    )


def test_partition_covers_every_id_once():
    ids = ("c", "a", "b", "d")
    parts = partition_ids(ids, 3)
    flat = [i for p in parts for i in p]
    assert sorted(flat) == ["a", "b", "c", "d"]
    assert len(flat) == len(set(flat))


def test_one_four_eight_workers_are_byte_identical():
    items = tuple(_item(f"p{i}", 10_000 * (i + 1)) for i in range(8))
    credits = tuple(
        _credit(f"crd_{i:02d}", items[i].amount_paise, date(2025, 1, 10), "acc_01")
        for i in range(8)
    )
    cfg = load_solver_config()
    payloads = []
    for n in (1, 4, 8):
        rows = map_reduce(credits, items, cfg, n)
        payloads.append(canonical_payload(rows))
    assert payloads[0] == payloads[1] == payloads[2]
    assert b"credit_id" in payloads[0]
