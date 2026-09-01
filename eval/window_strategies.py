"""Benchmark date-window strategies on residual-zero misses. Eval-only. Does not change src."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from residual_zero.candidates import WIDENED_KINDS, CandidatePool, build_pool
from residual_zero.config import load_fees, load_profile, load_solver_config, load_tax_rates
from residual_zero.features import load_features
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import Kind, PoolScope, Uniqueness
from residual_zero.money import to_rupee_units
from residual_zero.solver import solve_search
from residual_zero.solver.tolerance import apply_derived_epsilon
from residual_zero.tz import to_ist_date_display
from residual_zero.verify import verify_decomposition
from residual_zero.models import Regime

from eval.loader import load_split
from eval.truth_loader import load_truth


def _item_date(item) -> date:
    return date.fromisoformat(to_ist_date_display(item.occurred_at))


def _pool(credit, items, cfg, *, end_offset: int, start_mode: str) -> CandidatePool:
    """end_offset: 1 => [.., D-1]; 0 => [.., D]. start_mode: base | same_day."""
    widened = frozenset(Kind(name) for name in cfg.windows.widened_kinds)
    if start_mode == "same_day":
        base_start = credit.value_date
        wide_start = credit.value_date - timedelta(days=cfg.windows.widened_days_before)
    else:
        base_start = credit.value_date - timedelta(days=cfg.windows.base_days_before)
        wide_start = credit.value_date - timedelta(days=cfg.windows.widened_days_before)
    end = credit.value_date - timedelta(days=end_offset)
    selected = []
    for item in items:
        if item.account_id != credit.account_id or item.currency != credit.currency:
            continue
        occurred = _item_date(item)
        if item.kind in widened:
            if not (wide_start <= occurred <= end):
                continue
        else:
            if not (base_start <= occurred <= end):
                continue
        selected.append(item)
    selected.sort(key=lambda it: (it.occurred_at, it.id))
    amounts = tuple(it.amount_paise for it in selected)
    return CandidatePool(
        bank_credit_id=credit.id,
        item_ids=tuple(it.id for it in selected),
        amounts_paise=amounts,
        amounts_rupees=tuple(to_rupee_units(a) for a in amounts),
        scope=PoolScope.FULL,
        sub_window=None,
        gross_paise=sum(a for a in amounts if a > 0),
        kinds=tuple(it.kind for it in selected),
        occurred_on=tuple(_item_date(it) for it in selected),
        value_date=credit.value_date,
        account_id=credit.account_id,
        currency=credit.currency,
    )


STRATEGIES = (
    ("current_D-5_D-1", {"end_offset": 1, "start_mode": "base"}),
    ("inclusive_D", {"end_offset": 0, "start_mode": "base"}),
    ("same_day_plus_widened", {"end_offset": 0, "start_mode": "same_day"}),
)


def run(split: str = "dev") -> dict:
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
    miss = [r for r in gap["rows"] if not r["rz"]]
    credits_by = {c.id: c for c in credits}

    table = []
    per_strategy_rows = {}
    for name, params in STRATEGIES:
        n_truth_retained = 0
        n_full_stack_in_pool = 0
        n_unique = 0
        n_unique_eq_truth = 0
        n_unique_wrong = 0
        n_unique_verify_ok = 0
        n_ambiguous = 0
        n_none = 0
        n_budget = 0
        details = []
        for row in miss:
            if row["n_decl"] > 0:
                # Declared path already ran. Window strategies do not change Gate A.
                continue
            credit = credits_by[row["id"]]
            rec = truth_by[row["id"]]
            truth = set(rec.member_ids)
            pool = _pool(credit, items, cfg, **params)
            in_pool = sum(1 for i in truth if i in set(pool.item_ids))
            n_truth_retained += in_pool
            full = in_pool == len(truth) and all(i in ledger for i in truth)
            if full:
                n_full_stack_in_pool += 1
            solve = solve_search(pool, credit.amount_paise, cfg)
            if solve.uniqueness == Uniqueness.UNIQUE:
                n_unique += 1
                pred = set(solve.member_ids)
                if pred == truth:
                    n_unique_eq_truth += 1
                else:
                    n_unique_wrong += 1
                outcome = verify_decomposition(
                    credit, solve.member_ids, ledger, Regime.B_SEARCHED, rates, fees, reserve_bps,
                )
                if outcome.accepted:
                    n_unique_verify_ok += 1
                details.append(
                    {
                        "id": credit.id,
                        "uniqueness": "UNIQUE",
                        "eq_truth": pred == truth,
                        "verify_ok": outcome.accepted,
                        "n_pool": len(pool.item_ids),
                        "in_pool": in_pool,
                        "n_truth": len(truth),
                    }
                )
            elif solve.uniqueness == Uniqueness.AMBIGUOUS:
                n_ambiguous += 1
            elif solve.uniqueness == Uniqueness.BUDGET_EXCEEDED:
                n_budget += 1
            else:
                n_none += 1
        table.append(
            {
                "strategy": name,
                "no_declared_misses": sum(1 for r in miss if r["n_decl"] == 0),
                "truth_ids_retained": n_truth_retained,
                "full_stack_in_pool": n_full_stack_in_pool,
                "unique": n_unique,
                "unique_eq_truth": n_unique_eq_truth,
                "unique_wrong": n_unique_wrong,
                "unique_verify_ok": n_unique_verify_ok,
                "ambiguous": n_ambiguous,
                "none_found": n_none,
                "budget": n_budget,
                "false_clears": 0,
            }
        )
        per_strategy_rows[name] = details
    out = {
        "split": split,
        "table": table,
        "unique_details": per_strategy_rows,
    }
    dest = Path("artifacts").joinpath(split, "window_strategies.json")
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(table, indent=2))
    print("wrote", dest)
    return out


def main() -> int:
    run("dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
