"""Shared arm result type."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.models import Disposition

_STRICT = ConfigDict(frozen=True, extra="forbid")


class ArmResult(BaseModel):
    model_config = _STRICT

    arm: str
    predictions: dict[str, tuple[str, ...]]
    dispositions: dict[str, Disposition]
    has_exception_path: bool
    has_budget_path: bool
