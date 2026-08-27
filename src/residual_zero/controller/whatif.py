"""F43: substitute rate/reserve parameters over an already-known member set. Not a counterfactual."""

from __future__ import annotations

from typing import Mapping, Sequence

from residual_zero.config import FeeSchedule, TaxRates
from residual_zero.models import BankCredit, LedgerItem
from residual_zero.solver.fastpath import DeclaredLine, FastPathResult, verify_declared
from residual_zero.verify import VerificationOutcome, verify_decomposition


def recompute(
    credit: BankCredit,
    member_ids: Sequence[str],
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int,
) -> FastPathResult:
    """Re-derive the settlement of a known member set under the given tables."""
    declared = tuple(
        DeclaredLine(ledger[mid].id, ledger[mid].kind, ledger[mid].amount_paise, ledger[mid].instrument)
        for mid in member_ids
        if mid in ledger
    )
    return verify_declared(credit, declared, ledger, rates, fees, reserve_bps=reserve_bps)


def reproduces_exactly(
    credit: BankCredit,
    member_ids: Sequence[str],
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int,
) -> VerificationOutcome:
    """True when the known set still sums to the credit at paise under these parameters."""
    from residual_zero.models import Regime

    return verify_decomposition(
        credit, member_ids, ledger, Regime.A_DECLARED, rates, fees, reserve_bps=reserve_bps
    )
