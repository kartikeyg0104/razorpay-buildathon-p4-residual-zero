"""Dataset integrity. Does not modify production CSVs."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import Kind
from residual_zero.normalise import parse_rupee_display


def _csv_shape(path: Path) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    return {"path": str(path), "row_count": len(rows), "column_count": len(fields), "columns": fields}


def _parse_amount(raw: str) -> tuple[int | None, str | None]:
    try:
        return parse_rupee_display(raw), None
    except Exception as exc:
        return None, str(exc)


def _audit(split: str) -> dict[str, object]:
    rendered = Path("data").joinpath(split, "rendered")
    bank_csv = rendered.joinpath("bank.csv")
    ledger_csv = rendered.joinpath("ledger.csv")
    settlement_csv = rendered.joinpath("settlement.csv")
    truth = Path("data").joinpath(split, "truth.jsonl")
    root = SourceRoot(rendered)
    credits = load_bank_credits(root)
    items = load_ledger_items(root)
    declared = load_settlement_report(root)
    credit_ids = [c.id for c in credits]
    item_ids = [i.id for i in items]
    ledger = {i.id: i for i in items}
    bank_ids = set(credit_ids)
    dup_credits = [k for k, n in Counter(credit_ids).items() if n > 1]
    dup_items = [k for k, n in Counter(item_ids).items() if n > 1]
    orphan_items = [r.item_id for r in declared if r.item_id not in ledger]
    orphan_credits = [r.credit_id for r in declared if r.credit_id not in bank_ids]
    kinds = Counter(i.kind.value for i in items)
    set_kinds = Counter(r.kind.value for r in declared)
    bank_ccy = Counter(c.currency for c in credits)
    ledger_ccy = Counter(i.currency for i in items)
    malformed_bank = 0
    invalid_bank_dates = 0
    with bank_csv.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            amt, err = _parse_amount(raw.get("amount") or "")
            if err is not None or amt is None:
                malformed_bank += 1
            try:
                date.fromisoformat((raw.get("value_date") or "").strip())
            except ValueError:
                invalid_bank_dates += 1
    malformed_ledger = 0
    invalid_ledger_dates = 0
    with ledger_csv.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            amt, err = _parse_amount(raw.get("amount") or "")
            if err is not None or amt is None:
                malformed_ledger += 1
            stamp = (raw.get("occurred_at") or "").strip()
            if len(stamp) < 10:
                invalid_ledger_dates += 1
            else:
                try:
                    date.fromisoformat(stamp[:10])
                except ValueError:
                    invalid_ledger_dates += 1
    order_ids = [i.order_id for i in items if i.order_id]
    dup_orders = [k for k, n in Counter(order_ids).items() if n > 1]
    negative_bank = sum(1 for c in credits if c.amount_paise < 0)
    zero_bank = sum(1 for c in credits if c.amount_paise == 0)
    return {
        "split": split,
        "bank_csv": _csv_shape(bank_csv),
        "ledger_csv": _csv_shape(ledger_csv),
        "settlement_csv": _csv_shape(settlement_csv),
        "truth_jsonl_exists": truth.is_file(),
        "truth_lines": sum(1 for line in truth.read_text(encoding="utf-8").splitlines() if line.strip()) if truth.is_file() else 0,
        "loaded_bank": len(credits),
        "loaded_ledger": len(items),
        "loaded_settlement": len(declared),
        "duplicate_bank_ids": len(dup_credits),
        "duplicate_ledger_ids": len(dup_items),
        "null_bank_ids": sum(1 for i in credit_ids if not i),
        "null_ledger_ids": sum(1 for i in item_ids if not i),
        "orphan_settlement_item_ids": len(orphan_items),
        "orphan_settlement_credit_ids": len(set(orphan_credits)),
        "sample_orphan_items": orphan_items[:8],
        "malformed_bank_amounts": malformed_bank,
        "malformed_ledger_amounts": malformed_ledger,
        "invalid_bank_dates": invalid_bank_dates,
        "invalid_ledger_dates": invalid_ledger_dates,
        "unsupported_bank_currency": sum(1 for c in credits if c.currency != "INR"),
        "unsupported_ledger_currency": sum(1 for i in items if i.currency != "INR"),
        "bank_currencies": dict(bank_ccy),
        "ledger_currencies": dict(ledger_ccy),
        "negative_bank_credits": negative_bank,
        "zero_bank_credits": zero_bank,
        "ledger_kind_counts": dict(kinds),
        "settlement_kind_counts": dict(set_kinds),
        "duplicate_ledger_order_ids": len(dup_orders),
        "settlement_member_id_column": False,
        "fee_gst_withholding_refund_reserve": {
            kind: kinds.get(kind, 0)
            for kind in (
                Kind.FEE.value,
                Kind.TAX_GST.value,
                Kind.TAX_WITHHOLDING.value,
                Kind.REFUND.value,
                Kind.RESERVE_HOLD.value,
                Kind.RESERVE_RELEASE.value,
                Kind.BANK_CHARGE.value,
            )
        },
        "writes_cleared": False,
        "source_modified": False,
    }


def main() -> dict[str, object]:
    payload = {
        "dev": _audit("dev"),
        "test": _audit("test"),
        "fee_config": Path("config").joinpath("fees.yaml").is_file(),
        "tax_config": Path("config").joinpath("tax_rates.yaml").is_file(),
        "writes_cleared": False,
    }
    out = Path("artifacts").joinpath("qa", "dataset_integrity.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    main()
