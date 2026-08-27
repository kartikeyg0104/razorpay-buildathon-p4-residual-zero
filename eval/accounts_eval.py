"""F44: FP on legitimate data/dev first, then class-25 detection on a fixture plan."""

from __future__ import annotations

from pathlib import Path
from random import Random

from residual_zero.controller.accounts import detect_credit, false_positives
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import BankCredit

from eval.loader import load_split
from generator.corrupt import apply_corruptions, phase4_class25_plan
from generator.render import render
from generator.scenario import build_scenario
from generator.truth import build_truth
from residual_zero.config import load_fees, load_profile, load_tax_rates


def measure_fp(split: str = "dev") -> tuple[int, int, tuple[str, ...]]:
    items, credits = load_split(split)
    ledger = {it.id: it for it in items}
    root = SourceRoot(Path("data").joinpath(split, "rendered"))
    declared: dict[str, list[str]] = {}
    for row in load_settlement_report(root):
        declared.setdefault(row.credit_id, []).append(row.item_id)
    fired = false_positives(credits, declared, ledger)
    return len(fired), len(credits), fired


def measure_detection() -> tuple[int, int]:
    profile = load_profile(Path("config").joinpath("profiles").joinpath("phase1.yaml"))
    truth = build_truth(build_scenario(profile, 1), load_tax_rates(), load_fees())
    views, records = apply_corruptions(render(truth), truth, phase4_class25_plan(), Random(25_000))
    items = {i.id: i for i in truth.items}
    bank = {row["id"]: row for row in views.bank_rows}
    labelled = [r for r in records if 25 in r.corruption_classes]
    detected = 0
    for record in labelled:
        row = bank[record.bank_credit_id]
        credit = BankCredit(
            id=record.bank_credit_id,
            amount_paise=record.total_paise,
            value_date=truth.credits[0].value_date,
            account_id=row["account_id"],
            currency="INR",
            narration_raw=row["narration_raw"],
            narration_norm=row["narration_raw"].lower(),
        )
        if detect_credit(credit, record.member_ids, items):
            detected += 1
    return detected, len(labelled)


def measure() -> str:
    n_fp, n_credits, _fired = measure_fp("dev")
    n_hit, n_lab = measure_detection()
    lines = [
        "# F44 multi-account / class 25",
        "",
        f"- legitimate_batch: data/dev n={n_credits} credits, two accounts",
        f"- false_positives: {n_fp}/{n_credits}",
        f"- class25_detection: {n_hit}/{n_lab} (phase4_class25_plan on seed 1; data/dev not regenerated)",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    out = Path("artifacts").joinpath("p4")
    out.mkdir(parents=True, exist_ok=True)
    text = measure()
    out.joinpath("accounts.md").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
