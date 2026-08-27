"""Request/response types for the model. The NN-3 mechanism is the type: no numeric fields."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from residual_zero.models import ExceptionClass

_STRICT = ConfigDict(frozen=True, extra="forbid")

MONEY_PATTERN = re.compile(r"\d[\d,]*\.\d{2}|(?:₹|Rs\.?|INR)\s*\d")


class AmountLeakError(RuntimeError):
    """Raised before egress when a payload contains a money-shaped literal. NN-3 as a mechanism."""


def assert_no_amounts(payload_bytes: bytes) -> None:
    """Scan an outbound payload for money-shaped literals and raise AmountLeakError on a hit.

    Deliberately does not reject bare digit runs: UTRs and invoice numbers are legitimate.
    """
    text = payload_bytes.decode("utf-8", errors="replace")
    if MONEY_PATTERN.search(text):
        raise AmountLeakError("outbound payload contains a money-shaped literal (NN-3)")


class CandidateEntity(BaseModel):
    model_config = _STRICT

    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)


class EntityResolutionRequest(BaseModel):
    model_config = _STRICT

    narration_norm: str
    counterparty_text: str
    candidates: tuple[CandidateEntity, ...]


class EntityResolutionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selected_id: str | None
    reason: str

    @model_validator(mode="after")
    def _selected_is_closed_set_when_bound(self) -> "EntityResolutionResponse":
        # Closed-set check is applied by bind_selection against the request. The type itself
        # carries no numeric field and forbids extras (NN-3).
        return self


class NarrationRequest(BaseModel):
    model_config = _STRICT

    exception_class: ExceptionClass
    facts: tuple[str, ...]
    slots: tuple[str, ...]


class NarrationResponse(BaseModel):
    model_config = _STRICT

    prose: str


def bind_selection(
    request: EntityResolutionRequest, response: EntityResolutionResponse
) -> EntityResolutionResponse | None:
    """None if selected_id is not in the request's candidate ids. Abstention (None id) is valid."""
    if response.selected_id is None:
        return response
    allowed = {c.id for c in request.candidates}
    if response.selected_id not in allowed:
        return None
    return response
