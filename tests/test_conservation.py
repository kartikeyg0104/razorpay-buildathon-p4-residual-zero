"""F33 conservation identity: period identity and no double-claimed items."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

from residual_zero.books import check_account, check_books, format_identity
from residual_zero.db import init_db, open_readonly
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.verify import open_verify, write_cleared
from residual_zero.models import Decomposition, PoolScope, ProofLine, ProofRecord, Regime, Uniqueness


_AWARE = datetime(2025, 1, 9, 6, 0, tzinfo=timezone.utc)


def _item(item_id: str, amount: int, account: str = "acc_01") -> LedgerItem:
    return LedgerItem(
        id=item_id,
        kind=Kind.PAYMENT,
        amount_paise=amount,
        occurred_at=_AWARE,
        account_id=account,
        currency="INR",
        instrument=Instrument.UPI,
        narration_raw="pay",
        narration_norm="pay",
        source=Source.INTERNAL_LEDGER,
    )


def _credit(cid: str, amount: int, day: date, account: str = "acc_01") -> BankCredit:
    return BankCredit(
        id=cid,
        amount_paise=amount,
        value_date=day,
        account_id=account,
        currency="INR",
        narration_raw="cr",
        narration_norm="cr",
    )


def _proof(cid: str) -> ProofRecord:
    return ProofRecord(
        bank_credit_id=cid,
        lines=(ProofLine(label="PAYMENT", detail="x", amount_paise=100, member_ids=("x",), derived_from="LEDGER"),),
        computed_total_paise=100,
        residual_paise=0,
        regime=Regime.A_DECLARED,
        uniqueness=Uniqueness.UNIQUE,
        alternate_count=1,
        pool_size=1,
        pool_scope=PoolScope.FULL,
        rate_config_digest="ab" * 32,
    )


def _deco(cid: str, members: tuple[str, ...], total: int) -> Decomposition:
    return Decomposition(
        bank_credit_id=cid,
        member_ids=tuple(sorted(members)),
        claimed_total_paise=total,
        residual_paise=0,
        regime=Regime.A_DECLARED,
        uniqueness=Uniqueness.UNIQUE,
        alternate_count=1,
        pool_scope=PoolScope.FULL,
        ordering_score=0.0,
        proof=_proof(cid),
    )


def test_identity_holds_when_nothing_is_cleared(tmp_path):
    db = tmp_path / "l.sqlite"
    init_db(db)
    credits = (_credit("c1", 10_000, date(2025, 1, 9)), _credit("c2", 20_000, date(2025, 1, 10)))
    ledger = {"p1": _item("p1", 10_000)}
    conn = open_readonly(db)
    try:
        reports = check_books(conn, credits, ledger)
    finally:
        conn.close()
    assert len(reports) == 1
    r = reports[0]
    assert r.identity_holds
    assert r.cleared_members_paise == 0
    assert r.unreconciled_credits_paise == 30_000
    assert r.double_claimed_item_ids == ()
    assert "HOLDS" in format_identity(r)


def test_identity_holds_for_a_cleared_credit(tmp_path):
    db = tmp_path / "l.sqlite"
    init_db(db)
    item = _item("itm_a", 50_000)
    credit = _credit("crd_a", 50_000, date(2025, 1, 9))
    v = open_verify(db)
    try:
        write_cleared(v, _deco("crd_a", ("itm_a",), 50_000))
    finally:
        v.close()
    conn = open_readonly(db)
    try:
        r = check_account(conn, (credit,), {"itm_a": item}, "acc_01", date(2025, 1, 1), date(2025, 12, 31))
    finally:
        conn.close()
    assert r.identity_holds
    assert r.n_cleared == 1
    assert r.cleared_members_paise == 50_000
    assert r.unreconciled_credits_paise == 0


def test_double_claim_is_detected(tmp_path):
    db = tmp_path / "l.sqlite"
    init_db(db)
    shared = _item("itm_shared", 10_000)
    other = _item("itm_b", 10_000)
    c1 = _credit("crd_1", 10_000, date(2025, 1, 9))
    c2 = _credit("crd_2", 10_000, date(2025, 1, 10))
    v = open_verify(db)
    try:
        write_cleared(v, _deco("crd_1", ("itm_shared",), 10_000))
        write_cleared(v, _deco("crd_2", ("itm_shared", "itm_b")[:1], 10_000))
    finally:
        v.close()
    conn = open_readonly(db)
    try:
        r = check_books(conn, (c1, c2), {"itm_shared": shared, "itm_b": other})[0]
    finally:
        conn.close()
    assert r.double_claimed_item_ids == ("itm_shared",)
    assert r.identity_holds is False


def test_straddling_item_follows_the_credit_value_date(tmp_path):
    """An item that occurred in December is attributed to January if that is the credit's value_date."""
    db = tmp_path / "l.sqlite"
    init_db(db)
    item = _item("itm_old", 8_000)
    credit = _credit("crd_jan", 8_000, date(2025, 1, 6))
    v = open_verify(db)
    try:
        write_cleared(v, _deco("crd_jan", ("itm_old",), 8_000))
    finally:
        v.close()
    conn = open_readonly(db)
    try:
        in_jan = check_account(
            conn, (credit,), {"itm_old": item}, "acc_01", date(2025, 1, 1), date(2025, 1, 31)
        )
        in_dec = check_account(
            conn, (credit,), {"itm_old": item}, "acc_01", date(2024, 12, 1), date(2024, 12, 31)
        )
    finally:
        conn.close()
    assert in_jan.n_cleared == 1
    assert in_jan.identity_holds
    assert in_dec.n_credits == 0
    assert in_dec.n_cleared == 0
    assert in_dec.identity_holds


def test_accounts_are_isolated(tmp_path):
    db = tmp_path / "l.sqlite"
    init_db(db)
    conn = sqlite3.connect(str(db))
    conn.close()
    a = _credit("c_a", 1_000, date(2025, 1, 9), account="acc_01")
    b = _credit("c_b", 9_000, date(2025, 1, 9), account="acc_02")
    conn = open_readonly(db)
    try:
        reports = check_books(conn, (a, b), {})
    finally:
        conn.close()
    by = {r.account_id: r for r in reports}
    assert by["acc_01"].credits_paise == 1_000
    assert by["acc_02"].credits_paise == 9_000
    assert all(r.identity_holds for r in reports)
