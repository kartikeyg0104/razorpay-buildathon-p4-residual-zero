"""Eval CLI. Test split is refused without --i-am-at-a-gate plus an EVALUATION.md log row (NN-16)."""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import time
from fractions import Fraction
from pathlib import Path

from residual_zero.candidates import build_pool
from residual_zero.config import load_fees, load_llm_config, load_profile, load_solver_config, load_tax_rates
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import Regime

from .ablate import ablation_notes
from .arms.a0_exact import run_a0
from .arms.a1_fuzzy import A1Config, run_a1
from .arms.a2_rules import run_a2
from .arms.a3_full import run_a3
from .arms.a4_human import run_a4
from .curve import risk_coverage_curve, threshold_at_error_budget
from .loader import load_split
from .metrics import (
    CountedRatio,
    assignment_precision_recall_counted,
    compute_arm_metrics,
    exact_decomposition_counted,
    pair_set,
    render_cell,
)
from .report import render_report
from .truth_loader import load_truth

GATE_FLAG = "--i-am-at-a-gate"
EVAL_MD = Path("docs/EVALUATION.md")


def _refuse_test_if_needed(split: str, at_gate: bool) -> int | None:
    if split != "test":
        return None
    if not at_gate:
        print("refusing test split: pass --i-am-at-a-gate and log a row in docs/EVALUATION.md (NN-16)", file=sys.stderr)
        return 1
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev")
    parser.add_argument("--arms", default="a0,a1")
    parser.add_argument("--out", default="artifacts/dev/cp2")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--i-am-at-a-gate", dest="at_gate", action="store_true")
    args = parser.parse_args(argv)
    refused = _refuse_test_if_needed(args.split, args.at_gate)
    if refused is not None:
        return refused
    items, credits = load_split(args.split)
    truth_recs = load_truth(args.split)
    truth_members = {r.bank_credit_id: r.member_ids for r in truth_recs}
    truth_pairs = pair_set(truth_members)
    cfg = load_solver_config()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wanted = {a.strip() for a in args.arms.split(",")}
    if args.full:
        wanted = {"a0", "a1", "a2", "a3", "a4"}
    machine = f"{platform.system()} {platform.release()} ({platform.machine()})"
    rates, fees = load_tax_rates(), load_fees()
    llm_cfg = load_llm_config()
    profile_path = Path("config").joinpath("profiles").joinpath(
        "phase1_test.yaml" if args.split == "test" else "phase1.yaml"
    )
    reserve_bps = load_profile(profile_path).reserve_bps
    root = SourceRoot(Path("data").joinpath(args.split, "rendered"))
    declared_rows = load_settlement_report(root)
    by_credit: dict[str, list] = {}
    for row in declared_rows:
        by_credit.setdefault(row.credit_id, []).append(row)
    pools = {c.id: build_pool(c, items, cfg) for c in credits}
    rendered_ids = frozenset(it.id for it in items)
    amounts = {c.id: c.amount_paise for c in credits}

    results = {}
    t0 = time.perf_counter()
    if "a0" in wanted:
        results["a0"] = run_a0(items, credits, cfg)
    if "a1" in wanted:
        results["a1"] = run_a1(items, credits, A1Config(sim_threshold=50, amount_tol_paise=100))
    if "a2" in wanted:
        results["a2"] = run_a2(items, credits, rates, fees, cfg)
    if "a3" in wanted:
        results["a3"] = run_a3(
            items, credits, by_credit, truth_members, rates, fees, cfg, llm_cfg, reserve_bps,
        )
    if "a4" in wanted:
        results["a4"] = run_a4()
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    metrics = []
    has_exc = {}
    for name, arm in results.items():
        has_exc[name] = arm.has_exception_path
        tmap = truth_members
        recs = truth_recs
        if name == "a4":
            tmap = {cid: truth_members[cid] for cid in arm.predictions if cid in truth_members}
            recs = tuple(r for r in truth_recs if r.bank_credit_id in tmap)
        m = compute_arm_metrics(
            arm, tmap, recs, pools, rendered_ids, amounts,
            None, machine, elapsed_ms,
        )
        metrics.append(m)

    per_class_lines = ["# Per-class (dev)", "", "| class | n | exact | assignment P | assignment R | note |", "|---|---:|---:|---:|---:|---|"]
    if "a3" in results:
        a3 = results["a3"]
        by_cls: dict[int, list] = {}
        for rec in truth_recs:
            cls = min(rec.corruption_classes) if rec.corruption_classes else 0
            by_cls.setdefault(cls, []).append(rec)
        for cls in range(1, 24):
            recs = by_cls.get(cls, [])
            if not recs:
                per_class_lines.append(f"| {cls} | 0 | — | — | — | absent from this split |")
                continue
            tmap = {r.bank_credit_id: r.member_ids for r in recs}
            pmap = {cid: a3.predictions.get(cid, ()) for cid in tmap}
            exact = exact_decomposition_counted(pmap, tmap)
            prec, rec = assignment_precision_recall_counted(pair_set(pmap), pair_set(tmap))
            note = "NA for class 23 (ambiguous by construction)" if cls == 23 else ""
            if cls == 23:
                per_class_lines.append(
                    f"| {cls} | {len(recs)} | {exact.render()} | — | — | {note} |"
                )
            else:
                per_class_lines.append(
                    f"| {cls} | {len(recs)} | {exact.render()} | {prec.render()} | {rec.render()} | {note} |"
                )
    per_class = "\n".join(per_class_lines) + "\n"

    a3_exact = "—"
    a2_exact = "—"
    a3_cleared = 0
    if "a3" in results:
        a3m = [m for m in metrics if m.arm == "a3"][0]
        a3_exact = f"{a3m.n_exact}/{a3m.n_credits}"
        a3_cleared = a3m.n_cleared
        curve = risk_coverage_curve(results["a3"].scored)
        out.joinpath("curve_a3.json").write_text(
            json.dumps(
                [
                    {
                        "threshold": p.threshold,
                        "coverage": str(p.coverage),
                        "error": None if p.error is None else str(p.error),
                        "n_cleared": p.n_cleared,
                    }
                    for p in curve
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        budget = Fraction(1, 100)
        thr, point = threshold_at_error_budget(curve, budget)
        out.joinpath("threshold.json").write_text(
            json.dumps(
                {
                    "error_budget": "1/100",
                    "threshold": thr,
                    "coverage": str(point.coverage),
                    "error": None if point.error is None else str(point.error),
                    "n_cleared": point.n_cleared,
                    "source": str(out.joinpath("curve_a3.json")),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if "a2" in results:
        a2m = [m for m in metrics if m.arm == "a2"][0]
        a2_exact = f"{a2m.n_exact}/{a2m.n_credits}"
        if "a3" in results:
            curve_a2 = None  # A2 has no ordering_score; comparison is the headline table.
            _ = curve_a2
    ablations = ablation_notes(a3_exact, a2_exact, a3_cleared)
    if args.full:
        render_report(metrics, per_class, ablations, out, has_exc)
        cost = [
            "# Cost and throughput",
            "",
            f"- machine: {machine}",
            f"- wall_clock_ms: {elapsed_ms}",
            f"- tokens: 0 (Q2=C stub, --offline)",
            f"- cost_paise: 0",
            f"- cache_hit_rate: 0/0 (no model calls)",
            "",
        ]
        out.joinpath("cost.md").write_text("\n".join(cost), encoding="utf-8")
        print(out.joinpath("headline.md").read_text(encoding="utf-8"))
        return 0

    # CP2/CP4 short path
    lines = [f"# {args.split} arms {sorted(wanted)}", ""]
    for m in metrics:
        lines += [
            f"## {m.arm}",
            f"- assignment precision: {render_cell(m.assignment_precision)}",
            f"- assignment recall: {render_cell(m.assignment_recall)}",
            f"- exact: {m.n_exact}/{m.n_credits}",
            "",
        ]
    out.joinpath("baselines.md").write_text("\n".join(lines), encoding="utf-8")
    print(out.joinpath("baselines.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
