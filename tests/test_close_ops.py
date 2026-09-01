"""Close pack: bidirectional unmatched, tax mismatch, SLA, four-way, Tally. Never writes CLEARED."""

from __future__ import annotations

from datetime import date, datetime, timezone

from residual_zero.console.close_ops import (
    autonomy_rungs,
    build_close_pack,
    causal_chain,
    corpus_as_of,
    four_way_identity,
    is_tax_mismatch,
    sla_age_days,
    sla_bucket_name,
    tax_mismatch_rows,
)
from residual_zero.console.ops import GateA, Overlay
from residual_zero.ingest.settlement_report import DeclaredLine
from residual_zero.journal import build_journal, load_chart, render_tally_xml, trial_balance
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.money import format_rupees

_AWARE = datetime(2025, 1, 9, 6, 0, tzinfo=timezone.utc)


def _credit(cid: str, paise: int, day: date, utr: str | None = "UTR1") -> BankCredit:
    return BankCredit(
        id=cid,
        amount_paise=paise,
        value_date=day,
        account_id="acc_01",
        currency="INR",
        narration_raw="NEFT",
        narration_norm="neft",
        utr=utr,
    )


def _item(iid: str, kind: Kind, paise: int) -> LedgerItem:
    return LedgerItem(
        id=iid,
        kind=kind,
        amount_paise=paise,
        occurred_at=_AWARE,
        account_id="acc_01",
        currency="INR",
        instrument=Instrument.UPI,
        narration_raw=iid,
        narration_norm=iid,
        source=Source.INTERNAL_LEDGER,
    )


def _decl(cid: str, iid: str, kind: Kind, paise: int) -> DeclaredLine:
    return DeclaredLine(cid, iid, kind, paise, Instrument.UPI, None)


def _gate(cid: str, *, ok: bool, residual: int, n_deltas: int, members: tuple[str, ...] = ()) -> GateA:
    return GateA(
        credit_id=cid,
        member_ids=members,
        residual_paise=residual,
        computed_total_paise=0,
        posted_sum_paise=0,
        ok=ok,
        n_deltas=n_deltas,
    )


def _overlay(by_id: dict[str, GateA], journalable: dict[str, tuple[str, ...]] | None = None) -> Overlay:
    return Overlay(
        by_id=by_id,
        n_ok=sum(1 for g in by_id.values() if g.ok),
        n_residual_zero=sum(1 for g in by_id.values() if g.residual_paise == 0),
        n_declared=len(by_id),
        n_journalable=len(journalable or {}),
        journalable=journalable or {},
        double_claimed=(),
        n_mismatch=0,
    )


def test_bidirectional_unmatched_and_tax_never_unique():
    c_ok = _credit("c_ok", 90_000, date(2025, 1, 20))
    c_bare = _credit("c_bare", 10_000, date(2025, 1, 18), utr=None)
    c_tax = _credit("c_tax", 50_000, date(2025, 1, 1))
    pay = _item("p", Kind.PAYMENT, 100_000)
    fee = _item("f", Kind.FEE, -8_000)
    gst = _item("g", Kind.TAX_GST, -2_000)
    orphan = _item("orphan", Kind.PAYMENT, 5_000)
    by_credit = {
        "c_ok": (_decl("c_ok", "p", Kind.PAYMENT, 100_000), _decl("c_ok", "f", Kind.FEE, -8_000)),
        "c_bare": (),
        "c_tax": (_decl("c_tax", "p", Kind.PAYMENT, 100_000), _decl("c_tax", "g", Kind.TAX_GST, -1_000)),
    }
    overlay = _overlay(
        {
            "c_ok": _gate("c_ok", ok=True, residual=0, n_deltas=0, members=("p", "f")),
            "c_tax": _gate("c_tax", ok=False, residual=100, n_deltas=1, members=("p", "g")),
        },
        journalable={"c_ok": ("p", "f")},
    )
    audits = {"c_tax": {"uniqueness": "UNIQUE"}}
    pack = build_close_pack(
        (c_ok, c_bare, c_tax),
        {"p": pay, "f": fee, "g": gst, "orphan": orphan},
        by_credit,
        overlay,
        audits,
        books_hold=True,
        journal_balanced=True,
        control_ok=True,
        chain_ok=True,
        n_auto_cleared=0,
    )
    assert pack.writes_cleared is False
    assert pack.n_bank_uncovered == 2
    ids = {row["transaction_id"] for row in pack.bank_uncovered}
    assert ids == {"c_bare", "c_tax"}
    assert pack.n_ledger_orphans == 1
    assert pack.ledger_orphans[0]["item_id"] == "orphan"
    tax = tax_mismatch_rows((c_ok, c_bare, c_tax), by_credit, overlay, audits)
    assert len(tax) == 1
    assert tax[0]["transaction_id"] == "c_tax"
    assert tax[0]["uniqueness"] != "UNIQUE"
    assert tax[0]["clears"] is False
    assert tax[0]["writes_cleared"] is False
    assert is_tax_mismatch(overlay.by_id["c_ok"], by_credit["c_ok"]) is False
    assert all(item["writes_cleared"] is False for item in pack.checklist)
    assert pack.n_human == 2


def test_aging_uses_corpus_max_date():
    credits = (
        _credit("a", 100, date(2025, 1, 20)),
        _credit("b", 100, date(2025, 1, 18)),
        _credit("c", 100, date(2025, 1, 10)),
        _credit("d", 100, date(2025, 1, 1)),
    )
    as_of = corpus_as_of(credits)
    assert as_of == date(2025, 1, 20)
    assert sla_age_days(date(2025, 1, 20), as_of) == 0
    assert sla_bucket_name(0) == "0-1"
    assert sla_bucket_name(2) == "2-7"
    assert sla_bucket_name(10) == "8-14"
    assert sla_bucket_name(19) == "15+"
    assert sla_age_days(date(2025, 1, 1), as_of) == 19


def test_four_way_is_evidence_not_a_clear():
    credit = _credit("c1", 90_000, date(2025, 1, 9))
    declared = (_decl("c1", "p", Kind.PAYMENT, 100_000),)
    ledger = {"p": _item("p", Kind.PAYMENT, 100_000)}
    ident = four_way_identity(credit, declared, ledger, 0)
    assert ident["n_hit"] == 4
    assert ident["clears"] is False
    assert ident["writes_cleared"] is False
    assert ident["residual_zero"] is True
    chain = causal_chain(
        (
            _decl("c1", "p", Kind.PAYMENT, 100_000),
            _decl("c1", "f", Kind.FEE, -8_000),
            _decl("c1", "g", Kind.TAX_GST, -1_440),
        )
    )
    assert chain[0] == "PAYMENT"
    assert "FEE" in chain
    assert "TAX_GST" in chain
    assert chain[-1] == "BANK_CREDIT"


def test_autonomy_rungs_auto_clear_zero():
    rungs = autonomy_rungs()
    assert [r["name"] for r in rungs] == ["NORMAL", "NO_MODEL", "NO_SEARCH", "READ_ONLY", "HALTED"]
    assert all(r["auto_clear"] == 0 for r in rungs)


def test_tally_xml_balances_and_names_the_reference():
    chart = load_chart()
    credit = _credit("c1", 90_000, date(2025, 1, 9))
    pay = _item("p", Kind.PAYMENT, 100_000)
    fee = _item("f", Kind.FEE, -10_000)
    lines = build_journal((credit,), {"p": pay, "f": fee}, {"c1": ("f", "p")}, chart)
    debit, cred = trial_balance(lines)
    assert debit == cred
    xml = render_tally_xml(lines)
    assert "<ENVELOPE>" in xml
    assert "<VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>" in xml
    assert "<REFERENCE>c1</REFERENCE>" in xml
    assert format_rupees(90_000).replace(",", "") in xml
    assert "/" not in xml.split("<?xml", 1)[0]


def test_close_ops_source_never_writes():
    from pathlib import Path

    src = Path("src").joinpath("residual_zero", "console", "close_ops.py").read_text(encoding="utf-8")
    assert "open_verify" not in src
    assert "INSERT" not in src
    assert "writes_cleared=False" in src
