"""CLI. CP3 ships ``solve`` so the MIXED_N_M definition-of-done command exists."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from residual_zero.candidates import build_pool
from residual_zero.config import load_fees, load_profile, load_solver_config, load_tax_rates
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import Kind, Uniqueness
from residual_zero.money import format_rupees
from residual_zero.solver import solve_search
from residual_zero.solver.fastpath import DeclaredLine, verify_declared


def _load_split(split: str):
    root = SourceRoot(Path("data").joinpath(split, "rendered"))
    return load_ledger_items(root), load_bank_credits(root), load_settlement_report(root)


def _is_mixed_nm(kinds: tuple[Kind, ...]) -> bool:
    n_pay = sum(1 for k in kinds if k == Kind.PAYMENT)
    n_ref = sum(1 for k in kinds if k == Kind.REFUND)
    return n_pay >= 2 and n_ref >= 1


def _profile_for_split(split: str) -> Path:
    if split == "test":
        return Path("config").joinpath("profiles").joinpath("phase1_test.yaml")
    return Path("config").joinpath("profiles").joinpath("phase1.yaml")


def _print_proof(credit, member_ids, ledger, residual, header: str) -> None:
    print(f"credit {credit.id}")
    print(f"  {header}")
    print(f"  members: {len(member_ids)}")
    for mid in member_ids:
        item = ledger[mid]
        print(f"    {item.kind.value:16} {format_rupees(item.amount_paise):>14}  {mid}")
    print(f"  credit amount: {format_rupees(credit.amount_paise)}")
    print(f"  residual:      {format_rupees(residual)}")
    print()


def _cmd_solve(args: argparse.Namespace) -> int:
    items, credits, declared_rows = _load_split(args.split)
    cfg = load_solver_config()
    rates = load_tax_rates()
    fees = load_fees()
    reserve_bps = load_profile(_profile_for_split(args.split)).reserve_bps
    ledger = {it.id: it for it in items}
    by_credit: dict[str, list] = defaultdict(list)
    for row in declared_rows:
        by_credit[row.credit_id].append(row)
    shown = 0
    for credit in credits:
        declared = by_credit.get(credit.id, ())
        declared_kinds = tuple(row.kind for row in declared)
        pool = None
        if args.class_id == 4:
            if declared and not _is_mixed_nm(declared_kinds):
                continue
            if not declared:
                pool = build_pool(credit, items, cfg)
                if not _is_mixed_nm(pool.kinds):
                    continue
        residual = None
        member_ids: tuple[str, ...] = ()
        header = ""
        if declared:
            fp_lines = tuple(
                DeclaredLine(row.item_id, row.kind, row.amount_paise, row.instrument)
                for row in declared
            )
            fast = verify_declared(credit, fp_lines, ledger, rates, fees, reserve_bps=reserve_bps)
            member_ids = tuple(row.item_id for row in declared if row.item_id in ledger)
            residual = fast.residual_paise
            header = (
                f"regime: A_DECLARED  ok: {fast.ok}  "
                f"line_deltas: {len(fast.line_deltas)}  missing: {len(fast.missing_item_ids)}"
            )
        else:
            if pool is None:
                pool = build_pool(credit, items, cfg)
            result = solve_search(pool, credit.amount_paise, cfg)
            header = (
                f"uniqueness: {result.uniqueness.value}  "
                f"pool_size: {result.pool_size}  scope: {result.pool_scope.value}"
            )
            if result.uniqueness == Uniqueness.UNIQUE:
                member_ids = result.member_ids
                residual = credit.amount_paise - sum(ledger[i].amount_paise for i in member_ids)
        if residual != 0 or not member_ids:
            continue
        if args.show_proof:
            _print_proof(credit, member_ids, ledger, residual, header)
        shown += 1
        if args.limit and shown >= args.limit:
            break
    if args.class_id == 4 and args.limit and shown < args.limit:
        print(
            f"only {shown} MIXED_N_M credits decomposed at zero paise residual "
            f"(wanted {args.limit})",
            file=sys.stderr,
        )
        return 1
    return 0


def _cmd_run_org(args) -> int:
    """Record a run for one organisation, into whichever database is configured.

    The backend comes from the environment, never from a guess: production requires a
    PostgreSQL RZ_DATABASE_URL and refuses to write a local file instead. A failure to
    persist is a failure of the run, reported as such and with a non-zero exit — the
    engine succeeding is not the same thing as the run being recorded.
    """
    from residual_zero.identity.store import AuthError, IdentityStore
    from residual_zero.runner import (
        PersistenceError,
        RunConflict,
        record_run,
        require_production_database,
    )

    # Before the identity store, not after. Opening it under a production environment with
    # no PostgreSQL creates a local SQLite identity database and then reports "unknown
    # organisation" — a loud failure for the wrong reason, having already written exactly
    # the local production database that must never exist. Caught by running the real
    # image with RZ_DATABASE_URL unset.
    try:
        require_production_database()
    except PersistenceError as exc:
        print(str(exc), file=sys.stderr)
        return 4

    try:
        store = IdentityStore()
        found = store.find_organization(args.org)
        if found is None:
            print(f"unknown organisation {args.org!r}", file=sys.stderr)
            return 2
        tenant = store.tenant_for_org(found.org_id)
    except (AuthError, PersistenceError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        result = record_run(
            tenant=tenant,
            split=args.split,
            limit=args.limit,
            run_id=args.run_id or None,
            offline=args.offline,
        )
    except RunConflict as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except PersistenceError as exc:
        print(f"run NOT recorded: {exc}", file=sys.stderr)
        return 4

    if result.reused:
        print(
            f"run {result.run_id} already recorded for {result.org_id} "
            f"({result.n_persisted}/{result.n_credits} credits covered, "
            f"{result.backend}); nothing to do"
        )
        return 0
    # Coverage first, because that is what "the run did the work" means. The invocation's
    # own tally is reported beside it and never instead of it.
    print(
        f"recorded run {result.run_id} for {result.org_id}: "
        f"{result.status} {result.n_persisted}/{result.n_credits} credits covered "
        f"({result.n_computed} computed, {result.n_reused} already persisted) "
        f"into {result.backend}"
    )
    if not result.complete:
        print(
            f"run {result.run_id} is PARTIAL: "
            f"{result.n_credits - result.n_persisted} credits are not covered. "
            f"Re-running computes exactly those.",
            file=sys.stderr,
        )
        return 5
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="residual_zero")
    sub = parser.add_subparsers(dest="cmd", required=True)
    solve_p = sub.add_parser("solve")
    solve_p.add_argument("--split", default="dev")
    solve_p.add_argument("--class", dest="class_id", type=int, default=None)
    solve_p.add_argument("--limit", type=int, default=0)
    solve_p.add_argument("--show-proof", action="store_true")
    run_p = sub.add_parser("run")
    run_p.add_argument("--split", default="dev")
    run_p.add_argument("--limit", type=int, default=0)
    run_p.add_argument("--out", default="artifacts/dev")
    run_p.add_argument("--offline", action="store_true")
    run_p.add_argument(
        "--org", default="",
        help="record the run for this organisation, in the configured database. "
             "Without it the run writes the local SQLite ledger under --out.",
    )
    run_p.add_argument(
        "--run-id", default="",
        help="override the derived run identity. The default is a digest of "
             "organisation + dataset + configuration, so the same run twice collides.",
    )
    challenge_p = sub.add_parser("challenge")
    challenge_p.add_argument("file")
    args = parser.parse_args(argv)
    if args.cmd == "solve":
        return _cmd_solve(args)
    if args.cmd == "run":
        if args.org:
            return _cmd_run_org(args)
        # No organisation named: the single-tenant local path, unchanged. It writes the
        # SQLite ledger under --out and records no run, which is what every existing
        # caller and Makefile target expects.
        from residual_zero.orchestrator import run_split
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        db = out.joinpath("ledger.sqlite")
        n = run_split(args.split, db, limit=args.limit, offline=args.offline)
        print(f"processed {n} credits into {db}")
        return 0
    if args.cmd == "challenge":
        from residual_zero.challenge import run_challenge
        from residual_zero.models import Disposition
        disp = run_challenge(Path(args.file))
        print(disp.value)
        return 0
    raise SystemError(f"unhandled command {args.cmd}")


if __name__ == "__main__":
    sys.exit(main())
