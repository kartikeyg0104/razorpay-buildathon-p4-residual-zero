"""F36: median symmetric-difference size vs median decomposition size on the live corpus."""

from __future__ import annotations

from pathlib import Path

from residual_zero.candidates import build_pool
from residual_zero.config import load_fees, load_profile, load_solver_config, load_tax_rates
from residual_zero.features import load_features
from residual_zero.models import Uniqueness
from residual_zero.solver import collect_enumerated, disambiguate, solve_search
from residual_zero.solver.alt_diff import median_int, pair_stats
from residual_zero.solver.tolerance import apply_derived_epsilon

from eval.loader import load_split


def measure(split: str = "dev") -> str:
    flags = load_features()
    items, credits = load_split(split)
    ledger = {it.id: it for it in items}
    cfg = apply_derived_epsilon(load_solver_config(), flags)
    rates, fees = load_tax_rates(), load_fees()
    profile_path = Path("config").joinpath("profiles").joinpath(
        "phase1_test.yaml" if split == "test" else "phase1.yaml"
    )
    reserve_bps = load_profile(profile_path).reserve_bps
    all_diffs: list[int] = []
    all_sizes: list[int] = []
    n_ambiguous = 0
    n_capped = 0
    n_pairs = 0
    for credit in credits:
        pool = build_pool(credit, items, cfg)
        solve = solve_search(pool, credit.amount_paise, cfg)
        if solve.uniqueness != Uniqueness.AMBIGUOUS:
            continue
        n_ambiguous += 1
        enumerated, capped, budgeted = collect_enumerated(
            pool, credit.amount_paise, cfg, flags.f31_enumerate_cap
        )
        if budgeted or capped or not enumerated:
            n_capped += 1
            continue
        d = disambiguate(
            pool.item_ids, enumerated, ledger, rates, fees, reserve_bps,
            frozenset(), enumeration_capped=capped,
        )
        diffs, sizes = pair_stats(pool.item_ids, enumerated, d.feasible_indices)
        all_diffs.extend(diffs)
        all_sizes.extend(sizes)
        n_pairs += len(diffs)
    med_diff = median_int(all_diffs)
    med_size = median_int(all_sizes)
    def _cell(v: int | None) -> str:
        return "—" if v is None else str(v)
    lines = [
        "# F36 alternate-decomposition diff",
        "",
        f"- n_credits: {len(credits)}",
        f"- n_ambiguous: {n_ambiguous}",
        f"- n_capped_or_budgeted: {n_capped}",
        f"- n_uncapped_pairs: {n_pairs}",
        f"- median_symmetric_difference_size: {_cell(med_diff)}",
        f"- median_decomposition_size: {_cell(med_size)}",
        "",
        "Cap-hit credits contribute no pair (NN-18). Fixture in tests/test_alt_diff.py "
        "(three feasible sets, fully enumerated): median symmetric-difference size 3, "
        "median decomposition size 1.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    out = Path("artifacts").joinpath("p4")
    out.mkdir(parents=True, exist_ok=True)
    text = measure("dev")
    out.joinpath("alt_diff.md").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
