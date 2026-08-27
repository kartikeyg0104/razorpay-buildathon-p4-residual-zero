"""Deterministic exception decision table. First match wins. The model never assigns the class."""

from __future__ import annotations

from residual_zero.config import FeeSchedule, SolverConfig, TaxRates
from residual_zero.models import ExceptionClass, PoolScope, ResolutionTier, Uniqueness
from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(frozen=True, extra="forbid")


class ExceptionSignals(BaseModel):
    """Every input to classification, all observable. No model output appears here."""

    model_config = _STRICT

    uniqueness: Uniqueness
    pool_scope: PoolScope
    alternates: int = Field(ge=0)
    pool_size: int = Field(ge=0)
    pool_gross_paise: int = Field(ge=0)
    nearest_delta_paise: int | None
    delta_matches_pool_member_ids: tuple[str, ...]
    delta_matches_out_of_window_item_ids: tuple[str, ...]
    delta_equals_twice_member_ids: tuple[str, ...]
    duplicate_credit_ids: tuple[str, ...]
    declared_line_deltas: tuple[tuple[str, int], ...]
    unresolved_entity_count: int = Field(ge=0)
    cross_window_member_count: int = Field(ge=0)
    max_resolution_tier: ResolutionTier


class Classification(BaseModel):
    model_config = _STRICT

    exception_class: ExceptionClass
    matched_rule: str
    rule_matched: bool


def _rate_error(delta: int, gross: int, rate_bps: int) -> int:
    """Integer |delta/gross - rate_bps/10000| * gross * 10000, i.e. |delta*10000 - rate_bps*gross|."""
    return abs(delta * 10000 - rate_bps * gross)


def _matches_rate(delta: int, gross: int, rate_bps: int, tolerance_bps: int, min_delta: int, ceiling: int) -> bool:
    if gross <= 0:
        return False
    ad = abs(delta)
    if ad <= ceiling:
        return False
    if ad < min_delta:
        return False
    return _rate_error(delta, gross, rate_bps) <= tolerance_bps * gross


def classify(
    signals: ExceptionSignals,
    rates: TaxRates,
    fees: FeeSchedule,
    cfg: SolverConfig,
) -> Classification:
    """Deterministic decision table, first match wins, precedence exactly as D13 lists it."""
    if signals.uniqueness == Uniqueness.BUDGET_EXCEEDED or signals.pool_scope == PoolScope.REDUCED:
        return Classification(
            exception_class=ExceptionClass.BUDGET_EXCEEDED,
            matched_rule="budget_or_reduced",
            rule_matched=True,
        )
    if signals.uniqueness == Uniqueness.AMBIGUOUS:
        return Classification(
            exception_class=ExceptionClass.AMBIGUOUS_DECOMPOSITION,
            matched_rule="uniqueness_ambiguous",
            rule_matched=True,
        )
    if signals.unresolved_entity_count > 0:
        return Classification(
            exception_class=ExceptionClass.ENTITY_UNRESOLVED,
            matched_rule="unresolved_entity",
            rule_matched=True,
        )
    if signals.duplicate_credit_ids:
        return Classification(
            exception_class=ExceptionClass.DUPLICATE_CREDIT,
            matched_rule="duplicate_credit",
            rule_matched=True,
        )

    delta = signals.nearest_delta_paise
    if delta is None:
        return Classification(
            exception_class=ExceptionClass.MISSING_RECORD,
            matched_rule="fallback_no_delta",
            rule_matched=False,
        )

    if signals.declared_line_deltas:
        explained = 0
        for _item_id, line_delta in signals.declared_line_deltas:
            explained += line_delta
        if explained == delta:
            return Classification(
                exception_class=ExceptionClass.RATE_MISMATCH,
                matched_rule="declared_line_deltas_explain_residual",
                rule_matched=True,
            )

    if len(signals.delta_equals_twice_member_ids) == 1:
        return Classification(
            exception_class=ExceptionClass.SIGN_REVERSAL,
            matched_rule="delta_equals_minus_twice_member",
            rule_matched=True,
        )

    if signals.delta_matches_out_of_window_item_ids:
        return Classification(
            exception_class=ExceptionClass.CROSS_WINDOW_UNRESOLVED,
            matched_rule="delta_matches_out_of_window",
            rule_matched=True,
        )

    if len(signals.delta_matches_pool_member_ids) == 1:
        return Classification(
            exception_class=ExceptionClass.MISSING_RECORD,
            matched_rule="delta_equals_one_pool_member",
            rule_matched=True,
        )

    ceiling = cfg.diagnosis.rounding_delta_ceiling_paise
    if abs(delta) <= ceiling:
        return Classification(
            exception_class=ExceptionClass.ROUNDING_RESIDUE,
            matched_rule="abs_delta_within_rounding_ceiling",
            rule_matched=True,
        )

    tol = cfg.diagnosis.rate_match_tolerance_bps
    min_d = cfg.diagnosis.min_rate_delta_paise
    gross = signals.pool_gross_paise
    wh_bps = rates.withholding.bps
    wh_ok = _matches_rate(delta, gross, wh_bps, tol, min_d, ceiling)
    fee_hits: list[tuple[int, int]] = []
    for _instrument, entry in fees.per_instrument_bps.items():
        if _matches_rate(delta, gross, entry.bps, tol, min_d, ceiling):
            fee_hits.append((_rate_error(delta, gross, entry.bps), entry.bps))
    fee_ok = bool(fee_hits)
    if wh_ok and fee_ok:
        wh_err = _rate_error(delta, gross, wh_bps)
        fee_err = min(err for err, _bps in fee_hits)
        if fee_err < wh_err:
            return Classification(
                exception_class=ExceptionClass.UNITEMISED_FEE,
                matched_rule="rate_shape_fee_smaller_relative_error",
                rule_matched=True,
            )
        return Classification(
            exception_class=ExceptionClass.SUSPECTED_WITHHOLDING,
            matched_rule="rate_shape_withholding_tiebreak",
            rule_matched=True,
        )
    if wh_ok:
        return Classification(
            exception_class=ExceptionClass.SUSPECTED_WITHHOLDING,
            matched_rule="rate_shape_withholding",
            rule_matched=True,
        )
    if fee_ok:
        return Classification(
            exception_class=ExceptionClass.UNITEMISED_FEE,
            matched_rule="rate_shape_fee",
            rule_matched=True,
        )
    return Classification(
        exception_class=ExceptionClass.MISSING_RECORD,
        matched_rule="fallback",
        rule_matched=False,
    )
