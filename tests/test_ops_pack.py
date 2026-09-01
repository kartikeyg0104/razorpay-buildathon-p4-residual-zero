"""Second-wave ops pack: cash bridge, tax radar, certificate, playbooks. Never writes CLEARED."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from residual_zero.config import load_fees, load_tax_rates
from residual_zero.console.ops import GateA, Overlay
from residual_zero.console.ops_pack import (
    amount_twin_rows,
    batch_certificate,
    cash_bridge,
    close_bundle_zip,
    close_markdown,
    dispute_draft,
    duplicate_utr_rows,
    exceptions_csv,
    exposure_queue,
    four_way_gaps,
    normalise_work_status,
    playbook_for,
    prometheus_text,
    standup_markdown,
    tax_radar,
    three_way,
    utr_siblings,
)
from residual_zero.ingest.settlement_report import DeclaredLine
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.money import apply_bps, format_rupees

_AWARE = datetime(2025, 1, 9, 6, 0, tzinfo=timezone.utc)


def _credit(cid: str, paise: int, utr: str | None = "UTR99") -> BankCredit:
    return BankCredit(
        id=cid,
        amount_paise=paise,
        value_date=date(2025, 1, 9),
        account_id="acc_01",
        currency="INR",
        narration_raw="NEFT RAZORPAY SETTLEMENT acc_01 2025-01-09",
        narration_norm="neft razorpay settlement acc_01 2025-01-09",
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


def _overlay(journalable: dict[str, tuple[str, ...]] | None = None) -> Overlay:
    by_id = {
        "c1": GateA(
            credit_id="c1",
            member_ids=("p",),
            residual_paise=0,
            computed_total_paise=90_000,
            posted_sum_paise=90_000,
            ok=True,
            n_deltas=0,
        )
    }
    return Overlay(
        by_id=by_id,
        n_ok=1,
        n_residual_zero=1,
        n_declared=1,
        n_journalable=len(journalable or {}),
        journalable=journalable or {},
        double_claimed=(),
        n_mismatch=0,
    )


def test_cash_bridge_residual_stays_unplugged():
    credits = (_credit("c1", 90_000),)
    pay = _item("p", Kind.PAYMENT, 100_000)
    fee = _item("f", Kind.FEE, -10_000)
    bridge = cash_bridge(credits, {"p": pay, "f": fee}, _overlay({"c1": ("p",)}))
    assert bridge["plugged"] is False
    assert bridge["writes_cleared"] is False
    assert bridge["bank_landed_paise"] == 90_000
    assert bridge["ledger_total_paise"] == 90_000
    assert bridge["residual_paise"] == 0
    assert bridge["journalable_paise"] == 90_000
    assert bridge["unreconciled_paise"] == 0
    bare = cash_bridge(credits, {"p": pay, "f": fee}, _overlay())
    assert bare["unreconciled_paise"] == 90_000
    assert bare["plugged"] is False


def test_tax_radar_is_rate_table_not_gstn():
    rates, fees = load_tax_rates(), load_fees()
    gross = 100_000
    fee = -apply_bps(gross, fees.per_instrument_bps[Instrument.UPI].bps)
    gst = apply_bps(fee, rates.gst_on_fee.bps)
    tds = -apply_bps(gross, rates.withholding.bps)
    ledger = {
        "p": _item("p", Kind.PAYMENT, gross),
        "f": _item("f", Kind.FEE, fee),
        "g": _item("g", Kind.TAX_GST, gst),
        "t": _item("t", Kind.TAX_WITHHOLDING, tds),
    }
    radar = tax_radar(ledger, rates, fees)
    assert radar["not_form_26as"] is True
    assert radar["gst_on_fee_not_gross"] is True
    assert radar["writes_cleared"] is False
    assert radar["gst_delta_display"] == format_rupees(0)
    assert radar["tds_delta_display"] == format_rupees(0)
    assert radar["fee_delta_display"] == format_rupees(0)
    wrong = dict(ledger)
    wrong["g"] = _item("g", Kind.TAX_GST, gst + 1)
    delta = tax_radar(wrong, rates, fees)
    assert delta["gst_delta_display"] == format_rupees(1)


def test_three_way_and_dispute_are_evidence():
    credit = _credit("c1", 90_000)
    declared = (
        DeclaredLine("c1", "p", Kind.PAYMENT, 100_000, Instrument.UPI, None),
        DeclaredLine("c1", "missing", Kind.FEE, -2_000, Instrument.UPI, "ord_1"),
    )
    ledger = {"p": _item("p", Kind.PAYMENT, 100_000)}
    desk = three_way(credit, declared, ledger)
    assert desk["writes_cleared"] is False
    assert desk["n_settlement"] == 2
    assert desk["n_ledger_missing"] == 1
    assert desk["ledger"][1]["status"] == "MISSING"
    letter = dispute_draft(credit, "AMBIGUOUS", format_rupees(0), playbook_for("AMBIGUOUS"))
    assert "UTR99" in letter
    assert "does not write CLEARED" in letter or "Overlay does not write CLEARED" in letter
    assert "will not pick a subset" in letter


def test_certificate_and_prometheus_never_clear():
    cert = batch_certificate(
        audit_head="abc",
        n_credits=239,
        n_gate_a=142,
        n_journalable=136,
        n_unique=0,
        n_ambiguous=236,
        n_none_found=3,
        n_auto_cleared=0,
        chain_ok=True,
    )
    assert cert["writes_cleared"] is False
    assert len(cert["sha256"]) == 64
    assert cert["n_unique"] == 0
    text = prometheus_text(n_credits=239, n_gate_a=142, n_human=97, n_auto_cleared=0)
    assert "rz_writes_cleared 0" in text
    assert "rz_auto_clear 0" in text
    csv = exceptions_csv(
        [{"id": "c1", "account": "acc_01", "value_date": "2025-01-09", "amount": "1.00", "uniqueness": "AMBIGUOUS", "gate": "REFUSED", "cls": "AMBIGUOUS"}]
    )
    assert "false" in csv.splitlines()[1]
    assert "writes_cleared" in csv.splitlines()[0]


def test_work_status_rejects_cleared():
    assert normalise_work_status("investigating") == "investigating"
    with pytest.raises(ValueError):
        normalise_work_status("cleared")
    with pytest.raises(ValueError):
        normalise_work_status("CLEARED")


def test_playbook_covers_exception_classes():
    assert "does not write CLEARED" in playbook_for("AMBIGUOUS") or "Leave flagged" in playbook_for("AMBIGUOUS")
    assert "194-O" in playbook_for("SUSPECTED_WITHHOLDING")


def test_close_markdown_unplugged():
    class _Pack:
        as_of = "2025-01-09"
        n_bank_uncovered = 1
        n_ledger_orphans = 0
        n_tax_mismatch = 0
        n_human = 1

    md = close_markdown(
        _Pack(),
        {
            "ledger_total_display": "1.00",
            "bank_landed_display": "1.00",
            "residual_display": "0.00",
            "journalable_display": "0.00",
            "unreconciled_display": "1.00",
        },
        {
            "gst_posted_display": "0.00",
            "gst_expected_display": "0.00",
            "gst_delta_display": "0.00",
            "tds_posted_display": "0.00",
            "tds_expected_display": "0.00",
            "tds_delta_display": "0.00",
        },
        {"sha256": "deadbeef"},
    )
    assert "unplugged" in md
    assert "writes_cleared: false" in md
    assert "not GSTN" in md


def test_ops_pack_source_never_writes():
    src = Path("src").joinpath("residual_zero", "console", "ops_pack.py").read_text(encoding="utf-8")
    assert "open_verify" not in src
    assert "INSERT" not in src
    assert "CLEARED" in src


def _refused_overlay(*ids: str) -> Overlay:
    by_id = {
        cid: GateA(
            credit_id=cid,
            member_ids=(),
            residual_paise=1,
            computed_total_paise=0,
            posted_sum_paise=0,
            ok=False,
            n_deltas=0,
        )
        for cid in ids
    }
    return Overlay(
        by_id=by_id,
        n_ok=0,
        n_residual_zero=0,
        n_declared=len(by_id),
        n_journalable=0,
        journalable={},
        double_claimed=(),
        n_mismatch=0,
    )


def test_exposure_ranks_refused_not_a_match_score():
    heavy = _credit("c_heavy", 90_000)
    light = _credit("c_light", 1_000)
    overlay = _refused_overlay("c_heavy", "c_light")
    overlay.by_id["c_ok"] = GateA(
        credit_id="c_ok",
        member_ids=("p",),
        residual_paise=0,
        computed_total_paise=90_000,
        posted_sum_paise=90_000,
        ok=True,
        n_deltas=0,
    )
    got = exposure_queue((heavy, light, _credit("c_ok", 90_000)), overlay, date(2025, 1, 9), limit=8)
    assert got["writes_cleared"] is False
    assert got["n"] == 2
    assert got["rows"][0]["id"] == "c_heavy"
    assert got["rows"][0]["score"] == 90_000
    assert "/" not in str(got["rows"][0]["amount_display"]).replace(",", "")


def test_duplicate_utr_twins_and_siblings():
    a = _credit("c1", 10_000, "UTR-DUP")
    b = _credit("c2", 10_000, "UTR-DUP")
    c = BankCredit(
        id="c3",
        amount_paise=10_000,
        value_date=date(2025, 1, 10),
        account_id="acc_01",
        currency="INR",
        narration_raw="x",
        narration_norm="x",
        utr="UTR-OTHER",
    )
    dupes = duplicate_utr_rows((a, b, c))
    assert dupes["writes_cleared"] is False
    assert dupes["n"] == 1
    assert dupes["rows"][0]["n"] == 2
    twins = amount_twin_rows((a, b, c))
    assert twins["writes_cleared"] is False
    assert twins["n"] >= 1
    sib = utr_siblings((a, b, c), "c1")
    assert sib["n"] == 1
    assert sib["ids"] == ["c2"]
    assert sib["writes_cleared"] is False


def test_four_way_gaps_are_evidence():
    credit = _credit("c1", 90_000, None)
    gaps = four_way_gaps((credit,), {}, {}, None)
    assert gaps["writes_cleared"] is False
    assert gaps["missing_utr"] == 1
    assert gaps["n_full"] == 0


def test_standup_and_zip_never_clear():
    class _Pack:
        as_of = "2025-01-09"
        n_human = 2
        n_bank_uncovered = 1
        n_tax_mismatch = 0

    md = standup_markdown(
        _Pack(),
        {"residual_display": "0.00"},
        {"gst_delta_display": "0.00"},
        {"sha256": "abc"},
        {"rows": [{"id": "c1", "amount_display": "1.00", "age_days": 2}]},
        {"n": 0},
        {"n_full": 0, "n_credits": 1},
    )
    assert "writes_cleared: false" in md
    assert "does not write CLEARED" in md
    blob = close_bundle_zip(
        close_md="close",
        standup_md=md,
        cert={"sha256": "abc", "writes_cleared": False},
        exceptions_csv_text="id\n",
    )
    import io
    import zipfile

    archive = zipfile.ZipFile(io.BytesIO(blob))
    assert set(archive.namelist()) == {"close.md", "standup.md", "certificate.json", "exceptions.csv"}
    assert "writes_cleared: false" in archive.read("standup.md").decode("utf-8")
