"""Generator stage 1–4 properties. These tests are the cheap insurance against a 1:1 data model."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from random import Random

from residual_zero.config import load_fees, load_profile, load_tax_rates
from residual_zero.models import Kind
from residual_zero.money import to_rupee_units

from generator.corrupt import CorruptionClass, apply_corruptions, phase1_dev_plan
from generator.render import render, write_split
from generator.scenario import build_scenario
from generator.truth import build_truth


def _one_seed(seed: int = 1):
    profile = load_profile(Path("config/profiles/phase1.yaml"))
    scenario = build_scenario(profile, seed)
    truth = build_truth(scenario, load_tax_rates(), load_fees())
    return profile, scenario, truth


def test_truth_sums_exactly_at_paise():
    """For every credit, the signed sum of its truth members equals the credit amount exactly."""
    _, _, truth = _one_seed()
    items = {i.id: i for i in truth.items}
    credits = {c.id: c for c in truth.credits}
    assert truth.records, "no records; the generator produced nothing"
    for record in truth.records:
        total = sum(items[mid].amount_paise for mid in record.member_ids)
        assert total == credits[record.bank_credit_id].amount_paise
        assert total == record.total_paise


def test_corruption_never_mutates_truth():
    """member_ids and total_paise are identical with class-23 corruption on and off."""
    _, _, truth = _one_seed()
    views = render(truth)
    plan_on = phase1_dev_plan()
    plan_off = plan_on._replace(apply_class_23=False, mutation_classes=())
    _, rec_on = apply_corruptions(views, truth, plan_on, Random(23))
    _, rec_off = apply_corruptions(views, truth, plan_off, Random(23))
    on = {r.bank_credit_id: (r.member_ids, r.total_paise) for r in rec_on}
    off = {r.bank_credit_id: (r.member_ids, r.total_paise) for r in rec_off}
    assert on == off


def test_two_generations_byte_identical(tmp_path: Path):
    """Two runs at one seed produce identical rendered views and truth."""
    profile = load_profile(Path("config/profiles/phase1.yaml"))
    rates, fees = load_tax_rates(), load_fees()

    def dump(root: Path) -> tuple[str, str, str, str]:
        scenario = build_scenario(profile, 1)
        truth = build_truth(scenario, rates, fees)
        views, records = apply_corruptions(render(truth), truth, phase1_dev_plan(), Random(1 + 23_000))
        write_split("dev", views, records, root, seeds=(1,), n_items=len(truth.items), profile_name=profile.name)
        rendered = root / "dev" / "rendered"
        return (
            (root / "dev" / "truth.jsonl").read_text(encoding="utf-8"),
            (rendered / "bank.csv").read_text(encoding="utf-8"),
            (rendered / "ledger.csv").read_text(encoding="utf-8"),
            (rendered / "settlement.csv").read_text(encoding="utf-8"),
        )

    a = dump(tmp_path / "a")
    b = dump(tmp_path / "b")
    assert a == b


def test_subrupee_member_count_within_design_bound():
    """Every credit's m is <= profile.subrupee_member_max. This is the D6 guard."""
    profile, _, truth = _one_seed()
    assert truth.records
    for record in truth.records:
        assert record.subrupee_member_count <= profile.subrupee_member_max


def test_class4_is_genuinely_n_to_m():
    """Every class-4 credit has >= 2 payments AND >= 1 refund, and some class-4 order spans credits."""
    _, _, truth = _one_seed()
    items = {i.id: i for i in truth.items}
    class4 = [r for r in truth.records if 4 in r.corruption_classes]
    assert class4, "generator produced no MIXED_N_M credits"
    spanning = False
    order_to_credits: dict[str, set[str]] = defaultdict(set)
    for record in truth.records:
        for mid in record.member_ids:
            item = items[mid]
            if item.kind == Kind.PAYMENT and item.order_id:
                order_to_credits[item.order_id].add(record.bank_credit_id)
    for record in class4:
        pays = [items[m] for m in record.member_ids if items[m].kind == Kind.PAYMENT]
        refs = [items[m] for m in record.member_ids if items[m].kind == Kind.REFUND]
        assert len(pays) >= 2, f"{record.bank_credit_id} class 4 has {len(pays)} payments"
        assert len(refs) >= 1, f"{record.bank_credit_id} class 4 has {len(refs)} refunds"
        for payment in pays:
            if payment.order_id and len(order_to_credits[payment.order_id]) >= 2:
                spanning = True
    assert spanning, "no class-4 order settles across two credits"


def test_class23_two_distinct_subsets_within_tolerance():
    """For every class-23 credit, two subsets exist with equal rupee sums and |Δ| >= 3."""
    _, _, truth = _one_seed()
    views, records = apply_corruptions(render(truth), truth, phase1_dev_plan(), Random(1 + 23_000))
    items = {i.id: i for i in truth.items}
    ledger_by_id = {row["id"]: row for row in views.ledger_rows}
    class23 = [r for r in records if int(CorruptionClass.AMBIGUOUS_BY_CONSTRUCTION) in r.corruption_classes]
    assert class23, "no class-23 credits"
    from residual_zero.normalise import parse_rupee_display

    for record in class23:
        decoys = [
            row for row in views.ledger_rows
            if row["id"].startswith(f"itm_c23_{record.bank_credit_id}_")
        ]
        assert len(decoys) == 2, f"{record.bank_credit_id} expected 2 decoys, got {len(decoys)}"
        members = [items[mid] for mid in record.member_ids if items[mid].kind == Kind.PAYMENT]
        members.sort(key=lambda p: p.id)
        a = members[:2]
        v_a = sum(to_rupee_units(p.amount_paise) for p in a)
        v_b = sum(to_rupee_units(parse_rupee_display(d["amount"])) for d in decoys)
        assert v_a == v_b
        a_ids = {p.id for p in a}
        b_ids = {d["id"] for d in decoys}
        assert a_ids.isdisjoint(b_ids)
        assert len(a_ids | b_ids) >= 3
        for decoy in decoys:
            assert decoy["id"] not in record.member_ids
            assert decoy["order_id"] not in {p.order_id for p in a}


def test_forbidden_classes_absent():
    """Classes 25/26 exist as enum members from Phase 4 but are not on the Phase 1 plan."""
    assert hasattr(CorruptionClass, "FEE_RATE_DRIFT")
    assert hasattr(CorruptionClass, "CROSS_ACCOUNT_MISPOSTING")
    assert hasattr(CorruptionClass, "FX_ROUNDING_RESIDUE")
    assert 24 in set(CorruptionClass)
    assert 25 in set(CorruptionClass)
    assert 26 in set(CorruptionClass)
    _, _, truth = _one_seed()
    _, records = apply_corruptions(render(truth), truth, phase1_dev_plan(), Random(7))
    seen = {c for r in records for c in r.corruption_classes}
    assert 24 not in seen
    assert not ({25, 26} & seen)
