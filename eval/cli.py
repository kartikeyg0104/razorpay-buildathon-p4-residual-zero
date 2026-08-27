"""Run A0/A1 on a split. ``python -m eval.cli --split dev --arms a0,a1 --out artifacts/dev/cp2``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from residual_zero.config import load_solver_config

from .arms.a0_exact import run_a0
from .arms.a1_fuzzy import A1Config, SIM_GRID, TOL_GRID, run_a1, tune_a1_on_dev
from .loader import load_split
from .metrics import assignment_precision_recall_counted, exact_decomposition_counted, pair_set
from .truth_loader import load_truth


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev")
    parser.add_argument("--arms", default="a0,a1")
    parser.add_argument("--out", default="artifacts/dev/cp2")
    args = parser.parse_args(argv)
    items, credits = load_split(args.split)
    truth_recs = load_truth(args.split)
    truth_members = {r.bank_credit_id: r.member_ids for r in truth_recs}
    truth_pairs = pair_set(truth_members)
    cfg = load_solver_config()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# CP2 baselines (dev)", "", "A0 and A1 measured **before** the solver exists (NN-13).", ""]
    wanted = {a.strip() for a in args.arms.split(",")}
    if "a0" in wanted:
        a0 = run_a0(items, credits, cfg)
        p, r = assignment_precision_recall_counted(pair_set(a0.predictions), truth_pairs)
        exact = exact_decomposition_counted(a0.predictions, truth_members)
        lines += [
            "## A0 exact match",
            f"- assignment precision: {p.render()}",
            f"- assignment recall: {r.render()}",
            f"- exact decomposition: {exact.render()}",
            "- exception path: — (none)",
            "- budget path: — (none)",
            "",
        ]
    if "a1" in wanted:
        chosen, log = tune_a1_on_dev(items, credits, truth_members)
        a1 = run_a1(items, credits, chosen)
        p, r = assignment_precision_recall_counted(pair_set(a1.predictions), truth_pairs)
        exact = exact_decomposition_counted(a1.predictions, truth_members)
        lines += [
            "## A1 fuzzy 1:1 (optimal assignment)",
            f"- chosen sim_threshold: {chosen.sim_threshold}",
            f"- chosen amount_tol_paise: {chosen.amount_tol_paise}",
            f"- assignment precision: {p.render()}",
            f"- assignment recall: {r.render()}",
            f"- exact decomposition: {exact.render()}",
            "- exception path: — (none)",
            "- budget path: — (none)",
            "",
            "A1's similarity threshold and amount tolerance were swept on the dev split and fixed at the",
            "values that maximised A1's own exact-decomposition rate.",
            "",
        ]
        eval_md = Path("docs/EVALUATION.md")
        _append_tuning(eval_md, chosen, log)
    if "a2" in wanted:
        from residual_zero.config import load_fees, load_tax_rates
        from .arms.a2_rules import run_a2
        a2 = run_a2(items, credits, load_tax_rates(), load_fees(), cfg)
        p, r = assignment_precision_recall_counted(pair_set(a2.predictions), truth_pairs)
        exact = exact_decomposition_counted(a2.predictions, truth_members)
        lines = [
            "# CP4 A2 rules-only (dev)",
            "",
            "A2 measured with the real tax config, the same candidate pools, and no uniqueness check.",
            "",
            "## A2 rules-only greedy",
            f"- assignment precision: {p.render()}",
            f"- assignment recall: {r.render()}",
            f"- exact decomposition: {exact.render()}",
            "- exception path: present",
            "- budget path: present",
            "",
        ]
    out.joinpath("baselines.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out.joinpath("baselines.md").read_text(encoding="utf-8"))
    return 0


def _append_tuning(path: Path, chosen: A1Config, log) -> None:
    sim_swept = ",".join(str(s) for s in SIM_GRID)
    tol_swept = ",".join(str(t) for t in TOL_GRID)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "| Held-out class | `TBD-CP2` |",
        "| Held-out class | `9 OVERPAYMENT` |",
    )
    text = text.replace(
        "| A1 | similarity threshold | `TBD-CP2` | `TBD-CP2` | maximises A1's **own** exact-decomposition rate on dev |",
        f"| A1 | similarity threshold | `{sim_swept}` | `{chosen.sim_threshold}` | maximises A1's **own** exact-decomposition rate on dev |",
    )
    text = text.replace(
        "| A1 | amount tolerance | `TBD-CP2` | `TBD-CP2` | as above |",
        f"| A1 | amount tolerance (paise) | `{tol_swept}` | `{chosen.amount_tol_paise}` | as above |",
    )
    marker_start = "<!-- A1-SWEEP-START -->"
    marker_end = "<!-- A1-SWEEP-END -->"
    sweep_lines = [
        marker_start,
        "",
        "A1 exact-decomposition on each (sim, amount_tol_paise) cell, as exact Fractions:",
        "",
        "| sim_threshold | amount_tol_paise | exact_decomposition |",
        "|---|---:|---|",
    ]
    for sim, tol, frac in log.rows:
        sweep_lines.append(f"| {sim} | {tol} | `{frac}` |")
    sweep_lines += ["", marker_end]
    sweep_block = "\n".join(sweep_lines)
    if marker_start in text and marker_end in text:
        pre, rest = text.split(marker_start, 1)
        _, post = rest.split(marker_end, 1)
        text = pre + sweep_block + post
    else:
        text = text.rstrip() + "\n\n" + sweep_block + "\n"
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
