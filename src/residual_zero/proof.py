"""§5.7 calculator-checkable proof block. Every figure is rendered here."""

from __future__ import annotations

from typing import Mapping

from residual_zero.models import BankCredit, ProofRecord, Regime, ResolutionTier
from residual_zero.money import format_rupees
from residual_zero.solver.enumerate import SolveResult
from residual_zero.verify import VerificationOutcome


def build_proof(
    credit: BankCredit,
    outcome: VerificationOutcome,
    solve: SolveResult,
    regime: Regime,
    tier_mix: Mapping[ResolutionTier, int],
    rate_digest: str,
) -> ProofRecord:
    return ProofRecord(
        bank_credit_id=credit.id,
        lines=outcome.derived_lines,
        computed_total_paise=credit.amount_paise - outcome.residual_paise,
        residual_paise=outcome.residual_paise,
        regime=regime,
        uniqueness=solve.uniqueness,
        alternate_count=solve.alternates,
        pool_size=solve.pool_size,
        pool_scope=solve.pool_scope,
        tier_mix=dict(tier_mix),
        rate_config_digest=rate_digest,
        audit_entry_hash=None,
    )


def render_proof(proof: ProofRecord, credit: BankCredit) -> str:
    """Aligned IST dates, rupees from money.format_rupees. Nothing downstream formats a number."""
    rows = []
    rows.append(f"PROOF  {credit.id}")
    rows.append(f"value_date  {credit.value_date.isoformat()}")
    rows.append(f"regime      {proof.regime.value}")
    rows.append(f"uniqueness  {proof.uniqueness.value}  alternates={proof.alternate_count}")
    rows.append("")
    for line in proof.lines:
        rows.append(
            f"{line.label:16} {format_rupees(line.amount_paise):>14}  {line.derived_from}  {line.detail}"
        )
    rows.append("")
    rows.append(f"{'computed':16} {format_rupees(proof.computed_total_paise):>14}")
    rows.append(f"{'credit':16} {format_rupees(credit.amount_paise):>14}")
    rows.append(f"{'residual':16} {format_rupees(proof.residual_paise):>14}")
    rows.append(f"rate_digest {proof.rate_config_digest}")
    return "\n".join(rows) + "\n"
