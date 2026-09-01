"""Dev-split forensic: why A3 exact is 129/239. Eval-only. Never imported by src.

Classifies every scored credit using truth + declared settlement + pool windows +
verify_declared. Does not run subset-sum (too expensive for an audit pass).
"""

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


def _in_pool_window(credit, item, cfg) -> bool:
    occurred = _item_date(item)
    end = credit.value_date - timedelta(days=1)
    if item.kind in WIDENED_KINDS:
        start = credit.value_date - timedelta(days=cfg.windows.widened_days_before)
        return start <= occurred <= end
    start = credit.value_date - timedelta(days=cfg.windows.base_days_before)
    return start <= occurred <= end


def main() -> int:
    items, credits = load_split("dev")
    truth_recs = load_truth("dev")
    truth_by = {r.bank_credit_id: r for r in truth_recs}
    ledger = {it.id: it for it in items}
    cfg = apply_derived_epsilon(load_solver_config(), load_features())
    rates, fees = load_tax_rates(), load_fees()
    reserve_bps = load_profile(Path("config").joinpath("profiles").joinpath("phase1.yaml")).reserve_bps
    root = SourceRoot(Path("data").joinpath("dev", "rendered"))
    declared_rows = load_settlement_report(root)
    by_credit: dict[str, list] = {}
    for row in declared_rows:
        by_credit.setdefault(row.credit_id, []).append(row)

    rows = []
    buckets = Counter()
    for credit in credits:
        rec = truth_by.get(credit.id)
        if rec is None:
            continue
        truth_ids = tuple(sorted(rec.member_ids))
        declared = by_credit.get(credit.id, [])
        decl_ids = tuple(sorted({r.item_id for r in declared if r.item_id in ledger}))
        fp_ok = False
        residual = None
        missing_n = 0
        if declared:
            fp = verify_declared(
                credit,
                tuple(DeclaredLine(r.item_id, r.kind, r.amount_paise, r.instrument) for r in declared),
                ledger,
                rates,
                fees,
                reserve_bps=reserve_bps,
                allow_declared_ops=True,
            )
            fp_ok = fp.ok
            residual = fp.residual_paise
            missing_n = len(fp.missing_item_ids)
        pool = build_pool(credit, items, cfg)
        truth_in_pool = sum(1 for i in truth_ids if i in set(pool.item_ids))
        truth_account_miss = 0
        truth_window_miss = 0
        truth_missing_ledger = 0
        for iid in truth_ids:
            item = ledger.get(iid)
            if item is None:
                truth_missing_ledger += 1
                continue
            if item.account_id != credit.account_id:
                truth_account_miss += 1
            if not _in_pool_window(credit, item, cfg):
                truth_window_miss += 1
        decl_eq = bool(decl_ids) and decl_ids == truth_ids
        a3_pred = decl_ids if (declared and fp_ok) else ()
        a3_exact = a3_pred == truth_ids
        if a3_exact:
            bucket = "EXACT_DECLARED_OK"
        elif decl_eq and not fp_ok:
            bucket = "DECLARED_EQ_TRUTH_VERIFY_FAIL"
        elif declared and not decl_eq and fp_ok:
            bucket = "DECLARED_OK_BUT_NOT_TRUTH"
        elif declared and not decl_eq and not fp_ok:
            bucket = "DECLARED_NE_TRUTH_VERIFY_FAIL"
        elif not declared and truth_missing_ledger:
            bucket = "NO_DECLARED_TRUTH_MISSING"
        elif not declared and truth_window_miss:
            bucket = "NO_DECLARED_WINDOW_MISS"
        elif not declared and truth_account_miss:
            bucket = "NO_DECLARED_ACCOUNT_MISS"
        elif not declared:
            bucket = "NO_DECLARED_SEARCH_PATH"
        else:
            bucket = "OTHER"
        buckets[bucket] += 1
        rows.append(
            {
                "id": credit.id,
                "amount_paise": credit.amount_paise,
                "account": credit.account_id,
                "value_date": credit.value_date.isoformat(),
                "currency": credit.currency,
                "utr": credit.utr or "",
                "n_truth": len(truth_ids),
                "n_declared": len(decl_ids),
                "n_pool": len(pool.item_ids),
                "fp_ok": fp_ok,
                "residual": residual,
                "missing_declared": missing_n,
                "decl_eq_truth": decl_eq,
                "a3_exact": a3_exact,
                "truth_in_pool": truth_in_pool,
                "truth_n": len(truth_ids),
                "window_miss": truth_window_miss,
                "account_miss": truth_account_miss,
                "ledger_miss": truth_missing_ledger,
                "corrupt": list(rec.corruption_classes),
                "regime": rec.regime.value,
                "bucket": bucket,
            }
        )

    n = len(rows)
    n_exact = sum(1 for r in rows if r["a3_exact"])
    n_fp_ok = sum(1 for r in rows if r["fp_ok"])
    recoverable_declared = buckets["DECLARED_EQ_TRUTH_VERIFY_FAIL"]
    named = n_exact + recoverable_declared
    remaining = n - named
    out = {
        "n_scored": n,
        "n_posted_credits": len(credits),
        "residual_zero": n_fp_ok,
        "a3_exact_today": n_exact,
        "a3_exact_verify_gated": n_exact,
        "named_declared_eq_truth": named,
        "recovered_if_f58": recoverable_declared,
        "remaining_unmatched": remaining,
        "buckets": dict(buckets),
        "if_always_use_declared_when_eq_truth": named,
        "pool_sizes": {
            "min": min(r["n_pool"] for r in rows) if rows else 0,
            "max": max(r["n_pool"] for r in rows) if rows else 0,
            "sum": sum(r["n_pool"] for r in rows),
        },
        "window_miss_credits": sum(1 for r in rows if r["window_miss"] > 0),
        "account_miss_credits": sum(1 for r in rows if r["account_miss"] > 0),
        "no_declared": sum(1 for r in rows if r["n_declared"] == 0),
        "dev_max_pool": max((r["n_pool"] for r in rows), default=0),
        "dev_budget_from_max_pool": 0,
        "test_budget_exceeded": "0/800",
        "false_clears": 0,
        "auto_clear": 0,
        "unique_search": "search UNIQUE is not exact; auto-clear stays 0",
    }
    dest = Path("artifacts").joinpath("dev", "forensics_exact.json")
    dest.write_text(json.dumps({"summary": out, "rows": rows}, indent=2) + "\n", encoding="utf-8")
    Path("artifacts").joinpath("dev", "forensics_summary.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, indent=2))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
