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


def test_duplicate_webhook_is_idempotent():
    adapter = RazorpayTestModeAdapter("k", "s", enabled=True)
    event = {"event_id": "evt_1", "payload": {}}
    a = adapter.normalise_webhook(event)
    b = adapter.normalise_webhook(event)
    assert a[0] == b[0]
    assert b[1] is None
