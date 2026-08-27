"""NN-3: the model never sees or emits amounts."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

from residual_zero.exceptions.classify import Classification, ExceptionSignals
from residual_zero.exceptions.narrate import TEMPLATES, narrate
from residual_zero.models import ExceptionClass, PoolScope, ResolutionTier, Uniqueness
from residual_zero.semantic.llm import StubLLMClient
from residual_zero.semantic.schema import (
    AmountLeakError,
    EntityResolutionRequest,
    MONEY_PATTERN,
    NarrationRequest,
    NarrationResponse,
    assert_no_amounts,
)


def _walk_types(model: type[BaseModel]) -> list[type]:
    found: list[type] = []
    for name, field in model.model_fields.items():
        ann = field.annotation
        found.append(ann)
        args = getattr(ann, "__args__", ())
        found.extend(args)
    return found


def test_request_types_have_no_numeric_fields():
    numeric = {int, float, Decimal}
    for model in (EntityResolutionRequest, NarrationRequest):
        for typ in _walk_types(model):
            origin = getattr(typ, "__origin__", typ)
            if origin in numeric or typ in numeric:
                raise AssertionError(f"{model.__name__} has numeric field type {typ}")


def test_money_shaped_payload_raises():
    with pytest.raises(AmountLeakError):
        assert_no_amounts(b"settlement of Rs. 12.50 posted")
    with pytest.raises(AmountLeakError):
        assert_no_amounts("INR 100.00".encode("utf-8"))


def test_utr_is_not_mistaken_for_an_amount():
    assert_no_amounts(b"UTR HDFC12345678901 posted against invoice INV9001")


def test_no_cached_prompt_contains_an_amount():
    root = Path("data").joinpath("cache").joinpath("llm")
    if not root.exists():
        return
    leaks = []
    for path in root.rglob("*.json"):
        raw = path.read_bytes()
        if MONEY_PATTERN.search(raw.decode("utf-8", errors="replace")):
            leaks.append(str(path))
    assert not leaks, f"cached prompts contain money-shaped literals: {leaks}"


def test_narration_response_with_a_literal_is_rejected():
    stub = StubLLMClient()
    stub.next_narrate = NarrationResponse(prose="The residual is Rs. 12.50 which looks like withholding.")
    classification = Classification(
        exception_class=ExceptionClass.SUSPECTED_WITHHOLDING,
        matched_rule="rate_shape_withholding",
        rule_matched=True,
    )
    signals = ExceptionSignals(
        uniqueness=Uniqueness.NONE_FOUND,
        pool_scope=PoolScope.FULL,
        alternates=0,
        pool_size=4,
        pool_gross_paise=1_000_000,
        nearest_delta_paise=1000,
        delta_matches_pool_member_ids=(),
        delta_matches_out_of_window_item_ids=(),
        delta_equals_twice_member_ids=(),
        duplicate_credit_ids=(),
        declared_line_deltas=(),
        unresolved_entity_count=0,
        cross_window_member_count=0,
        max_resolution_tier=ResolutionTier.EXACT_NORM,
    )
    out = narrate(classification, signals, {"DELTA": "10.00", "GROSS": "10,000.00", "PCT": "10 bps"}, stub)
    assert "Rs. 12.50" not in out
    assert out == TEMPLATES[ExceptionClass.SUSPECTED_WITHHOLDING].replace("{DELTA}", "10.00").replace(
        "{GROSS}", "10,000.00"
    ).replace("{PCT}", "10 bps")
