"""Measure actual schema joins. Does not install production rules. Eval may open truth."""

from __future__ import annotations

import json
from pathlib import Path

from eval.truth_loader import load_truth
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot


def _measure(split: str) -> dict[str, object]:
    root = SourceRoot(Path("data").joinpath(split, "rendered"))
    credits = load_bank_credits(root)
    items = load_ledger_items(root)
    declared = load_settlement_report(root)
    truth = load_truth(split)
    bank_ids = {c.id for c in credits}
    ledger_ids = {i.id for i in items}
    ledger = {i.id: i for i in items}
    ledger_orders = {i.order_id for i in items if i.order_id}
    ledger_accounts = {i.account_id for i in items}
    bank_accounts = {c.account_id for c in credits}
    item_ok = sum(1 for r in declared if r.item_id in ledger_ids)
    credit_ok = sum(1 for r in declared if r.credit_id in bank_ids)
    order_ok = sum(1 for r in declared if r.order_id and r.order_id in ledger_orders)
    order_present = sum(1 for r in declared if r.order_id)
    account_ok = 0
    for r in declared:
        item = ledger.get(r.item_id)
        credit = next((c for c in credits if c.id == r.credit_id), None)
        if item is not None and credit is not None and item.account_id == credit.account_id:
            account_ok += 1
    truth_ids = {r.bank_credit_id for r in truth}
    bank_in_truth = sum(1 for c in credits if c.id in truth_ids)
    declared_credits = {r.credit_id for r in declared}
    truth_with_settlement = sum(1 for r in truth if r.bank_credit_id in declared_credits)
    retained = 0
    false_alt = 0
    for rec in truth:
        declared_ids = {r.item_id for r in declared if r.credit_id == rec.bank_credit_id}
        truth_set = set(rec.member_ids)
        if not declared_ids:
            continue
        if truth_set <= declared_ids or declared_ids <= truth_set:
            retained += 1
        extra = declared_ids - truth_set
        if extra:
            false_alt += 1
    rows = [
        {
            "field": "settlement.item_id -> ledger.id",
            "support_count": item_ok,
            "coverage": f"{item_ok}/{len(declared)}" if declared else "0/0",
            "exists": True,
            "ground_truth_retention": f"{retained}/{len(truth)}",
            "false_alternatives": false_alt,
        },
        {
            "field": "settlement.credit_id -> bank.id",
            "support_count": credit_ok,
            "coverage": f"{credit_ok}/{len(declared)}" if declared else "0/0",
            "exists": True,
        },
        {
            "field": "settlement.member_id -> ledger.member_id",
            "support_count": 0,
            "coverage": "field_absent/field_absent",
            "exists": False,
            "note": "DeclaredLine and settlement.csv have no member_id. Join is item_id.",
        },
        {
            "field": "settlement.account_id -> account",
            "support_count": account_ok,
            "coverage": f"{account_ok}/{len(declared)}" if declared else "0/0",
            "exists": False,
            "note": "No settlement.account_id column. Measured via ledger.account_id == bank.account_id on item/credit join.",
        },
        {
            "field": "settlement.order_id -> ledger.order_id",
            "support_count": order_ok,
            "coverage": f"{order_ok}/{order_present}" if order_present else "0/0",
            "exists": True,
        },
        {
            "field": "bank.id -> truth.bank_credit_id",
            "support_count": bank_in_truth,
            "coverage": f"{bank_in_truth}/{len(credits)}",
            "exists": True,
        },
        {
            "field": "truth credits with settlement rows",
            "support_count": truth_with_settlement,
            "coverage": f"{truth_with_settlement}/{len(truth)}",
            "exists": True,
        },
        {
            "field": "ledger.account_id / bank.account_id",
            "support_count": len(ledger_accounts | bank_accounts),
            "coverage": f"ledger={len(ledger_accounts)} bank={len(bank_accounts)}",
            "exists": True,
        },
    ]
    return {
        "split": split,
        "n_bank": len(credits),
        "n_ledger": len(items),
        "n_settlement": len(declared),
        "n_truth": len(truth),
        "rows": rows,
        "writes_cleared": False,
        "implemented_new_rules": 0,
    }


def main() -> dict[str, object]:
    payload = {"dev": _measure("dev"), "test": _measure("test")}
    out = Path("artifacts").joinpath("qa", "schema_relationships.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    main()
