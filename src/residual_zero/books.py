"""F33 conservation identity. Batch sweep, never an incremental write guard (PLAN-P2 §0.1).

Over any period, for any single account:

    sum(bank credits) = sum(members of CLEARED decompositions)
                      + sum(unreconciled credit amounts)

and every ledger item belongs to at most one CLEARED decomposition.

Items that straddle a period boundary are attributed to the credit they were claimed
on (that credit's value_date), not to the item's occurred_at.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.db import open_readonly
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import BankCredit, LedgerItem
from residual_zero.money import format_rupees

_STRICT = ConfigDict(frozen=True, extra="forbid")


class ConservationReport(BaseModel):
    model_config = _STRICT

    period_start: date
    period_end: date
    account_id: str
    credits_paise: int
    cleared_members_paise: int
    unreconciled_credits_paise: int
    double_claimed_item_ids: tuple[str, ...]
    missing_member_ids: tuple[str, ...]
    identity_holds: bool
    n_credits: int = Field(ge=0)
    n_cleared: int = Field(ge=0)


def _cleared_members(conn: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    """bank_credit_id -> member item_ids for CLEARED rows only."""
    rows = list(
        conn.execute(
            "SELECT r.bank_credit_id, m.item_id "
            "FROM reconciliation r "
            "JOIN decomposition_member m ON m.bank_credit_id = r.bank_credit_id "
            "WHERE r.disposition = 'CLEARED' "
            "ORDER BY r.bank_credit_id, m.item_id"
        )
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for credit_id, item_id in rows:
        grouped[str(credit_id)].append(str(item_id))
    return {cid: tuple(ids) for cid, ids in grouped.items()}


def identity_from_cleared(
    credits: tuple[BankCredit, ...] | list[BankCredit],
    ledger: Mapping[str, LedgerItem],
    account_id: str,
    start: date,
    end: date,
    cleared: Mapping[str, Sequence[str]],
) -> ConservationReport:
    """Identity for one account over [start, end] using an in-memory cleared map.

    Search-cleared and ops-accepted (declared, residual 0, posted sum equals credit)
    share this formula. The map is the only input that changes.
    """
    in_period = [
        c
        for c in credits
        if c.account_id == account_id and start <= c.value_date <= end
    ]
    claimed: dict[str, list[str]] = defaultdict(list)
    for cid, mids in cleared.items():
        for item_id in mids:
            claimed[str(item_id)].append(str(cid))
    double = tuple(sorted(i for i, owners in claimed.items() if len(set(owners)) > 1))
    credits_paise = sum(c.amount_paise for c in in_period)
    cleared_members_paise = 0
    missing: list[str] = []
    n_cleared = 0
    for credit in in_period:
        members = cleared.get(credit.id)
        if members is None:
            continue
        n_cleared += 1
        for item_id in members:
            item = ledger.get(item_id)
            if item is None:
                missing.append(item_id)
                continue
            cleared_members_paise += item.amount_paise
    unreconciled = sum(c.amount_paise for c in in_period if c.id not in cleared)
    identity = (
        credits_paise == cleared_members_paise + unreconciled
        and not double
        and not missing
    )
    return ConservationReport(
        period_start=start,
        period_end=end,
        account_id=account_id,
        credits_paise=credits_paise,
        cleared_members_paise=cleared_members_paise,
        unreconciled_credits_paise=unreconciled,
        double_claimed_item_ids=double,
        missing_member_ids=tuple(missing),
        identity_holds=identity,
        n_credits=len(in_period),
        n_cleared=n_cleared,
    )


def check_account(
    conn: sqlite3.Connection,
    credits: tuple[BankCredit, ...] | list[BankCredit],
    ledger: dict[str, LedgerItem],
    account_id: str,
    start: date,
    end: date,
) -> ConservationReport:
    """Identity for one account over [start, end] inclusive on credit.value_date."""
    return identity_from_cleared(
        credits, ledger, account_id, start, end, _cleared_members(conn),
    )


def check_books_from_cleared(
    credits: tuple[BankCredit, ...] | list[BankCredit],
    ledger: Mapping[str, LedgerItem],
    cleared: Mapping[str, Sequence[str]],
) -> tuple[ConservationReport, ...]:
    """One report per account using an in-memory cleared map (ops overlay or search)."""
    if not credits:
        return ()
    by_acct: dict[str, list[BankCredit]] = defaultdict(list)
    for credit in credits:
        by_acct[credit.account_id].append(credit)
    reports = []
    for account_id in sorted(by_acct):
        bucket = by_acct[account_id]
        start = min(c.value_date for c in bucket)
        end = max(c.value_date for c in bucket)
        reports.append(identity_from_cleared(credits, ledger, account_id, start, end, cleared))
    return tuple(reports)


def check_books(
    conn: sqlite3.Connection,
    credits: tuple[BankCredit, ...] | list[BankCredit],
    ledger: dict[str, LedgerItem],
) -> tuple[ConservationReport, ...]:
    """One report per account spanning min–max value_date of that account's credits."""
    return check_books_from_cleared(credits, ledger, _cleared_members(conn))


def format_identity(report: ConservationReport) -> str:
    lhs = format_rupees(report.credits_paise)
    members = format_rupees(report.cleared_members_paise)
    unrec = format_rupees(report.unreconciled_credits_paise)
    rhs = format_rupees(report.cleared_members_paise + report.unreconciled_credits_paise)
    hold = "HOLDS" if report.identity_holds else "FAILS"
    return (
        f"F33 {report.account_id} [{report.period_start.isoformat()}, "
        f"{report.period_end.isoformat()}] {hold}: "
        f"{lhs} = {members} (cleared members) + {unrec} (unreconciled) "
        f"[rhs {rhs}]; double_claimed={len(report.double_claimed_item_ids)} "
        f"n_credits={report.n_credits} n_cleared={report.n_cleared}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="residual_zero.books")
    parser.add_argument("--db", default="artifacts/dev/ledger.sqlite")
    parser.add_argument("--split", default="dev")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"verify-books: missing {db_path}", file=sys.stderr)
        return 1
    root = SourceRoot(Path("data").joinpath(args.split, "rendered"))
    items = load_ledger_items(root)
    credits = load_bank_credits(root)
    ledger = {it.id: it for it in items}
    conn = open_readonly(db_path)
    try:
        reports = check_books(conn, credits, ledger)
        failed = False
        total_unrec = 0
        total_double = 0
        for report in reports:
            print(format_identity(report))
            total_unrec += report.unreconciled_credits_paise
            total_double += len(report.double_claimed_item_ids)
            if not report.identity_holds:
                failed = True
        print(
            f"verify-books unreconciled_value={format_rupees(total_unrec)} "
            f"double_claimed={total_double}"
        )
        return 1 if failed or total_double else 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
