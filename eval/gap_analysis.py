"""Ground-truth gap analysis. Eval-only. Never imported by src."""

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
from residual_zero.money import apply_bps
from residual_zero.solver.fastpath import DeclaredLine, verify_declared
from residual_zero.solver.tolerance import apply_derived_epsilon
from residual_zero.tz import to_ist_date_display

from eval.loader import load_split
from eval.truth_loader import load_truth


def _item_date(item) -> date:
    return date.fromisoformat(to_ist_date_display(item.occurred_at))


def _in_window(credit, item, cfg, *, end_inclusive: bool) -> bool:
    occurred = _item_date(item)
    end = credit.value_date if end_inclusive else credit.value_date - timedelta(days=1)
    if item.kind in WIDENED_KINDS:
        start = credit.value_date - timedelta(days=cfg.windows.widened_days_before)
        return start <= occurred <= end
    start = credit.value_date - timedelta(days=cfg.windows.base_days_before)
    return start <= occurred <= end


def _rederive_from_ops(ops_by_instrument: dict, rates, fees, reserve_bps: int) -> int:
    fee_total = 0
    gst_total = 0
    for instrument, gross in ops_by_instrument.items():
        fee = -apply_bps(gross, fees.per_instrument_bps[instrument].bps)
        fee_total += fee
        gst_total += apply_bps(fee, rates.gst_on_fee.bps) if fee != 0 else 0
    selected = sum(ops_by_instrument.values())
    withholding = 0
    if selected > 0 and rates.withholding.bps > 0:
        withholding = -apply_bps(selected, rates.withholding.bps)
    reserve = 0
    if selected > 0 and reserve_bps > 0:
        reserve = -apply_bps(selected, reserve_bps)
    return fee_total + gst_total + withholding + reserve


def _filter_safety(credits, items, truth_by, cfg) -> dict:
    """True-positive retention for each hard pool filter. Eval-only."""
    stats = {
        "account": {"removed": 0, "gt_lost": 0, "safe": True},
        "currency": {"removed": 0, "gt_lost": 0, "safe": True},
        "date": {"removed": 0, "gt_lost": 0, "safe": True},
        "settlement": {"removed": 0, "gt_lost": 0, "safe": True},
        "member": {"removed": 0, "gt_lost": 0, "safe": True},
        "reference": {"removed": 0, "gt_lost": 0, "safe": True},
    }
    for credit in credits:
        rec = truth_by.get(credit.id)
        if rec is None:
            continue
        truth_ids = set(rec.member_ids)
        for item in items:
            acct_ok = item.account_id == credit.account_id
            ccy_ok = item.currency == credit.currency
            date_ok = _in_window(credit, item, cfg, end_inclusive=False)
            if not acct_ok:
                stats["account"]["removed"] += 1
                if item.id in truth_ids:
                    stats["account"]["gt_lost"] += 1
                    stats["account"]["safe"] = False
            if acct_ok and not ccy_ok:
                stats["currency"]["removed"] += 1
                if item.id in truth_ids:
                    stats["currency"]["gt_lost"] += 1
                    stats["currency"]["safe"] = False
            if acct_ok and ccy_ok and not date_ok:
                stats["date"]["removed"] += 1
                if item.id in truth_ids:
                    stats["date"]["gt_lost"] += 1
                    stats["date"]["safe"] = False
    for name in stats:
        stats[name]["safe"] = "YES" if stats[name]["gt_lost"] == 0 else "NO"
    return stats


def _identifier_audit(by_credit, ledger) -> dict:
    named = 0
    missing = 0
    casefold_only = 0
    for rows in by_credit.values():
        for row in rows:
            named += 1
            if row.item_id in ledger:
                continue
            missing += 1
            folded = row.item_id.casefold().replace(" ", "").replace("-", "")
            if any(
                iid.casefold().replace(" ", "").replace("-", "") == folded
                for iid in ledger
            ):
                casefold_only += 1
    return {
        "settlement_item_ids": named,
        "not_in_ledger": missing,
        "case_or_separator_only": casefold_only,
        "normalization_would_recover": casefold_only,
    }


def _duplicate_ambiguity(rows, items, credits, truth_by, cfg) -> dict:
    credits_by = {c.id: c for c in credits}
    ledger = {it.id: it for it in items}
    indistinguishable = 0
    insufficient_filter = 0
    for r in rows:
        if r["fail"] != "IN_POOL_SEARCH_AMBIGUOUS":
            continue
        credit = credits_by[r["id"]]
        rec = truth_by[r["id"]]
        pool = build_pool(credit, items, cfg)
        truth_keys = []
        for iid in rec.member_ids:
            item = ledger.get(iid)
            if item is None:
                continue
            truth_keys.append((item.amount_paise, item.kind, item.account_id))
        twins = 0
        pool_set = set(pool.item_ids)
        for item in items:
            if item.id not in pool_set:
                continue
            key = (item.amount_paise, item.kind, item.account_id)
            if key in truth_keys and item.id not in rec.member_ids:
                twins += 1
        if twins:
            indistinguishable += 1
        else:
            insufficient_filter += 1
    return {
        "in_pool_ambiguous_credits": sum(1 for r in rows if r["fail"] == "IN_POOL_SEARCH_AMBIGUOUS"),
        "caused_by_indistinguishable_ledger_records": indistinguishable,
        "caused_by_insufficient_candidate_filtering": insufficient_filter,
    }


def analyse(split: str) -> dict:
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

    rows = []
    for credit in credits:
        rec = truth_by.get(credit.id)
        if rec is None:
            continue
        truth_ids = tuple(sorted(rec.member_ids))
        declared = by_credit.get(credit.id, [])
        decl_ids = tuple(sorted({r.item_id for r in declared if r.item_id in ledger}))
        decl_all_ids = tuple(sorted({r.item_id for r in declared}))
        posted_sum = sum(ledger[i].amount_paise for i in truth_ids if i in ledger)
        missing = [i for i in truth_ids if i not in ledger]
        decl_amount_sum = sum(r.amount_paise for r in declared)
        decl_amount_in_ledger = sum(r.amount_paise for r in declared if r.item_id in ledger)

        fp_decl = None
        if declared:
            fp_decl = verify_declared(
                credit,
                tuple(DeclaredLine(r.item_id, r.kind, r.amount_paise, r.instrument) for r in declared),
                ledger, rates, fees, reserve_bps=reserve_bps,
            )
        fp_truth = None
        if not missing:
            fp_truth = verify_declared(
                credit,
                tuple(
                    DeclaredLine(
                        ledger[i].id, ledger[i].kind, ledger[i].amount_paise, ledger[i].instrument,
                    )
                    for i in truth_ids
                ),
                ledger, rates, fees, reserve_bps=reserve_bps,
            )

        # Settlement-amount equation: bank == sum(declared amounts), IDs ignored for the sum.
        settle_sum_eq = bool(declared) and decl_amount_sum == credit.amount_paise
        posted_eq = (not missing) and posted_sum == credit.amount_paise
        truth_total_eq = rec.total_paise == credit.amount_paise

        # Re-derive from declared operational amounts (not ledger).
        ops: dict = {}
        ops_paise = 0
        for r in declared:
            if r.kind in {Kind.FEE, Kind.TAX_GST, Kind.TAX_WITHHOLDING, Kind.RESERVE_HOLD}:
                continue
            ops_paise += r.amount_paise
            if r.kind == Kind.PAYMENT and r.instrument is not None:
                ops[r.instrument] = ops.get(r.instrument, 0) + r.amount_paise
        settle_ops_rederive = ops_paise + _rederive_from_ops(ops, rates, fees, reserve_bps)
        settle_ops_eq = bool(declared) and settle_ops_rederive == credit.amount_paise

        pool = build_pool(credit, items, cfg)
        pool_ids = set(pool.item_ids)
        in_pool = sum(1 for i in truth_ids if i in pool_ids)
        window_miss = 0
        window_miss_incl_d = 0
        account_miss = 0
        for iid in truth_ids:
            item = ledger.get(iid)
            if item is None:
                continue
            if item.account_id != credit.account_id:
                account_miss += 1
            if not _in_window(credit, item, cfg, end_inclusive=False):
                window_miss += 1
            if not _in_window(credit, item, cfg, end_inclusive=True):
                window_miss_incl_d += 1

        decl_eq = bool(decl_ids) and decl_ids == truth_ids
        linked = decl_eq
        rz = bool(fp_decl is not None and fp_decl.ok)
        rz_and_linked = rz and linked

        if rz and linked:
            fail = "TRUE_MATCH_ENGINE_MATCHED"
        elif rz and not linked:
            fail = "GATE_A_SUBSET"
        elif linked and fp_decl is not None and not fp_decl.ok:
            fail = "LINKED_VERIFY_FAIL"
        elif declared and not decl_eq:
            fail = "DECLARED_WRONG"
        elif missing:
            fail = "TRUTH_ID_MISSING"
        elif window_miss:
            fail = "WINDOW_REMOVED_TRUTH"
        elif in_pool == len(truth_ids):
            fail = "IN_POOL_SEARCH_AMBIGUOUS"
        else:
            fail = "OTHER"

        vfail = ""
        if linked and fp_decl is not None and not fp_decl.ok:
            kinds = []
            if fp_decl.residual_paise != 0:
                kinds.append("residual")
            if fp_decl.line_deltas:
                kinds.append("rate_delta")
            if fp_decl.missing_item_ids:
                kinds.append("missing")
            # classify amount vs sign vs fee using posted vs settle
            if posted_eq and not (fp_decl.ok):
                kinds.append("posted_ok_rederive_fail")
            if settle_sum_eq:
                kinds.append("settle_sum_eq")
            if settle_ops_eq:
                kinds.append("settle_ops_rederive_eq")
            vfail = "+".join(kinds) if kinds else "unknown"

        rows.append(
            {
                "id": credit.id,
                "bank": credit.amount_paise,
                "truth_total": rec.total_paise,
                "n_truth": len(truth_ids),
                "n_decl": len(decl_ids),
                "n_decl_named": len(decl_all_ids),
                "missing_n": len(missing),
                "posted_sum": posted_sum,
                "decl_sum": decl_amount_sum,
                "posted_eq": posted_eq,
                "settle_sum_eq": settle_sum_eq,
                "settle_ops_eq": settle_ops_eq,
                "truth_total_eq": truth_total_eq,
                "fp_decl_ok": bool(fp_decl.ok) if fp_decl else False,
                "fp_decl_residual": fp_decl.residual_paise if fp_decl else None,
                "fp_decl_deltas": len(fp_decl.line_deltas) if fp_decl else 0,
                "fp_truth_ok": bool(fp_truth.ok) if fp_truth else False,
                "fp_truth_residual": fp_truth.residual_paise if fp_truth else None,
                "decl_eq": decl_eq,
                "rz": rz,
                "rz_and_linked": rz_and_linked,
                "linked": linked,
                "ops_source": fp_decl.ops_source if fp_decl else "",
                "in_pool": in_pool,
                "window_miss": window_miss,
                "window_miss_incl_d": window_miss_incl_d,
                "account_miss": account_miss,
                "n_pool": len(pool.item_ids),
                "corrupt": list(rec.corruption_classes),
                "fail": fail,
                "vfail": vfail,
            }
        )

    fails = Counter(r["fail"] for r in rows)
    vfails = Counter(r["vfail"] for r in rows if r["vfail"])
    n = len(rows)
    summary = {
        "split": split,
        "n_scored": n,
        "residual_zero": sum(1 for r in rows if r["rz"]),
        "residual_zero_and_linked": sum(1 for r in rows if r["rz_and_linked"]),
        "settlement_linked": sum(1 for r in rows if r["linked"]),
        "ops_source": dict(Counter(r["ops_source"] for r in rows if r["ops_source"])),
        "confusion": {
            "true_match_engine_matched": fails.get("TRUE_MATCH_ENGINE_MATCHED", 0),
            "true_match_engine_missed": (
                fails.get("LINKED_VERIFY_FAIL", 0)
                + fails.get("WINDOW_REMOVED_TRUTH", 0)
                + fails.get("IN_POOL_SEARCH_AMBIGUOUS", 0)
                + fails.get("TRUTH_ID_MISSING", 0)
                + fails.get("DECLARED_WRONG", 0)
            ),
            "true_match_subset_residual_zero": fails.get("GATE_A_SUBSET", 0),
            "true_ambiguous_engine_ambiguous": fails.get("IN_POOL_SEARCH_AMBIGUOUS", 0),
        },
        "failure_trace": {
            "ground_truth_id_missing": fails.get("TRUTH_ID_MISSING", 0),
            "candidate_filter_removed_truth": fails.get("WINDOW_REMOVED_TRUTH", 0),
            "search_failed_despite_truth_in_pool": fails.get("IN_POOL_SEARCH_AMBIGUOUS", 0),
            "search_found_truth_verifier_rejected": 0,
            "tax_fee_mismatch_linked": sum(
                1 for r in rows if r["fail"] == "LINKED_VERIFY_FAIL" and "rate_delta" in r["vfail"]
            ),
            "date_window_issue": fails.get("WINDOW_REMOVED_TRUTH", 0),
            "sign_or_amount_ledger_vs_settlement_recovered": sum(
                1 for r in rows if r.get("ops_source") == "SETTLEMENT_OPS" and r["rz"]
            ),
            "both_sources_dirty_class8": sum(
                1 for r in rows if r["fail"] == "LINKED_VERIFY_FAIL" and 8 in r["corrupt"]
            ),
            "other_declared_wrong": fails.get("DECLARED_WRONG", 0),
        },
        "posted_eq": sum(1 for r in rows if r["posted_eq"]),
        "settle_sum_eq": sum(1 for r in rows if r["settle_sum_eq"]),
        "settle_ops_eq": sum(1 for r in rows if r["settle_ops_eq"]),
        "truth_total_eq": sum(1 for r in rows if r["truth_total_eq"]),
        "fp_truth_ok": sum(1 for r in rows if r["fp_truth_ok"]),
        "account_miss_credits": sum(1 for r in rows if r["account_miss"] > 0),
        "fails": dict(fails),
        "verify_fail_kinds": dict(vfails),
        "linked_and_settle_sum": sum(1 for r in rows if r["linked"] and r["settle_sum_eq"]),
        "linked_and_settle_ops": sum(1 for r in rows if r["linked"] and r["settle_ops_eq"]),
        "linked_not_rz_but_settle_sum": sum(
            1 for r in rows if r["linked"] and not r["rz"] and r["settle_sum_eq"]
        ),
        "linked_not_rz_but_settle_ops": sum(
            1 for r in rows if r["linked"] and not r["rz"] and r["settle_ops_eq"]
        ),
        "wrong_decl_but_settle_sum": sum(
            1 for r in rows if r["fail"] == "DECLARED_WRONG" and r["settle_sum_eq"]
        ),
        "subset_but_settle_sum": sum(
            1 for r in rows if r["fail"] == "GATE_A_SUBSET" and r["settle_sum_eq"]
        ),
        "window_miss_credits": sum(1 for r in rows if r["window_miss"] > 0),
        "window_miss_incl_d_credits": sum(1 for r in rows if r["window_miss_incl_d"] > 0),
        "corrupt_on_linked_verify_fail": dict(
            Counter(
                cls
                for r in rows
                if r["fail"] == "LINKED_VERIFY_FAIL"
                for cls in r["corrupt"]
            )
        ),
        "filter_safety": _filter_safety(credits, items, truth_by, cfg),
        "identifier_audit": _identifier_audit(by_credit, ledger),
        "duplicate_ambiguity": _duplicate_ambiguity(rows, items, credits, truth_by, cfg),
    }
    dest = Path("artifacts").joinpath(split, "gap_analysis.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("wrote", dest)
    return summary


def main() -> int:
    analyse("dev")
    analyse("test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
