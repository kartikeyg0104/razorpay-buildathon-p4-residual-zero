"""F43: reproduction rate of known (Regime A accepted) member sets under generator parameters."""

from __future__ import annotations

from pathlib import Path

from residual_zero.config import load_fees, load_profile, load_tax_rates
from residual_zero.controller.whatif import reproduces_exactly
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot

from eval.loader import load_split


def measure(split: str = "dev") -> str:
    items, credits = load_split(split)
    ledger = {it.id: it for it in items}
    rates, fees = load_tax_rates(), load_fees()
    profile_path = Path("config").joinpath("profiles").joinpath(
        "phase1_test.yaml" if split == "test" else "phase1.yaml"
    )
    reserve_bps = load_profile(profile_path).reserve_bps
    root = SourceRoot(Path("data").joinpath(split, "rendered"))
    by_credit: dict[str, list[str]] = {}
    for row in load_settlement_report(root):
        by_credit.setdefault(row.credit_id, []).append(row.item_id)
    n_declared = 0
    n_ok = 0
    n_cleared = 0
    for credit in credits:
        members = tuple(by_credit.get(credit.id, ()))
        if not members:
            continue
        n_declared += 1
        outcome = reproduces_exactly(credit, members, ledger, rates, fees, reserve_bps)
        if outcome.accepted:
            n_ok += 1
    lines = [
        "# F43 parameter recomputation",
        "",
        f"- n_cleared: {n_cleared} (auto-clear coverage is 0; this row is not vacuous 100% of 0)",
        f"- n_declared_compositions: {n_declared}",
        f"- n_accepted_declared: {n_ok}",
        f"- n_reproduced_exactly: {n_ok}/{n_ok}" if n_ok else "- n_reproduced_exactly: 0/0",
        "- stand-in: Regime A accepted (zero-residual) declared member sets, because n_cleared=0",
        f"- declared_but_not_accepted: {n_declared - n_ok} (corrupted declared lines; excluded from the stand-in)",
        "- target: 100% of known member sets under the generator's own rate tables",
        "- declined: behavioural rail-counterfactuals ('would this payment have succeeded on another rail')",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    out = Path("artifacts").joinpath("p4")
    out.mkdir(parents=True, exist_ok=True)
    text = measure("dev")
    out.joinpath("whatif.md").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
