"""A3: full system. Same pools as A2, uniqueness, verifier, ordering score."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from pydantic import Field

from residual_zero.candidates import WIDENED_KINDS, build_pool
from residual_zero.config import (
    FeeSchedule,
    LLMRuntimeConfig,
    SolverConfig,
    TaxRates,
    ThresholdNotDerivedError,
    load_profile,
)
from residual_zero.features import FeatureFlags, load_features
from residual_zero.solver.tolerance import apply_derived_epsilon
from residual_zero.exceptions.classify import ExceptionSignals, classify
from residual_zero.models import BankCredit, Disposition, LedgerItem, PoolScope, Regime, ResolutionTier, Uniqueness
from residual_zero.ordering import ordering_score, render_ordering_score
from residual_zero.semantic.tiers import registry_from_items, resolve
from residual_zero.solver import collect_enumerated, disambiguate, solve_search
from residual_zero.solver.fastpath import DeclaredLine, verify_declared
from residual_zero.tz import to_ist_date_display
from residual_zero.verify import verify_decomposition

from . import ArmResult
from eval.curve import ScoredCredit


class A3Result(ArmResult):
    scores: dict[str, str] = Field(default_factory=dict)
    eligible: dict[str, bool] = Field(default_factory=dict)
    residuals: dict[str, int] = Field(default_factory=dict)
    regimes: dict[str, Regime] = Field(default_factory=dict)
    scored: tuple[ScoredCredit, ...] = ()
    gate_a_ok: dict[str, bool] = Field(default_factory=dict)
    uniqueness: dict[str, str] = Field(default_factory=dict)
    ops_source: dict[str, str] = Field(default_factory=dict)


def run_a3(
    items: Sequence[LedgerItem],
    credits: Sequence[BankCredit],
    declared_by_credit: dict[str, list],
    truth_members: dict[str, tuple[str, ...]],
    rates: TaxRates,
    fees: FeeSchedule,
    cfg: SolverConfig,
    llm_cfg: LLMRuntimeConfig,
    reserve_bps: int,
    flags: FeatureFlags | None = None,
) -> A3Result:
    ledger = {it.id: it for it in items}
    flags = flags if flags is not None else load_features()
    cfg = apply_derived_epsilon(cfg, flags)
    registry = registry_from_items(items)
    try:
        threshold = cfg.autonomy.derived_threshold
    except ThresholdNotDerivedError:
        threshold = None
    predictions: dict[str, tuple[str, ...]] = {}
    dispositions: dict[str, Disposition] = {}
    scores: dict[str, str] = {}
    eligible_map: dict[str, bool] = {}
    residuals: dict[str, int] = {}
    regimes: dict[str, Regime] = {}
    gate_a_ok: dict[str, bool] = {}
    uniqueness: dict[str, str] = {}
    ops_source: dict[str, str] = {}
    scored: list[ScoredCredit] = []
    for credit in credits:
        declared = declared_by_credit.get(credit.id, ())
        regime = Regime.A_DECLARED if declared else Regime.B_SEARCHED
        member_ids: tuple[str, ...] = ()
        fp_ok = False
        source = ""
        if declared:
            fp = verify_declared(
                credit,
                tuple(DeclaredLine(r.item_id, r.kind, r.amount_paise, r.instrument) for r in declared),
                ledger, rates, fees, reserve_bps=reserve_bps,
                allow_declared_ops=flags.f59_settlement_declared_ops,
                allow_missing_rate_ids=flags.f60_reconstruct_missing_rate_ids,
            )
            fp_ok = fp.ok
            source = fp.ops_source
            if fp.ok:
                member_ids = tuple(r.item_id for r in declared if r.item_id in ledger)
            elif flags.f58_named_declared_members:
                # Settlement named these ids. Gate A failed the rate re-derive.
                # Predicting the named set is multi-source recon, not auto-clear.
                member_ids = tuple(r.item_id for r in declared if r.item_id in ledger)
        pool = build_pool(credit, items, cfg)
        solve = solve_search(pool, credit.amount_paise, cfg)
        if (
            flags.f31_disambiguation
            and solve.uniqueness == Uniqueness.AMBIGUOUS
            and solve.pool_scope == PoolScope.FULL
            and not member_ids
        ):
            enumerated, capped, budgeted = collect_enumerated(
                pool, credit.amount_paise, cfg, flags.f31_enumerate_cap,
            )
            if not budgeted and enumerated:
                d = disambiguate(
                    pool.item_ids, enumerated, ledger, rates, fees, reserve_bps,
                    frozenset(), enumeration_capped=capped,
                )
                if d.uniqueness == Uniqueness.UNIQUE:
                    solve = solve.model_copy(
                        update={
                            "uniqueness": Uniqueness.UNIQUE,
                            "member_ids": d.member_ids,
                            "alternates": 1,
                        }
                    )
        if not member_ids and solve.uniqueness == Uniqueness.UNIQUE and solve.pool_scope == PoolScope.FULL:
            member_ids = solve.member_ids
        outcome = verify_decomposition(
            credit, member_ids, ledger, regime, rates, fees, reserve_bps=reserve_bps,
        )
        pool_items = [ledger[i] for i in pool.item_ids if i in ledger]
        resolutions = [
            resolve(it.counterparty_raw or "", it.narration_norm, None, registry, llm_cfg, None)
            for it in pool_items
        ]
        unresolved = sum(1 for r in resolutions if r.tier == ResolutionTier.UNRESOLVED)
        base_start = credit.value_date - timedelta(days=cfg.windows.base_days_before)
        xwin = 0
        for mid in member_ids:
            item = ledger.get(mid)
            if item is None:
                continue
            occurred = date.fromisoformat(to_ist_date_display(item.occurred_at))
            if occurred < base_start and item.kind in WIDENED_KINDS:
                xwin += 1
        score = ordering_score(solve, resolutions, xwin, len(member_ids), cfg)
        score_s = render_ordering_score(score)
        eligible = (
            outcome.accepted
            and solve.uniqueness == Uniqueness.UNIQUE
            and solve.pool_scope == PoolScope.FULL
            and unresolved == 0
        )
        if solve.uniqueness == Uniqueness.BUDGET_EXCEEDED or solve.pool_scope == PoolScope.REDUCED:
            disp = Disposition.BUDGET_EXCEEDED
        elif eligible and threshold is not None and score_s >= threshold:
            disp = Disposition.CLEARED
        else:
            disp = Disposition.FLAGGED
        predictions[credit.id] = tuple(sorted(member_ids))
        dispositions[credit.id] = disp
        scores[credit.id] = score_s
        eligible_map[credit.id] = eligible
        residuals[credit.id] = outcome.residual_paise
        regimes[credit.id] = regime
        gate_a_ok[credit.id] = fp_ok
        uniqueness[credit.id] = solve.uniqueness.value
        ops_source[credit.id] = source
        scored.append(
            ScoredCredit(
                credit.id,
                tuple(sorted(member_ids)),
                score_s,
                eligible,
                tuple(sorted(truth_members.get(credit.id, ()))),
            )
        )
    return A3Result(
        arm="a3",
        predictions=predictions,
        dispositions=dispositions,
        has_exception_path=True,
        has_budget_path=True,
        scores=scores,
        eligible=eligible_map,
        residuals=residuals,
        regimes=regimes,
        scored=tuple(scored),
        gate_a_ok=gate_a_ok,
        uniqueness=uniqueness,
        ops_source=ops_source,
    )
