"""Arithmetic DAG: ingest → candidates → resolve → solve/fastpath → verify → classify → audit."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from residual_zero.audit import append_entry, open_audit
from residual_zero.candidates import WIDENED_KINDS, build_pool
from residual_zero.config import (
    ThresholdNotDerivedError,
    config_digest,
    load_fees,
    load_llm_config,
    load_profile,
    load_solver_config,
    load_tax_rates,
)
from residual_zero.db import init_db
from residual_zero.exceptions import classify, open_exceptions, write_exception
from residual_zero.exceptions.classify import ExceptionSignals
from residual_zero.exceptions.narrate import narrate
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import Decomposition, Disposition, PoolScope, Regime, ResolutionTier, Uniqueness
from residual_zero.money import format_rupees
from residual_zero.ordering import ordering_score, render_ordering_score
from residual_zero.proof import build_proof
from residual_zero.tz import to_ist_date_display
from residual_zero.semantic.llm import CachedLLMClient, StubLLMClient
from residual_zero.semantic.tiers import registry_from_items, resolve, tier_mix
from residual_zero.solver import solve_search
from residual_zero.solver.fastpath import DeclaredLine, verify_declared
from residual_zero.verify import open_verify, verify_decomposition, write_cleared


def _duplicates(credits) -> dict[str, tuple[str, ...]]:
    groups: dict[tuple[str, int], list] = defaultdict(list)
    for credit in credits:
        groups[(credit.account_id, credit.amount_paise)].append(credit)
    out: dict[str, tuple[str, ...]] = {}
    for _key, bucket in groups.items():
        if len(bucket) < 2:
            continue
        for credit in bucket:
            others = tuple(
                other.id
                for other in bucket
                if other.id != credit.id and abs((other.value_date - credit.value_date).days) <= 1
            )
            if others:
                out[credit.id] = others
    return out


def _delta_matches(amount_paise: int, delta: int) -> bool:
    return abs(amount_paise) == abs(delta)


def run_split(split: str, db_path: Path, limit: int = 0, offline: bool = False) -> int:
    """Process a split into the sqlite ledger, exceptions, and audit chain."""
    init_db(db_path)
    profile_path = Path("config").joinpath("profiles").joinpath(
        "phase1_test.yaml" if split == "test" else "phase1.yaml"
    )
    rates = load_tax_rates()
    fees = load_fees()
    cfg = load_solver_config()
    llm_cfg = load_llm_config()
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
    registry = registry_from_items(items)
    provider = StubLLMClient()
    client = CachedLLMClient(
        provider,
        Path(llm_cfg.cache_dir),
        offline=offline,
        token_budget=llm_cfg.token_budget if llm_cfg.token_budget > 0 else 10**9,
        prompt_version=llm_cfg.prompt_version,
        model_id=llm_cfg.model_id,
    )
    dupes = _duplicates(credits)
    audit = open_audit(db_path)
    verify_conn = open_verify(db_path)
    exc_conn = open_exceptions(db_path)
    all_resolutions = []
    class_counts: dict[str, int] = defaultdict(int)
    n = 0
    try:
        threshold: str | None
        try:
            threshold = cfg.autonomy.derived_threshold
        except ThresholdNotDerivedError:
            threshold = None
        for credit in credits:
            declared = by_credit.get(credit.id, ())
            regime = Regime.A_DECLARED if declared else Regime.B_SEARCHED
            member_ids: tuple[str, ...] = ()
            if declared:
                fp = verify_declared(
                    credit,
                    tuple(
                        DeclaredLine(r.item_id, r.kind, r.amount_paise, r.instrument) for r in declared
                    ),
                    ledger, rates, fees, reserve_bps=reserve_bps,
                )
                if fp.ok:
                    member_ids = tuple(r.item_id for r in declared if r.item_id in ledger)
            pool = build_pool(credit, items, cfg)
            solve = solve_search(pool, credit.amount_paise, cfg)
            if not member_ids:
                if solve.uniqueness == Uniqueness.UNIQUE and solve.pool_scope == PoolScope.FULL:
                    member_ids = solve.member_ids
            outcome = verify_decomposition(
                credit, member_ids, ledger, regime, rates, fees, reserve_bps=reserve_bps,
            )
            pool_items = [ledger[i] for i in pool.item_ids if i in ledger]
            resolutions = []
            for item in pool_items:
                res = resolve(
                    item.counterparty_raw or "",
                    item.narration_norm,
                    None,
                    registry,
                    llm_cfg,
                    client,
                )
                resolutions.append(res)
            all_resolutions.extend(resolutions)
            unresolved = sum(1 for r in resolutions if r.tier == ResolutionTier.UNRESOLVED)
            max_tier = max((r.tier for r in resolutions), default=ResolutionTier.EXACT_NORM)
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

            delta: int | None
            if solve.uniqueness in {Uniqueness.AMBIGUOUS, Uniqueness.BUDGET_EXCEEDED}:
                delta = None
            elif not outcome.accepted:
                delta = outcome.residual_paise
                if solve.nearest_delta_rupees is not None and solve.uniqueness == Uniqueness.NONE_FOUND:
                    delta = solve.nearest_delta_rupees * 100
            else:
                delta = None

            in_pool_matches = tuple(
                it.id for it in pool_items if delta is not None and _delta_matches(it.amount_paise, delta)
            )
            twice = tuple(
                it.id
                for it in pool_items
                if delta is not None and delta == (-2 * it.amount_paise)
            )
            pool_ids = set(pool.item_ids)
            out_matches = ()
            if delta is not None:
                found = []
                for item in items:
                    if item.account_id != credit.account_id or item.currency != credit.currency:
                        continue
                    if item.id in pool_ids:
                        continue
                    if _delta_matches(item.amount_paise, delta):
                        found.append(item.id)
                out_matches = tuple(found)
            declared_deltas = ()
            if declared:
                fp_lines = tuple(
                    DeclaredLine(r.item_id, r.kind, r.amount_paise, r.instrument) for r in declared
                )
                fp_now = verify_declared(credit, fp_lines, ledger, rates, fees, reserve_bps=reserve_bps)
                declared_deltas = fp_now.line_deltas

            signals = ExceptionSignals(
                uniqueness=solve.uniqueness,
                pool_scope=solve.pool_scope,
                alternates=solve.alternates,
                pool_size=solve.pool_size,
                pool_gross_paise=pool.gross_paise,
                nearest_delta_paise=delta,
                delta_matches_pool_member_ids=in_pool_matches,
                delta_matches_out_of_window_item_ids=out_matches,
                delta_equals_twice_member_ids=twice,
                duplicate_credit_ids=dupes.get(credit.id, ()),
                declared_line_deltas=declared_deltas,
                unresolved_entity_count=unresolved,
                cross_window_member_count=xwin,
                max_resolution_tier=max_tier,
            )
            classification = classify(signals, rates, fees, cfg)
            slots = {
                "DELTA": format_rupees(delta or 0),
                "GROSS": format_rupees(pool.gross_paise),
                "PCT": f"{rates.withholding.bps} bps",
                "ALTERNATES": str(solve.alternates),
                "DUPLICATES": ",".join(dupes.get(credit.id, ())),
            }
            # Narration is for the exception queue. Amounts are substituted here, never sent.
            _prose = narrate(classification, signals, slots, None)

            can_clear = (
                outcome.accepted
                and solve.uniqueness == Uniqueness.UNIQUE
                and solve.pool_scope == PoolScope.FULL
                and unresolved == 0
                and threshold is not None
                and score_s >= threshold
            )
            if solve.uniqueness == Uniqueness.BUDGET_EXCEEDED or solve.pool_scope == PoolScope.REDUCED:
                disposition = Disposition.BUDGET_EXCEEDED
            elif can_clear:
                disposition = Disposition.CLEARED
            else:
                disposition = Disposition.FLAGGED

            if disposition != Disposition.CLEARED:
                write_exception(exc_conn, credit.id, classification.exception_class)
                class_counts[classification.exception_class.value] += 1
            else:
                proof = build_proof(
                    credit, outcome, solve, regime, tier_mix(resolutions), digest,
                )
                deco = Decomposition(
                    bank_credit_id=credit.id,
                    member_ids=tuple(sorted(member_ids)),
                    claimed_total_paise=sum(ledger[m].amount_paise for m in member_ids),
                    residual_paise=outcome.residual_paise,
                    regime=regime,
                    uniqueness=solve.uniqueness,
                    alternate_count=solve.alternates,
                    pool_scope=solve.pool_scope,
                    ordering_score=score,
                    proof=proof,
                )
                write_cleared(verify_conn, deco)

            append_entry(
                audit,
                {
                    "bank_credit_id": credit.id,
                    "regime": regime.value,
                    "uniqueness": solve.uniqueness.value,
                    "accepted": outcome.accepted,
                    "residual_paise": outcome.residual_paise,
                    "disposition": disposition.value,
                    "ordering_score": score_s,
                    "exception_class": classification.exception_class.value,
                    "matched_rule": classification.matched_rule,
                },
                {"pool_size": solve.pool_size, "axis_width": solve.axis_width, "tier": int(max_tier)},
            )
            n += 1
            if limit and n >= limit:
                break
        mix = tier_mix(all_resolutions)
        print("tier_mix " + " ".join(f"{t.name}={mix[t]}" for t in mix))
        print("exception_classes " + " ".join(f"{k}={v}" for k, v in sorted(class_counts.items())))
    finally:
        audit.close()
        verify_conn.close()
        exc_conn.close()
    return n
