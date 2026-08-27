"""The canonical data model. Everything normalises into this before any logic touches it.

All money is integer paise (NN-1, ADR-5). Amounts are **signed** — inflows positive, deductions
negative — which is what lets one solver handle both uniformly; magnitudes plus a direction flag
are explicitly rejected (spec §5.3).

One decision here is worth reading the docstring for: sign correctness is a **derived check**,
not a validator. See :func:`expected_sign`.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum, IntEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .tz import ensure_utc

_STRICT = ConfigDict(frozen=True, extra="forbid")


class Kind(str, Enum):
    """The eleven ledger item kinds of spec §5.3."""

    PAYMENT = "PAYMENT"
    REFUND = "REFUND"
    CHARGEBACK = "CHARGEBACK"
    REPRESENTMENT = "REPRESENTMENT"
    FEE = "FEE"
    TAX_GST = "TAX_GST"
    TAX_WITHHOLDING = "TAX_WITHHOLDING"
    RESERVE_HOLD = "RESERVE_HOLD"
    RESERVE_RELEASE = "RESERVE_RELEASE"
    ADJUSTMENT = "ADJUSTMENT"
    BANK_CHARGE = "BANK_CHARGE"


class Instrument(str, Enum):
    CARD = "CARD"
    UPI = "UPI"
    NETBANKING = "NETBANKING"
    WALLET = "WALLET"
    EMI = "EMI"


class Source(str, Enum):
    SETTLEMENT_REPORT = "SETTLEMENT_REPORT"
    INTERNAL_LEDGER = "INTERNAL_LEDGER"
    BANK_STATEMENT = "BANK_STATEMENT"
    API = "API"


class Regime(str, Enum):
    A_DECLARED = "A_DECLARED"
    B_SEARCHED = "B_SEARCHED"


class Uniqueness(str, Enum):
    """Solver outcome. ``UNIQUE`` is the only value eligible to auto-clear (spec §5.6)."""

    UNIQUE = "UNIQUE"
    AMBIGUOUS = "AMBIGUOUS"
    NONE_FOUND = "NONE_FOUND"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class PoolScope(str, Enum):
    """Whether the search saw the whole candidate pool.

    A ``UNIQUE`` found on a ``REDUCED`` pool was never shown to be unique over the full pool, so
    it does not auto-clear (PLAN-P1 §0.3).
    """

    FULL = "FULL"
    REDUCED = "REDUCED"


class Disposition(str, Enum):
    """The three terminal outcomes. There is no fourth and no silent pass (spec §5.12)."""

    CLEARED = "CLEARED"
    FLAGGED = "FLAGGED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class ExceptionClass(str, Enum):
    """The eleven exception classes of spec §5.10. Closed set, assigned by rule, never by a model."""

    AMBIGUOUS_DECOMPOSITION = "AMBIGUOUS_DECOMPOSITION"
    MISSING_RECORD = "MISSING_RECORD"
    DUPLICATE_CREDIT = "DUPLICATE_CREDIT"
    SUSPECTED_WITHHOLDING = "SUSPECTED_WITHHOLDING"
    UNITEMISED_FEE = "UNITEMISED_FEE"
    ROUNDING_RESIDUE = "ROUNDING_RESIDUE"
    CROSS_WINDOW_UNRESOLVED = "CROSS_WINDOW_UNRESOLVED"
    SIGN_REVERSAL = "SIGN_REVERSAL"
    ENTITY_UNRESOLVED = "ENTITY_UNRESOLVED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    RATE_MISMATCH = "RATE_MISMATCH"
    STRUCTURALLY_INFEASIBLE = "STRUCTURALLY_INFEASIBLE"


class ResolutionTier(IntEnum):
    """Which tier of the semantic cascade resolved a counterparty (spec §5.9)."""

    EXACT_NORM = 1
    REFERENCE_TOKEN = 2
    FUZZY = 3
    MODEL = 4
    UNRESOLVED = 5


_EXPECTED_SIGN: dict[Kind, int] = {
    Kind.PAYMENT: +1,
    Kind.REFUND: -1,
    Kind.CHARGEBACK: -1,
    Kind.REPRESENTMENT: +1,
    Kind.FEE: -1,
    Kind.TAX_GST: -1,
    Kind.TAX_WITHHOLDING: -1,
    Kind.RESERVE_HOLD: -1,
    Kind.RESERVE_RELEASE: +1,
    Kind.ADJUSTMENT: 0,
    Kind.BANK_CHARGE: -1,
}


def expected_sign(kind: Kind) -> Literal[-1, 0, 1]:
    """``+1`` inflow, ``-1`` deduction, ``0`` either sign (``ADJUSTMENT`` only).

    The convention of spec §5.3 made checkable. Every ``Kind`` has an entry, so adding a kind
    without deciding its sign fails a test rather than defaulting silently.
    """
    return _EXPECTED_SIGN[kind]  # type: ignore[return-value]


def has_expected_sign(item: "LedgerItem") -> bool:
    """Whether the item's sign matches its kind.

    **This is deliberately a derived check rather than a model validator.** Generator stage 2
    asserts it over ground truth, so the answer key is always sign-correct. Ingest does *not*
    assert it, because corruption class 18 ``SIGN_REVERSAL`` posts a debit as a credit in a
    rendered view, and a validator that rejected such a row would make that class un-ingestible
    — the loader would raise instead of producing the case the system exists to diagnose
    (PLAN-P1 D1.1).
    """
    wanted = expected_sign(item.kind)
    if wanted == 0:
        return item.amount_paise != 0
    return (item.amount_paise > 0) == (wanted > 0)


class LedgerItem(BaseModel):
    """One line of the deduction stack, from any source. ``amount_paise`` is signed."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    kind: Kind
    amount_paise: int
    occurred_at: datetime
    account_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    instrument: Instrument | None = None
    order_id: str | None = None
    parent_id: str | None = None
    narration_raw: str
    narration_norm: str
    counterparty_raw: str | None = None
    counterparty_id: str | None = None
    source: Source

    @field_validator("amount_paise")
    @classmethod
    def _amount_must_be_nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("amount_paise must be non-zero; a zero-value ledger item is a defect")
        return v

    @field_validator("occurred_at")
    @classmethod
    def _store_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class BankCredit(BaseModel):
    """A credit landing in the merchant's account. The thing to be decomposed."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    amount_paise: int = Field(gt=0)
    value_date: date
    account_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    narration_raw: str
    narration_norm: str
    utr: str | None = None


class ProofLine(BaseModel):
    """One line of the §5.7 proof block, carrying where its amount came from."""

    model_config = _STRICT

    label: str
    detail: str
    amount_paise: int
    member_ids: tuple[str, ...]
    derived_from: str
    """``'LEDGER'``, a ``'RATE_TABLE:<path>'`` reference, or ``'DECLARED'``. A line that cannot
    name its derivation is not evidence."""


class ProofRecord(BaseModel):
    """The calculator-checkable record emitted for every verified decomposition."""

    model_config = _STRICT

    bank_credit_id: str
    lines: tuple[ProofLine, ...]
    computed_total_paise: int
    residual_paise: int
    regime: Regime
    uniqueness: Uniqueness
    alternate_count: int = Field(ge=0)
    pool_size: int = Field(ge=0)
    pool_scope: PoolScope
    tier_mix: dict[ResolutionTier, int] = Field(default_factory=dict)
    rate_config_digest: str
    """sha256 of the canonicalised rate config actually used. A proof that cannot name the rate
    table it was derived from cannot be replayed (PLAN-P1 D1.4)."""
    audit_entry_hash: str | None = None


class Decomposition(BaseModel):
    """A proposed or accepted explanation of one bank credit."""

    model_config = _STRICT

    bank_credit_id: str
    member_ids: tuple[str, ...]
    claimed_total_paise: int
    residual_paise: int
    regime: Regime
    uniqueness: Uniqueness
    alternate_count: int = Field(ge=0)
    pool_scope: PoolScope
    ordering_score: float
    """Built from observable quantities only, never from model self-reported confidence (NN-4,
    ADR-4). Published and compared as a fixed six-decimal string so it cannot break NN-9."""
    proof: ProofRecord

    @field_validator("member_ids")
    @classmethod
    def _members_sorted_and_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(v)) != len(v):
            raise ValueError("member_ids contains a duplicate; an item cannot be its own sibling")
        if list(v) != sorted(v):
            raise ValueError("member_ids must be sorted; fixed ordering is an NN-9 requirement")
        return v


def render_score(score: float) -> str:
    """The one rendering of ``ordering_score``, used for every comparison and serialisation.

    A float in a hashed audit payload or a threshold comparison would make the run
    machine-dependent and break NN-9, so the score becomes a fixed six-decimal string at the
    boundary and stays one (PLAN-P1 D1.3).
    """
    return f"{score:.6f}"
