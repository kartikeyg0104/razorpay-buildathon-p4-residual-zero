"""Run a challenge fixture to a terminal disposition."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from residual_zero.config import load_fees, load_solver_config, load_tax_rates
from residual_zero.exceptions.classify import ExceptionSignals, classify
from residual_zero.models import (
    BankCredit,
    Disposition,
    Instrument,
    Kind,
    LedgerItem,
    PoolScope,
    ResolutionTier,
    Source,
    Uniqueness,
)
from residual_zero.normalise import normalise_narration
from residual_zero.solver import solve_search
from residual_zero.candidates import build_pool
from residual_zero.tz import IST, ensure_utc


def run_challenge(path: Path) -> Disposition:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for raw in data.get("items", []):
        items.append(
            LedgerItem(
                id=raw["id"],
                kind=Kind(raw["kind"]),
                amount_paise=raw["amount_paise"],
                occurred_at=ensure_utc(datetime.fromisoformat(raw["occurred_at"]).replace(tzinfo=IST)),
                account_id=raw["account_id"],
                currency="INR",
                instrument=Instrument(raw["instrument"]) if raw.get("instrument") else None,
                order_id=None,
                parent_id=None,
                narration_raw=raw.get("narration_raw", "x"),
                narration_norm=normalise_narration(raw.get("narration_raw", "x")),
                counterparty_raw=raw.get("counterparty_raw", "x"),
                counterparty_id=None,
                source=Source.INTERNAL_LEDGER,
            )
        )
    c = data["credit"]
    credit = BankCredit(
        id=c["id"],
        amount_paise=c["amount_paise"],
        value_date=date.fromisoformat(c["value_date"]),
        account_id=c["account_id"],
        currency="INR",
        narration_raw=c.get("narration_raw", "NEFT"),
        narration_norm=normalise_narration(c.get("narration_raw", "NEFT")),
        utr=c.get("utr"),
    )
    cfg = load_solver_config()
    rates, fees = load_tax_rates(), load_fees()
    pool = build_pool(credit, items, cfg)
    solve = solve_search(pool, credit.amount_paise, cfg)
    if solve.uniqueness == Uniqueness.BUDGET_EXCEEDED or solve.pool_scope == PoolScope.REDUCED:
        return Disposition.BUDGET_EXCEEDED
    if solve.uniqueness == Uniqueness.UNIQUE:
        return Disposition.CLEARED
    signals = ExceptionSignals(
        uniqueness=solve.uniqueness,
        pool_scope=solve.pool_scope,
        alternates=solve.alternates,
        pool_size=solve.pool_size,
        pool_gross_paise=pool.gross_paise,
        nearest_delta_paise=credit.amount_paise if solve.uniqueness == Uniqueness.NONE_FOUND else None,
        delta_matches_pool_member_ids=(),
        delta_matches_out_of_window_item_ids=(),
        delta_equals_twice_member_ids=(),
        duplicate_credit_ids=(),
        declared_line_deltas=(),
        unresolved_entity_count=0,
        cross_window_member_count=0,
        max_resolution_tier=ResolutionTier.EXACT_NORM,
    )
    classification = classify(signals, rates, fees, cfg)
    print(f"challenge {path.name}: {solve.uniqueness.value} -> {classification.exception_class.value}")
    return Disposition.FLAGGED
