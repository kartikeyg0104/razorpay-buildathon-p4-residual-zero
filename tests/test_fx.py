"""F29: class 26 is a conversion-rounding residue; truth members are untouched."""

from __future__ import annotations

from random import Random

from residual_zero.exceptions.classify import ExceptionSignals, classify
from residual_zero.config import load_fees, load_solver_config, load_tax_rates
from residual_zero.models import ExceptionClass, PoolScope, ResolutionTier, Uniqueness
from residual_zero.normalise import parse_rupee_display

from generator.corrupt import CorruptionClass, apply_corruptions, phase4_fx_plan
from generator.render import render
from tests.test_generator import _one_seed


def test_class26_mutates_rendered_amount_only():
    _, _, truth = _one_seed()
    original = {r.bank_credit_id: (r.member_ids, r.total_paise) for r in truth.records}
    views, records = apply_corruptions(render(truth), truth, phase4_fx_plan(), Random(26_000))
    labelled = [r for r in records if int(CorruptionClass.FX_ROUNDING_RESIDUE) in r.corruption_classes]
    assert labelled, "phase4_fx_plan produced no class-26 credits"
    bank = {row["id"]: row for row in views.bank_rows}
    for record in labelled:
        assert (record.member_ids, record.total_paise) == original[record.bank_credit_id]
        rendered = parse_rupee_display(bank[record.bank_credit_id]["amount"])
        delta = rendered - record.total_paise
        assert 1 <= delta <= 99


def test_class26_residue_maps_to_rounding_exception():
    rates, fees, cfg = load_tax_rates(), load_fees(), load_solver_config()
    signals = ExceptionSignals(
        uniqueness=Uniqueness.NONE_FOUND,
        pool_scope=PoolScope.FULL,
        alternates=0,
        pool_size=8,
        pool_gross_paise=1_000_000,
        nearest_delta_paise=47,
        delta_matches_pool_member_ids=(),
        delta_matches_out_of_window_item_ids=(),
        delta_equals_twice_member_ids=(),
        duplicate_credit_ids=(),
        declared_line_deltas=(),
        unresolved_entity_count=0,
        cross_window_member_count=0,
        max_resolution_tier=ResolutionTier.EXACT_NORM,
    )
    got = classify(signals, rates, fees, cfg)
    assert got.exception_class == ExceptionClass.ROUNDING_RESIDUE
