"""F52 per-credit decision trace. A raise still leaves a trace."""

from __future__ import annotations

from residual_zero.models import Disposition
from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(frozen=True, extra="forbid")


class Gate(BaseModel):
    model_config = _STRICT

    name: str
    passed: bool
    detail: str


class DecisionTrace(BaseModel):
    model_config = _STRICT

    bank_credit_id: str
    gates: tuple[Gate, ...]
    disposition: Disposition | None = None
    error: str | None = None


class TraceBuilder:
    def __init__(self, bank_credit_id: str) -> None:
        self.bank_credit_id = bank_credit_id
        self._gates: list[Gate] = []
        self.error: str | None = None
        self.disposition: Disposition | None = None

    def gate(self, name: str, passed: bool, detail: str) -> None:
        self._gates.append(Gate(name=name, passed=passed, detail=detail))

    def finish(self, disposition: Disposition, error: str | None = None) -> DecisionTrace:
        self.disposition = disposition
        if error is not None:
            self.error = error
        if self.error and self.disposition is None:
            self.disposition = Disposition.FLAGGED
        disp = self.disposition if self.disposition is not None else Disposition.FLAGGED
        return DecisionTrace(
            bank_credit_id=self.bank_credit_id,
            gates=tuple(self._gates),
            disposition=disp,
            error=self.error,
        )
