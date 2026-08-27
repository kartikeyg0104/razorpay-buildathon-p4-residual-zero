"""D13 decision table: one fixture per class, precedence, fallback, purity."""

from __future__ import annotations

import inspect

from residual_zero.config import load_fees, load_solver_config, load_tax_rates
from residual_zero.exceptions.classify import Classification, ExceptionSignals, classify
from residual_zero.models import ExceptionClass, PoolScope, ResolutionTier, Uniqueness


def _sig(**kwargs) -> ExceptionSignals:
    base = dict(
        uniqueness=Uniqueness.NONE_FOUND,
        pool_scope=PoolScope.FULL,
        alternates=0,
        pool_size=8,
        pool_gross_paise=1_000_000,
        nearest_delta_paise=5_000,
        delta_matches_pool_member_ids=(),
        delta_matches_out_of_window_item_ids=(),
        delta_equals_twice_member_ids=(),
        duplicate_credit_ids=(),
        declared_line_deltas=(),
        unresolved_entity_count=0,
        cross_window_member_count=0,
        max_resolution_tier=ResolutionTier.EXACT_NORM,
    )
    base.update(kwargs)
    return ExceptionSignals(**base)


def test_one_case_per_class():
    rates, fees, cfg = load_tax_rates(), load_fees(), load_solver_config()
    cases = {
        ExceptionClass.BUDGET_EXCEEDED: _sig(uniqueness=Uniqueness.BUDGET_EXCEEDED),
        ExceptionClass.AMBIGUOUS_DECOMPOSITION: _sig(uniqueness=Uniqueness.AMBIGUOUS, alternates=2),
        ExceptionClass.ENTITY_UNRESOLVED: _sig(unresolved_entity_count=1),
        ExceptionClass.DUPLICATE_CREDIT: _sig(duplicate_credit_ids=("crd_other",)),
        ExceptionClass.RATE_MISMATCH: _sig(
            declared_line_deltas=(("itm_fee", 5_000),), nearest_delta_paise=5_000
        ),
        ExceptionClass.SIGN_REVERSAL: _sig(
            nearest_delta_paise=-10_000, delta_equals_twice_member_ids=("itm_pay",)
        ),
        ExceptionClass.CROSS_WINDOW_UNRESOLVED: _sig(
            nearest_delta_paise=12_345, delta_matches_out_of_window_item_ids=("itm_out",)
        ),
        ExceptionClass.MISSING_RECORD: _sig(
            nearest_delta_paise=12_345, delta_matches_pool_member_ids=("itm_one",)
        ),
        ExceptionClass.ROUNDING_RESIDUE: _sig(nearest_delta_paise=100),
        ExceptionClass.SUSPECTED_WITHHOLDING: _sig(nearest_delta_paise=1_000),
        ExceptionClass.UNITEMISED_FEE: _sig(nearest_delta_paise=20_000),
    }
    assert set(cases) == set(ExceptionClass)
    for expected, signals in cases.items():
        got = classify(signals, rates, fees, cfg)
        assert got.exception_class == expected, (expected, got)
        assert got.rule_matched is True


def test_precedence_when_two_rules_match():
    rates, fees, cfg = load_tax_rates(), load_fees(), load_solver_config()
    both_budget = classify(
        _sig(uniqueness=Uniqueness.AMBIGUOUS, pool_scope=PoolScope.REDUCED, alternates=2),
        rates, fees, cfg,
    )
    assert both_budget.exception_class == ExceptionClass.BUDGET_EXCEEDED

    equal_rates = rates.model_copy(
        update={"withholding": rates.withholding.model_copy(update={"bps": 200})}
    )
    tied = classify(_sig(nearest_delta_paise=20_000), equal_rates, fees, cfg)
    assert tied.exception_class == ExceptionClass.SUSPECTED_WITHHOLDING


def test_fallback_is_flagged_as_such():
    rates, fees, cfg = load_tax_rates(), load_fees(), load_solver_config()
    got = classify(_sig(nearest_delta_paise=123_456), rates, fees, cfg)
    assert got.exception_class == ExceptionClass.MISSING_RECORD
    assert got.rule_matched is False
    assert got.matched_rule == "fallback"


def test_classification_is_pure():
    sig = inspect.signature(classify)
    assert "client" not in sig.parameters
    assert "LLMClient" not in str(sig)
    names = set(ExceptionSignals.model_fields)
    assert "confidence" not in names
    assert "model" not in names
    assert Classification.__name__ == "Classification"
