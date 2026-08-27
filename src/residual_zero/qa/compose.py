"""Model writes slotted prose; substitution is total. A money literal rejects the response."""

from __future__ import annotations

from typing import Sequence

from residual_zero.models import ExceptionClass
from residual_zero.qa.format import deterministic_answer, render_slots
from residual_zero.qa.retrieve import RetrievedRows
from residual_zero.semantic.llm import LLMClient, OfflineCacheMiss
from residual_zero.semantic.schema import AmountLeakError, NarrationRequest, assert_no_amounts


def compose(
    question: str,
    rows: RetrievedRows,
    slot_names: Sequence[str],
    client: LLMClient | None,
) -> str:
    slots = render_slots(rows)
    fallback = deterministic_answer(rows, slots)
    if client is None:
        return fallback
    request = NarrationRequest(
        exception_class=ExceptionClass.MISSING_RECORD,
        facts=(question, rows.intent.value),
        slots=tuple(slot_names),
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
    filled = response.prose
    for name, value in slots.items():
        filled = filled.replace("{" + name + "}", value)
    if "{" in filled:
        return fallback
    return filled
