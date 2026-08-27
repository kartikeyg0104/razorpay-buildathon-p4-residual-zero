"""CLI for the four-stage generator. ``python -m generator.cli``."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from random import Random

from residual_zero.config import load_fees, load_profile, load_tax_rates
from residual_zero.models import Kind
from residual_zero.money import format_rupees

from .corrupt import apply_corruptions, plan_for_profile
from .profiles import SPLIT_SEEDS
from .render import RenderedViews, render, write_split
from .scenario import build_scenario
from .truth import TruthRecord, build_truth


def generate_split(
    split: str,
    profile_path: Path,
    out_root: Path,
    seeds: tuple[int, ...] | None = None,
) -> None:
    profile = load_profile(profile_path)
    rates = load_tax_rates()
    fees = load_fees()
    if seeds is None:
        seeds = SPLIT_SEEDS[split]
    all_items = []
    all_credits = []
    all_records: list[TruthRecord] = []
    all_bank: list[dict[str, str]] = []
    all_ledger: list[dict[str, str]] = []
    all_settlement: list[dict[str, str]] = []
    for seed in seeds:
        scenario = build_scenario(profile, seed)
        truth = build_truth(scenario, rates, fees)
        views = render(truth)
        views, records = apply_corruptions(views, truth, plan_for_profile(profile), Random(seed + 23_000))
        all_items.extend(truth.items)
        all_credits.extend(truth.credits)
        all_records.extend(records)
        all_bank.extend(views.bank_rows)
        all_ledger.extend(views.ledger_rows)
        all_settlement.extend(views.settlement_rows)
    merged_views = RenderedViews(
        bank_rows=tuple(sorted(all_bank, key=lambda r: (r["value_date"], r["id"]))),
        ledger_rows=tuple(sorted(all_ledger, key=lambda r: (r["occurred_at"], r["id"]))),
        settlement_rows=tuple(sorted(all_settlement, key=lambda r: (r["credit_id"], r["item_id"]))),
    )
    manifest = write_split(
        split,
        merged_views,
        tuple(sorted(all_records, key=lambda r: r.bank_credit_id)),
        out_root,
        seeds=seeds,
        n_items=len(all_items),
        profile_name=profile.name,
    )
    class_counts = Counter(
        cls for rec in all_records for cls in rec.corruption_classes
    )
    print(
        f"wrote {split}: {manifest.n_credits} credits, {manifest.n_ledger_rows} ledger rows, "
        f"class counts {dict(sorted(class_counts.items()))}"
    )


def print_class(split: str, class_id: int, limit: int, out_root: Path) -> None:
    truth_path = out_root.joinpath(split, "truth.jsonl")
    ledger_path = out_root.joinpath(split, "rendered", "ledger.csv")
    if not truth_path.is_file():
        raise SystemExit(f"no {truth_path}; generate the split first")
    records = [
        TruthRecord.model_validate(json.loads(line))
        for line in truth_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching = [r for r in records if class_id in r.corruption_classes]
    if not matching:
        raise SystemExit(f"no class-{class_id} credits in {split}")
    items_by_credit: dict[str, list[dict[str, str]]] = defaultdict(list)
    import csv

    with ledger_path.open("r", encoding="utf-8", newline="") as handle:
        by_id = {row["id"]: row for row in csv.DictReader(handle)}
    print(f"class {class_id}: {len(matching)} credits, showing {min(limit, len(matching))}\n")
    for record in matching[:limit]:
        members = [by_id[mid] for mid in record.member_ids if mid in by_id]
        pays = [m for m in members if m["kind"] == Kind.PAYMENT.value]
        refs = [m for m in members if m["kind"] == Kind.REFUND.value]
        order_ids = sorted({p["order_id"] for p in pays if p["order_id"]})
        print(f"credit {record.bank_credit_id}")
        print(f"  total {format_rupees(record.total_paise)}  regime {record.regime.value}")
        print(f"  classes {record.corruption_classes}  m={record.subrupee_member_count}")
        print(f"  payments={len(pays)} refunds={len(refs)} members={len(members)}")
        print(f"  payment order_ids ({len(order_ids)}): {order_ids[:12]}")
        spanning = []
        for other in records:
            if other.bank_credit_id == record.bank_credit_id:
                continue
            other_orders = set()
            for mid in other.member_ids:
                row = by_id.get(mid)
                if row and row["kind"] == Kind.PAYMENT.value and row["order_id"]:
                    other_orders.add(row["order_id"])
            shared = set(order_ids) & other_orders
            if shared:
                spanning.append((other.bank_credit_id, sorted(shared)))
        if spanning:
            print(f"  orders that also settle in another credit: {spanning[:4]}")
        else:
            print("  no split orders on this credit")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generator.cli")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--profile", default="config/profiles/phase1.yaml")
    parser.add_argument("--out-root", default="data")
    parser.add_argument("--print-class", type=int, default=None)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args(argv)
    out_root = Path(args.out_root)
    if args.print_class is not None:
        print_class(args.split, args.print_class, args.limit, out_root)
        return 0
    generate_split(args.split, Path(args.profile), out_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
