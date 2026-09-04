"""Verifier: the only writer to the reconciliation tables. Acceptance never widens (NN-12)."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from residual_zero.config import FeeSchedule, TaxRates
from residual_zero.db import _open_readwrite
from residual_zero.models import BankCredit, Decomposition, Kind, LedgerItem, ProofLine, Regime
from residual_zero.solver.fastpath import DeclaredLine, verify_declared

_STRICT = ConfigDict(frozen=True, extra="forbid")


class VerificationOutcome(BaseModel):
    model_config = _STRICT

    accepted: bool
    residual_paise: int
    derived_lines: tuple[ProofLine, ...]
    mismatched_line_ids: tuple[str, ...]
    reason: str | None = None


def verify_decomposition(
    credit: BankCredit,
    member_ids: Sequence[str],
    ledger: Mapping[str, LedgerItem],
    regime: Regime,
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int = 0,
) -> VerificationOutcome:
    """Re-derive every rate-derived line at paise. Accepts only on a zero residual (NN-12)."""
    if not member_ids:
        return VerificationOutcome(
            accepted=False, residual_paise=credit.amount_paise, derived_lines=(),
            mismatched_line_ids=(), reason="empty member set",
        )
    missing = tuple(mid for mid in member_ids if mid not in ledger)
    declared = tuple(
        DeclaredLine(ledger[mid].id, ledger[mid].kind, ledger[mid].amount_paise, ledger[mid].instrument)
        for mid in member_ids if mid in ledger
    )
    fast = verify_declared(credit, declared, ledger, rates, fees, reserve_bps=reserve_bps)
    mismatched = tuple(item_id for item_id, delta in fast.line_deltas if delta != 0)
    lines = tuple(
        ProofLine(
            label=ledger[mid].kind.value if mid in ledger else "MISSING",
            detail=mid,
            amount_paise=ledger[mid].amount_paise if mid in ledger else 0,
            member_ids=(mid,),
            derived_from=(
                "RATE_TABLE:fees" if mid in ledger and ledger[mid].kind in
                {Kind.FEE, Kind.TAX_GST, Kind.TAX_WITHHOLDING, Kind.RESERVE_HOLD}
                else "LEDGER"
            ),
        )
        for mid in member_ids
    )
    accepted = (
        fast.residual_paise == 0
        and not mismatched
        and not missing
        and not fast.missing_item_ids
        and len(member_ids) > 0
    )
    reason = None if accepted else "nonzero residual or mismatched derived line"
    return VerificationOutcome(
        accepted=accepted,
        residual_paise=fast.residual_paise,
        derived_lines=lines,
        mismatched_line_ids=mismatched + missing,
        reason=reason,
    )


def open_verify(path) -> sqlite3.Connection:
    from pathlib import Path
    return _open_readwrite(Path(path), "verify")


class ConflictingClearError(RuntimeError):
    """A second, different explanation was offered for an already-cleared credit."""


def write_cleared(conn: sqlite3.Connection, decomposition: Decomposition) -> None:
    """Insert a cleared decomposition. The only function that writes reconciliation rows.

    Re-clearing the same credit with the same member set is a no-op, which is what makes a
    replay or a crash-resume safe (F25). Re-clearing it with a *different* member set is
    refused: two different explanations of one bank credit cannot both be true, and
    silently replacing the first would destroy the decomposition an earlier proof and audit
    entry were built from.

    The arithmetic is not repeated here. ``decomposition`` already carries the residual and
    uniqueness the solver and verifier established; this function only stores them.
    """
    existing = conn.execute(
        "SELECT disposition FROM reconciliation WHERE bank_credit_id = ?",
        (decomposition.bank_credit_id,),
    ).fetchone()
    if existing is not None and str(existing[0]) == "CLEARED":
        prior = tuple(
            str(r[0])
            for r in conn.execute(
                "SELECT item_id FROM decomposition_member WHERE bank_credit_id = ? "
                "ORDER BY item_id",
                (decomposition.bank_credit_id,),
            )
        )
        if prior and prior != tuple(decomposition.member_ids):
            raise ConflictingClearError(
                f"{decomposition.bank_credit_id} is already cleared with "
                f"{len(prior)} members; refusing to replace them with "
                f"{len(decomposition.member_ids)}"
            )
    conn.execute(
        "INSERT OR REPLACE INTO reconciliation "
        "(bank_credit_id, claimed_total_paise, residual_paise, uniqueness, pool_scope, disposition) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            decomposition.bank_credit_id,
            decomposition.claimed_total_paise,
            decomposition.residual_paise,
            decomposition.uniqueness.value,
            decomposition.pool_scope.value,
            "CLEARED",
        ),
    )
    conn.execute("DELETE FROM decomposition_member WHERE bank_credit_id = ?", (decomposition.bank_credit_id,))
    for mid in decomposition.member_ids:
        conn.execute(
            "INSERT INTO decomposition_member (bank_credit_id, item_id) VALUES (?, ?)",
            (decomposition.bank_credit_id, mid),
        )
    conn.commit()
