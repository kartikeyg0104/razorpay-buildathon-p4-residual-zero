"""Razorpay adapter: no write capability, disable is a no-op, duplicate webhook is idempotent."""

from __future__ import annotations

from datetime import date

from residual_zero.ingest.razorpay import RazorpayTestModeAdapter


def test_adapter_holds_no_write_capability():
    names = [n for n in dir(RazorpayTestModeAdapter) if not n.startswith("_")]
    assert "create" not in names
    assert "refund" not in names
    assert "capture" not in names
    assert "post" not in names


def test_disabling_razorpay_changes_nothing():
    off = RazorpayTestModeAdapter("k", "s", enabled=False)
    assert off.fetch_credits((date(2025, 1, 1), date(2025, 1, 31))) == ()
    assert off.fetch_items((date(2025, 1, 1), date(2025, 1, 31))) == ()


def test_parse_recon_combined_sample_file():
    from pathlib import Path
    import json

    from residual_zero.ingest.razorpay import parse_recon_combined

    path = Path("fixtures").joinpath("recon", "combined_sample.json")
    rows = parse_recon_combined(json.loads(path.read_text(encoding="utf-8")))
    assert len(rows) == 3
    assert {r.kind.value for r in rows} == {"PAYMENT", "FEE", "TAX_GST"}


def test_parse_mcp_fetch_settlement_recon_details_envelope():
    from pathlib import Path
    import json

    from residual_zero.ingest.razorpay import parse_recon_combined

    path = Path("fixtures").joinpath("recon", "mcp_fetch_settlement_recon_details.json")
    rows = parse_recon_combined(json.loads(path.read_text(encoding="utf-8")))
    assert len(rows) == 3
    assert rows[0].settlement_id == "setl_sample_01"


def test_mcp_capture_payment_is_rejected():
    from residual_zero.ingest.razorpay import parse_recon_combined

    try:
        parse_recon_combined({"tool": "capture_payment", "items": []})
    except ValueError as exc:
        assert "capture_payment" in str(exc)
        assert "fetch_settlement_recon_details" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_mcp_settlement_list_is_rejected():
    from residual_zero.ingest.razorpay import parse_recon_combined

    try:
        parse_recon_combined(
            {
                "entity": "collection",
                "items": [{"id": "setl_1", "entity": "settlement", "amount": 100}],
            }
        )
    except ValueError as exc:
        assert "fetch_settlement_recon_details" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_duplicate_webhook_is_idempotent():
    adapter = RazorpayTestModeAdapter("k", "s", enabled=True)
    event = {"event_id": "evt_1", "payload": {}}
    a = adapter.normalise_webhook(event)
    b = adapter.normalise_webhook(event)
    assert a[0] == b[0]
    assert b[1] is None
