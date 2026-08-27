"""Model writes slotted prose; this function substitutes pre-rendered figures. NN-3 holds."""

from __future__ import annotations

from typing import Mapping

from residual_zero.exceptions.classify import Classification, ExceptionSignals
from residual_zero.models import ExceptionClass
from residual_zero.semantic.llm import LLMClient, OfflineCacheMiss
from residual_zero.semantic.schema import MONEY_PATTERN, NarrationRequest, AmountLeakError, assert_no_amounts

TEMPLATES: dict[ExceptionClass, str] = {
    ExceptionClass.AMBIGUOUS_DECOMPOSITION: (
        "More than one subset reaches this credit within tolerance ({ALTERNATES} alternates). Flagged."
    ),
    ExceptionClass.MISSING_RECORD: (
        "The residual {DELTA} is unexplained by a rate shape or a windowed member. Information is absent from the inputs."
    ),
    ExceptionClass.DUPLICATE_CREDIT: (
        "Another credit shares this account and amount with a value-date within one day ({DUPLICATES})."
    ),
    ExceptionClass.SUSPECTED_WITHHOLDING: (
        "The residual {DELTA} is a clean percentage of pool gross {GROSS} near a configured withholding rate ({PCT})."
    ),
    ExceptionClass.UNITEMISED_FEE: (
        "The residual {DELTA} matches a configured per-instrument fee rate on pool gross {GROSS} ({PCT})."
    ),
    ExceptionClass.ROUNDING_RESIDUE: (
        "The residual {DELTA} sits inside the rounding ceiling. No rate-shaped diagnosis applies."
    ),
    ExceptionClass.CROSS_WINDOW_UNRESOLVED: (
        "An item outside the candidate window equals the residual {DELTA}. The record is not missing; the window excluded it."
    ),
    ExceptionClass.SIGN_REVERSAL: (
        "The residual equals minus twice one pool member. A debit posted as a credit moves the sum by twice its amount."
    ),
    ExceptionClass.ENTITY_UNRESOLVED: (
        "A counterparty could not be resolved against the closed registry. The pool itself may be wrong."
    ),
    ExceptionClass.BUDGET_EXCEEDED: (
        "Search did not finish: the pool was reduced or the axis/node cap fired. No other diagnosis is honest."
    ),
    ExceptionClass.RATE_MISMATCH: (
        "Declared line deltas fully explain the residual {DELTA}. A configured rate does not match the posted line."
    ),
}


def _fill(template: str, slot_values: Mapping[str, str]) -> str:
    prose = template
    for name, value in slot_values.items():
        prose = prose.replace("{" + name + "}", value)
    return prose


def _qualitative_facts(signals: ExceptionSignals) -> tuple[str, ...]:
    facts: list[str] = [
        f"uniqueness is {signals.uniqueness.value}",
        f"pool scope is {signals.pool_scope.value}",
    ]
    if signals.nearest_delta_paise is None:
        facts.append("delta is absent")
    elif signals.nearest_delta_paise < 0:
        facts.append("delta is negative")
    elif signals.nearest_delta_paise > 0:
        facts.append("delta is positive")
    else:
        facts.append("delta is zero")
    if signals.unresolved_entity_count > 0:
        facts.append("an entity is unresolved")
    return tuple(facts)


def narrate(
    classification: Classification,
    signals: ExceptionSignals,
    slot_values: Mapping[str, str],
    client: LLMClient | None,
) -> str:
    """Model writes prose containing slot names; this function substitutes the pre-rendered figures.

    A money-shaped literal in the model's output rejects the response and falls back to the
    deterministic template — never a retry loop (§5.12, §0.5).
    """
    template = TEMPLATES[classification.exception_class]
    fallback = _fill(template, slot_values)
    if client is None:
        return fallback
    request = NarrationRequest(
        exception_class=classification.exception_class,
        facts=_qualitative_facts(signals),
        slots=tuple(slot_values.keys()),
    )
    try:
        response = client.narrate(request)
    except OfflineCacheMiss:
        return fallback
    if response is None:
        return fallback
    try:
        assert_no_amounts(response.prose.encode("utf-8"))
    except AmountLeakError:
        return fallback
    if MONEY_PATTERN.search(response.prose):
        return fallback
    allowed = set(slot_values)
    filled = response.prose
    for name, value in slot_values.items():
        filled = filled.replace("{" + name + "}", value)
    leftover = [name for name in allowed if "{" + name + "}" in filled]
    if leftover:
        return fallback
    return filled
