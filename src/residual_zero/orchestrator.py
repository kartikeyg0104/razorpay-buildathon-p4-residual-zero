"""Arithmetic DAG: ingest → candidates → solve/fastpath → verify → proof → audit → disposition."""

from __future__ import annotations

from pathlib import Path

from residual_zero.audit import append_entry, open_audit
from residual_zero.candidates import build_pool
from residual_zero.config import config_digest, load_fees, load_profile, load_solver_config, load_tax_rates
from residual_zero.db import init_db
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import Disposition, PoolScope, Regime, Uniqueness
from residual_zero.proof import build_proof
from residual_zero.solver import solve_search
from residual_zero.solver.fastpath import DeclaredLine, verify_declared
from residual_zero.verify import open_verify, verify_decomposition, write_cleared


def run_split(split: str, db_path: Path, limit: int = 0) -> int:
    """Process a split into the sqlite ledger and audit chain. Returns credits processed."""
    init_db(db_path)
    profile_path = Path("config").joinpath("profiles").joinpath(
        "phase1_test.yaml" if split == "test" else "phase1.yaml"
    )
    rates = load_tax_rates()
    fees = load_fees()
    cfg = load_solver_config()
    reserve_bps = load_profile(profile_path).reserve_bps
    digest = config_digest(rates, fees)
    root = SourceRoot(Path("data").joinpath(split, "rendered"))
    items = load_ledger_items(root)
    credits = load_bank_credits(root)
    declared_rows = load_settlement_report(root)
    ledger = {it.id: it for it in items}
    by_credit: dict[str, list] = {}
    for row in declared_rows:
        by_credit.setdefault(row.credit_id, []).append(row)
    audit = open_audit(db_path)
    verify_conn = open_verify(db_path)
    n = 0
    for credit in credits:
        declared = by_credit.get(credit.id, ())
        regime = Regime.A_DECLARED if declared else Regime.B_SEARCHED
        member_ids: tuple[str, ...] = ()
        if declared:
            fp = verify_declared(
                credit,
                tuple(DeclaredLine(r.item_id, r.kind, r.amount_paise, r.instrument) for r in declared),
                ledger, rates, fees, reserve_bps=reserve_bps,
            )
            if fp.ok:
                member_ids = tuple(r.item_id for r in declared if r.item_id in ledger)
        if not member_ids:
            pool = build_pool(credit, items, cfg)
            solve = solve_search(pool, credit.amount_paise, cfg)
            if solve.uniqueness == Uniqueness.UNIQUE and solve.pool_scope == PoolScope.FULL:
                member_ids = solve.member_ids
        else:
            pool = build_pool(credit, items, cfg)
            solve = solve_search(pool, credit.amount_paise, cfg)
        outcome = verify_decomposition(
            credit, member_ids, ledger, regime, rates, fees, reserve_bps=reserve_bps,
        )
        if outcome.accepted and solve.uniqueness == Uniqueness.UNIQUE and solve.pool_scope == PoolScope.FULL:
            # Fast-path ok credits may still be AMBIGUOUS under search; they do not auto-clear
            # until uniqueness is established. Regime A with ok residual is accepted arithmetic
            # but disposition stays FLAGGED unless UNIQUE.
            disposition = Disposition.FLAGGED
        else:
            disposition = Disposition.FLAGGED
        if solve.uniqueness == Uniqueness.BUDGET_EXCEEDED or solve.pool_scope == PoolScope.REDUCED:
            disposition = Disposition.BUDGET_EXCEEDED
        append_entry(
            audit,
            {
                "bank_credit_id": credit.id,
                "regime": regime.value,
                "uniqueness": solve.uniqueness.value,
                "accepted": outcome.accepted,
                "residual_paise": outcome.residual_paise,
                "disposition": disposition.value,
            },
            {"pool_size": solve.pool_size, "axis_width": solve.axis_width},
        )
        n += 1
        if limit and n >= limit:
            break
    audit.close()
    verify_conn.close()
    return n
