"""F44: class 25 detection; false positives on a legitimate two-account batch first."""

from __future__ import annotations

from pathlib import Path
from random import Random

import pytest

from residual_zero.controller.accounts import consolidated_view, detect_credit, false_positives
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import BankCredit

from generator.corrupt import apply_corruptions, phase4_class25_plan
from generator.render import render
from tests.test_generator import _one_seed


@pytest.mark.skipif(not Path("data/dev/rendered/bank.csv").is_file(), reason="data/dev missing")
def test_false_positive_rate_on_legitimate_dev_is_zero():
    """FP protocol first: two legitimate MIDs must not fire."""
    root = SourceRoot(Path("data").joinpath("dev", "rendered"))
    credits = load_bank_credits(root)
    items = load_ledger_items(root)
    ledger = {it.id: it for it in items}
    declared: dict[str, list[str]] = {}
    for row in load_settlement_report(root):
        declared.setdefault(row.credit_id, []).append(row.item_id)
    fired = false_positives(credits, declared, ledger)
    assert fired == ()
    view = consolidated_view(credits)
    assert set(view) >= {"acc_00", "acc_01"}


def test_class25_detection_on_fixture():
    _, _, truth = _one_seed()
    views, records = apply_corruptions(render(truth), truth, phase4_class25_plan(), Random(25_000))
    labelled = [r for r in records if 25 in r.corruption_classes]
    assert labelled, "phase4_class25_plan produced no class-25 credits"
    items = {i.id: i for i in truth.items}
    bank = {row["id"]: row for row in views.bank_rows}
    detected = 0
    for record in labelled:
        row = bank[record.bank_credit_id]
        credit = BankCredit(
            id=record.bank_credit_id,
            amount_paise=record.total_paise,
            value_date=truth.credits[0].value_date,
            account_id=row["account_id"],
            currency="INR",
            narration_raw=row["narration_raw"],
            narration_norm=row["narration_raw"].lower(),
        )
        member_items = [items[mid] for mid in record.member_ids if mid in items]
        assert member_items
        assert all(m.account_id != credit.account_id for m in member_items)
        if detect_credit(credit, record.member_ids, items):
            detected += 1
    assert detected == len(labelled)
    for record in labelled:
        before = {r.bank_credit_id: (r.member_ids, r.total_paise) for r in truth.records}
        assert (record.member_ids, record.total_paise) == before[record.bank_credit_id]
