"""Console views, waterfall, least privilege."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from residual_zero.config import config_digest, load_fees, load_tax_rates
from residual_zero.console.app import audit, batch, credit_view, explorer, exceptions as exceptions_view
from residual_zero.console.waterfall import waterfall_svg
from residual_zero.models import BankCredit, PoolScope, ProofLine, ProofRecord, Regime, Uniqueness
from residual_zero.normalise import normalise_narration


def test_all_four_views_render():
    assert b"batch" in batch().body
    assert b"queue" in exceptions_view().body
    assert b"audit" in audit().body
    assert credit_view("crd_missing").status_code == 200
    expl = explorer()
    assert expl.status_code == 200
    assert b"explorer" in expl.body
    assert b"does not write CLEARED" in expl.body
    body = batch().body
    assert b"guesses refused" in body
    assert b"the product" in body
    assert b"does not write CLEARED" in body
    assert b"148/239" in body
    assert b"159/239" in body
    assert b"1,44,25,758.19" in body
    assert b"residual-zero" in body
    assert b"settlement-linked" in body
    assert b"search completed" in body
    assert b"Track 04" in body
    assert b"refuse-all" in body
    # Assert the queue's capabilities via stable markers (counts, hrefs, class names)
    # rather than user-facing prose, which gets reworded (test rot, 2026-09).
    q = exceptions_view().body
    ql = q.lower()
    assert b"human review" in ql or b"need a human" in ql
    assert b'href="/exceptions.csv"' in q
    assert b"playbook" in ql
    assert b'href="/credit/' in q      # the queue links each exception to its credit
    assert b'class="pill' in q         # and renders its exception class


def test_waterfall_lines_sum_to_zero_residual():
    rates, fees = load_tax_rates(), load_fees()
    credit = BankCredit(
        id="c1", amount_paise=10000, value_date=date(2025, 1, 15),
        account_id="acc_00", currency="INR", narration_raw="NEFT",
        narration_norm=normalise_narration("NEFT"), utr="U",
    )
    proof = ProofRecord(
        bank_credit_id="c1",
        lines=(
            ProofLine(label="PAYMENT", detail="p1", amount_paise=10000, member_ids=("p1",), derived_from="LEDGER"),
        ),
        computed_total_paise=10000,
        residual_paise=0,
        regime=Regime.B_SEARCHED,
        uniqueness=Uniqueness.UNIQUE,
        alternate_count=1,
        pool_size=1,
        pool_scope=PoolScope.FULL,
        rate_config_digest=config_digest(rates, fees),
    )
    svg = waterfall_svg(proof, credit)
    assert 'data-residual="0"' in svg
    assert sum(line.amount_paise for line in proof.lines) + proof.residual_paise == credit.amount_paise


def test_console_cannot_write_ledger():
    src = Path("src/residual_zero/console/app.py").read_text(encoding="utf-8")
    assert "open_verify" not in src
    assert "write_cleared" not in src
    assert "open_exceptions" in src


def test_batch_template_does_not_hardcode_official_cards():
    src = Path("src/residual_zero/console/templates/batch.html").read_text(encoding="utf-8")
    assert "521/800" not in src
    assert "464/800" not in src
    assert "142/239" not in src
    assert "t04_test.residual_zero" in src
    assert "t04_dev.verified_linked" in src
    from residual_zero.console.app import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/alts" in paths
    assert "/human" in paths
    assert "/recon" in paths
    assert "/credit/{credit_id}" in paths
    assert "/extension" in paths
    assert "/api/desk" in paths
    assert "/api/mcp/tool" in paths
    assert "/api/mcp/tools" in paths
    assert "/api/ask" in paths
    assert "/explorer" in paths
    assert "/mcp" in paths
    assert "/mixed" in paths
    assert "/proof/{credit_id}" in paths
    assert "/api/finance/proof" in paths
    assert "/api/t04" in paths
    assert "/demo" in paths
    assert "/close" in paths
    assert "/api/close" in paths
    assert "/journal.tally" in paths
    assert "/close.md" in paths
    assert "/certificate" in paths
    assert "/metrics" in paths
    assert "/exceptions.csv" in paths
    assert "/exceptions/{credit_id}/work" in paths
    assert "/health" in paths
    assert "/api/health" in paths
    assert "/api/ops" in paths
    assert "/standup.md" in paths
    assert "/close.zip" in paths


def test_alts_and_human_and_recon_render():
    from residual_zero.console.app import app

    alts = next(r for r in app.routes if getattr(r, "path", "") == "/alts")
    human = next(r for r in app.routes if getattr(r, "path", "") == "/human")
    recon = next(r for r in app.routes if getattr(r, "path", "") == "/recon" and "GET" in getattr(r, "methods", set()))
    assert b"fixture" in alts.endpoint().body
    assert b"F56" in human.endpoint().body or b"human" in human.endpoint().body
    assert recon.endpoint().status_code == 200
    body = recon.endpoint().body
    assert b"fetch_all_instant_settlements" in body
    assert b"settlement_id" in body
    assert b"does not write" in body or b"Nothing is written" in body
    assert b"CLEARED 0" in body
    demo = credit_view("crd_001_acc_01_2025-01-09")
    assert demo.status_code == 200
    # The settlement-data fold links to the recon tool. The heading text was reworded from
    # "MCP recon" to "Settlement data"; the link is the stable marker for the capability.
    assert b'href="/recon"' in demo.body
    assert b"fetch_settlement_recon_details" in demo.body
    assert b"CLEARED" in demo.body
    assert b"why this did not reconcile" in demo.body.lower()
    assert b"auto-clear blocked" in demo.body.lower()   # was "why this did not auto-clear"
    assert b"four-way identity" in demo.body.lower()
    assert b"causal chain" in demo.body
    assert b"three-way comparison" in demo.body.lower()  # was "three-way desk"
    assert b"dispute draft" in demo.body
    assert b"playbook" in demo.body
    assert b"queue work" in demo.body
    assert b"AUTO-CLEAR DECISION" in demo.body
    assert b"not the decision maker" in demo.body.lower()
    batch_body = batch().body
    # The batch page must keep residual-zero / verified-linked / UNIQUE / CLEARED as four
    # distinct predicates. The prose became a numbered stage list; assert the claim, not
    # the sentence (test rot, 2026-09).
    assert b"not a clear" in batch_body.lower()
    assert b"proves the equation" in batch_body.lower()
    assert b"overlay does not write cleared" in batch_body.lower()
    from residual_zero.console.app import app

    demo_page = next(r for r in app.routes if getattr(r, "path", "") == "/demo")
    # The demo page is the guided walkthrough and must reach the mixed uniqueness desk.
    # "golden path" / "Mixed uniqueness lab" were reworded to "uniqueness testing"
    # (test rot, 2026-09); the link is the stable marker for the capability.
    demo_body = demo_page.endpoint().body
    assert b'href="/mixed"' in demo_body
    assert b"uniqueness testing" in demo_body.lower()


def test_close_desk_and_tally_render():
    from residual_zero.console.app import app

    close = next(r for r in app.routes if getattr(r, "path", "") == "/close")
    body = close.endpoint().body
    assert close.endpoint().status_code == 200
    assert b"does not write CLEARED" in body
    # Case-insensitive: the heading is rendered "Month-End Close" (test rot, 2026-09).
    assert b"month-end" in body.lower()
    assert b"bank uncovered" in body
    assert b"cash bridge" in body
    assert b"tax reconciliation" in body.lower()   # was "tax radar" (test rot, 2026-09)
    assert b"batch certificate" in body
    assert b"plugged" in body.lower()              # cash bridge states its plug flag
    assert b"exposure" in body
    assert b"standup.md" in body
    standup = next(r for r in app.routes if getattr(r, "path", "") == "/standup.md")
    sbody = standup.endpoint().body
    assert b"writes_cleared: false" in sbody
    zipped = next(r for r in app.routes if getattr(r, "path", "") == "/close.zip")
    zresp = zipped.endpoint()
    assert zresp.status_code == 200
    assert zresp.body[:2] == b"PK"
    api = next(r for r in app.routes if getattr(r, "path", "") == "/api/close")
    payload = api.endpoint().body
    assert b"writes_cleared" in payload
    assert b"true" not in payload.lower().split(b"writes_cleared")[1][:40]
    md = next(r for r in app.routes if getattr(r, "path", "") == "/close.md")
    assert b"writes_cleared: false" in md.endpoint().body
    cert = next(r for r in app.routes if getattr(r, "path", "") == "/certificate")
    blob = cert.endpoint().body
    assert b"sha256" in blob
    assert b"writes_cleared" in blob
    metrics = next(r for r in app.routes if getattr(r, "path", "") == "/metrics")
    text = metrics.endpoint().body
    assert b"rz_writes_cleared 0" in text
    csv = next(r for r in app.routes if getattr(r, "path", "") == "/exceptions.csv")
    assert b"writes_cleared" in csv.endpoint().body
    health = next(r for r in app.routes if getattr(r, "path", "") == "/api/health")
    hbody = health.endpoint().body
    assert b"writes_cleared" in hbody
    assert b"true" not in hbody.lower().split(b"writes_cleared")[1][:40]
    ops = next(r for r in app.routes if getattr(r, "path", "") == "/api/ops")
    obody = ops.endpoint().body
    assert b"bridge" in obody
    assert b"radar" in obody
    assert b"plugged" in obody
    whatif = next(r for r in app.routes if getattr(r, "path", "") == "/whatif")
    wbody = whatif.endpoint(credit_id="crd_001_acc_01_2025-01-09", reserve_bps=-1).body
    assert b"Monte-Carlo" in wbody or b"monte" in wbody.lower()
    tally = next(r for r in app.routes if getattr(r, "path", "") == "/journal.tally")
    xml = tally.endpoint()
    assert xml.status_code == 200
    assert b"<ENVELOPE>" in xml.body
    expl = explorer("TAX_MISMATCH")
    assert expl.status_code == 200
    assert b"tax mismatch" in expl.body
    amb = explorer("AMBIGUOUS")
    assert amb.status_code == 200
    un = explorer("UNRESOLVED")
    assert un.status_code == 200
    # Over real HTTP: the write routes now take a Request for the origin guard, so calling
    # the endpoint function directly no longer matches how a browser reaches it.
    from fastapi.testclient import TestClient

    blocked = TestClient(app).post(
        "/exceptions/crd_x/work?status=cleared",
        headers={"Origin": "http://127.0.0.1:8765",
                 "Content-Type": "application/x-www-form-urlencoded"},
        content="",
    )
    assert blocked.status_code == 400
    assert "CLEARED" in blocked.text



def test_ask_overlay_stays_flagged():
    from residual_zero.console.app import app

    src = Path("src/residual_zero/console/extra.py").read_text(encoding="utf-8")
    assert '"GATE_A"' not in src
    ask = next(r for r in app.routes if getattr(r, "path", "") == "/ask")
    body = ask.endpoint(
        question="why is crd_001_acc_01_2025-01-09 short",
        credit_id="crd_001_acc_01_2025-01-09",
    ).body
    assert b"disposition GATE_A" not in body
    assert b"does not write CLEARED" in body
    landing = ask.endpoint().body.lower()
    # The landing says the controller answers off a fitted corpus, not a live model.
    # Reworded from "fitted controller" to a "Controller" heading plus "fitted corpus".
    assert b"controller" in landing
    assert b"fitted" in landing
    assert b"does not write" in landing
    policy = ask.endpoint(question="why is search auto-clear 0").body
    assert b"does not write CLEARED" in policy


def test_evidence_names_the_holes():
    from residual_zero.console.app import app

    evidence = next(r for r in app.routes if getattr(r, "path", "") == "/evidence")
    body = evidence.endpoint().body
    assert b"501/800" in body
    assert b"800/800" in body
    assert b"3977/5973" in body
    assert b"refuse-all" in body
    assert b"does not write CLEARED" in body
