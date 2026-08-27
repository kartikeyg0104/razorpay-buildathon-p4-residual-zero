"""F45: CAMT.053 and MT940 round-trip to the CSV BankCredit fields."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.ingest.camt053 import parse_camt053, render_camt053
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.mt940 import parse_mt940, render_mt940
from residual_zero.ingest.source_root import SourceRoot


def _csv_credits(n: int = 8):
    root = SourceRoot(Path("data").joinpath("dev", "rendered"))
    return load_bank_credits(root)[:n]


@pytest.mark.parametrize("fmt", ["camt", "mt940"])
def test_round_trip_matches_csv_fields(fmt: str):
    original = _csv_credits()
    account = original[0].account_id
    if fmt == "camt":
        payload = render_camt053(original, account)
        parsed = parse_camt053(payload, path="roundtrip.xml")
    else:
        text = render_mt940(original, account)
        parsed = parse_mt940(text, path="roundtrip.sta")
    assert len(parsed) == len(original)
    for a, b in zip(original, parsed, strict=True):
        assert a.id == b.id
        assert a.amount_paise == b.amount_paise
        assert a.value_date == b.value_date
        assert a.account_id == b.account_id
        assert a.currency == b.currency
        assert a.narration_raw == b.narration_raw
        assert a.narration_norm == b.narration_norm
        assert a.utr == b.utr
