"""Transaction-level forensic of residual-zero misses. Eval-only. Never imported by src."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from residual_zero.candidates import WIDENED_KINDS, build_pool
from residual_zero.config import load_fees, load_profile, load_solver_config, load_tax_rates
from residual_zero.features import load_features
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import Kind
from residual_zero.solver.fastpath import DeclaredLine, verify_declared
from residual_zero.solver.tolerance import apply_derived_epsilon
from residual_zero.tz import to_ist_date_display

from eval.loader import load_split
from eval.truth_loader import load_truth


def _item_date(item) -> date:
    return date.fromisoformat(to_ist_date_display(item.occurred_at))


def _kind_sum(ids, ledger, kinds) -> int:
    return sum(ledger[i].amount_paise for i in ids if i in ledger and ledger[i].kind in kinds)


def classify_row(r: dict) -> str:
    if r["fail"] == "TRUTH_ID_MISSING":
        return "TRUTH_LEDGER_ID_MISSING"
    if r["fail"] == "WINDOW_REMOVED_TRUTH":
        return "TRUTH_OUTSIDE_CURRENT_WINDOW"
    if r["fail"] == "IN_POOL_SEARCH_AMBIGUOUS":
        return "TRUTH_IN_POOL_BUT_AMBIGUOUS"
    if r["fail"] == "LINKED_VERIFY_FAIL" and 8 in r["corrupt"]:
        return "CORRUPTED_SETTLEMENT_AND_LEDGER"
    if r["fail"] == "DECLARED_WRONG" and 13 in r["corrupt"]:
        return "WITHHOLDING_MISMATCH"
    if r["fail"] == "DECLARED_WRONG" and 11 in r["corrupt"]:
        return "REFUND_MISMATCH"
    if r["fail"] == "DECLARED_WRONG":
        return "OTHER"
    if r["fail"] == "LINKED_VERIFY_FAIL":
        return "FEE_MISMATCH"
    return "OTHER"


def analyse(split: str = "dev") -> dict:
    items, credits = load_split(split)
    truth_recs = load_truth(split)
    truth_by = {r.bank_credit_id: r for r in truth_recs}
    ledger = {it.id: it for it in items}
    cfg = apply_derived_epsilon(load_solver_config(), load_features())
    rates, fees = load_tax_rates(), load_fees()
    profile = "phase1_test.yaml" if split == "test" else "phase1.yaml"
    reserve_bps = load_profile(Path("config").joinpath("profiles").joinpath(profile)).reserve_bps
    root = SourceRoot(Path("data").joinpath(split, "rendered"))
    by_credit: dict[str, list] = {}
    for row in load_settlement_report(root):
        by_credit.setdefault(row.credit_id, []).append(row)
    gap = json.loads(Path("artifacts").joinpath(split, "gap_analysis.json").read_text())
    miss_ids = [r["id"] for r in gap["rows"] if not r["rz"]]
    credits_by = {c.id: c for c in credits}

    traces = []
    for cid in miss_ids:
        rec = truth_by[cid]
        credit = credits_by[cid]
        gap_row = next(r for r in gap["rows"] if r["id"] == cid)
        truth_ids = list(rec.member_ids)
        declared = by_credit.get(cid, [])
        pool = build_pool(credit, items, cfg)
        pool_ids = set(pool.item_ids)
        missing = [i for i in truth_ids if i not in ledger]
        in_pool = [i for i in truth_ids if i in pool_ids]
        out_window = []
        for iid in truth_ids:
            item = ledger.get(iid)
            if item is None:
                continue
            if iid not in pool_ids:
                out_window.append(
                    {
                        "id": iid,
                        "kind": item.kind.value,
                        "occurred": _item_date(item).isoformat(),
                        "delta_days": (_item_date(item) - credit.value_date).days,
                    }
                )
        kind_counts = Counter(
            ledger[i].kind.value if i in ledger else "MISSING" for i in truth_ids
        )
        traces.append(
            {
                "transaction_id": cid,
                "bank_amount_paise": credit.amount_paise,
                "value_date": credit.value_date.isoformat(),
                "account": credit.account_id,
                "currency": credit.currency,
                "utr": credit.utr or "",
                "regime": rec.regime.value,
                "corrupt": list(rec.corruption_classes),
                "ground_truth_count": len(truth_ids),
                "truth_ids_in_pool": len(in_pool),
                "truth_ids_missing_ledger": missing,
                "n_pool": len(pool.item_ids),
                "n_settlement": len(declared),
                "settlement_item_ids": [r.item_id for r in declared],
                "ledger_ops_paise": sum(
                    ledger[i].amount_paise
                    for i in truth_ids
                    if i in ledger and ledger[i].kind not in {
                        Kind.FEE, Kind.TAX_GST, Kind.TAX_WITHHOLDING, Kind.RESERVE_HOLD,
                    }
                ),
                "settlement_ops_paise": sum(
                    r.amount_paise
                    for r in declared
                    if r.kind not in {Kind.FEE, Kind.TAX_GST, Kind.TAX_WITHHOLDING, Kind.RESERVE_HOLD}
                ),
                "fee_ledger": _kind_sum(truth_ids, ledger, {Kind.FEE}),
                "gst_ledger": _kind_sum(truth_ids, ledger, {Kind.TAX_GST}),
                "withholding_ledger": _kind_sum(truth_ids, ledger, {Kind.TAX_WITHHOLDING}),
                "refund_ledger": _kind_sum(truth_ids, ledger, {Kind.REFUND}),
                "reserve_ledger": _kind_sum(truth_ids, ledger, {Kind.RESERVE_HOLD}),
                "kind_counts": dict(kind_counts),
                "out_of_window": out_window,
                "fp_decl_ok": gap_row["fp_decl_ok"],
                "fp_truth_ok": gap_row["fp_truth_ok"],
                "settle_ops_eq": gap_row["settle_ops_eq"],
                "posted_eq": gap_row["posted_eq"],
                "fail": gap_row["fail"],
                "category": classify_row(gap_row),
            }
        )

    cats = Counter(t["category"] for t in traces)
    dest = Path("artifacts").joinpath(split, "deep_misses.json")
    summary = {
        "split": split,
        "n_miss": len(traces),
        "categories": dict(cats),
        "regime_on_miss": dict(Counter(t["regime"] for t in traces)),
        "fp_truth_ok_among_miss": sum(1 for t in traces if t["fp_truth_ok"]),
        "n_with_settlement": sum(1 for t in traces if t["n_settlement"] > 0),
    }
    dest.write_text(json.dumps({"summary": summary, "rows": traces}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("wrote", dest)
    return summary


def main() -> int:
    analyse("dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
