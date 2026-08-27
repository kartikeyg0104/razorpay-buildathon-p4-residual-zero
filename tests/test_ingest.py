"""Ingest is total-or-raise, and class 18 is ingestible."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from residual_zero.ingest import IngestError, SourceRoot
from residual_zero.ingest.csv_ledger import _row_to_item, load_ledger_items
from residual_zero.models import Kind
from residual_zero.normalise import sign_anomaly
from residual_zero.tz import IST


def test_sign_reversed_row_ingests_and_flags():
    """A class-18 row loads successfully and sign_anomaly returns True (PLAN-P1 §0.6)."""
    row = {
        "id": "itm_signrev",
        "kind": Kind.REFUND.value,
        "amount": "100.00",  # positive, which is the wrong sign for a refund
        "occurred_at": "2025-01-15 12:00:00 IST",
        "account_id": "acc_00",
        "currency": "INR",
        "instrument": "UPI",
        "order_id": "ord_x",
        "parent_id": "itm_parent",
        "narration_raw": "REFUND posted as credit",
        "counterparty_raw": "Aarav Textiles Pvt Ltd",
        "source": "INTERNAL_LEDGER",
    }
    item = _row_to_item(row)
    assert item.amount_paise > 0
    assert sign_anomaly(item) is True


def test_ingest_is_total_or_raises(tmp_path: Path):
    """A malformed row produces a typed ingestion error naming the line, never a partial load."""
    rendered = tmp_path / "rendered"
    rendered.mkdir()
    (rendered / "ledger.csv").write_text(
        "id,kind,amount,occurred_at,account_id,currency,instrument,order_id,parent_id,"
        "narration_raw,counterparty_raw,source\n"
        "itm_ok,PAYMENT,10.00,2025-01-15 12:00:00 IST,acc_00,INR,UPI,ord_1,,ok,Alice,INTERNAL_LEDGER\n"
        "itm_bad,PAYMENT,not-a-number,2025-01-15 12:00:00 IST,acc_00,INR,UPI,ord_2,,bad,Bob,INTERNAL_LEDGER\n",
        encoding="utf-8",
    )
    root = SourceRoot(rendered)
    with pytest.raises(IngestError) as excinfo:
        load_ledger_items(root)
    assert excinfo.value.line == 3
    assert "ledger.csv" in str(excinfo.value)
