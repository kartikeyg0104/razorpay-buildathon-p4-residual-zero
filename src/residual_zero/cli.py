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
    args = parser.parse_args(argv)
    if args.cmd == "solve":
        return _cmd_solve(args)
    if args.cmd == "run":
        from residual_zero.orchestrator import run_split
        db = Path(args.out).joinpath("ledger.sqlite")
        n = run_split(args.split, db, limit=args.limit)
        print(f"processed {n} credits into {db}")
        return 0
    raise SystemError(f"unhandled command {args.cmd}")


if __name__ == "__main__":
    sys.exit(main())
