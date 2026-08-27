"""F47: four deliveries, one ledger state."""

from __future__ import annotations

from pathlib import Path

from residual_zero.ingest.webhooks import WebhookEngine


def _payment(event_id: str = "evt_pay_1") -> dict:
    return {
        "event_id": event_id,
        "event": "payment.captured",
        "payload": {
            "id": "pay_1",
            "amount_paise": 10_000,
            "account_id": "acc_00",
            "currency": "INR",
            "narration_raw": "captured",
            "order_id": "ord_1",
        },
    }


def _refund(event_id: str = "evt_ref_1") -> dict:
    return {
        "event_id": event_id,
        "event": "refund.processed",
        "payload": {
            "id": "ref_1",
            "amount_paise": 2_000,
            "account_id": "acc_00",
            "currency": "INR",
            "narration_raw": "refund",
            "parent_id": "pay_1",
        },
    }


def _run(path: Path, mode: str) -> bytes:
    engine = WebhookEngine(path)
    try:
        pay, refund = _payment(), _refund()
        if mode == "normal":
            engine.deliver(pay)
            engine.deliver(refund)
        elif mode == "duplicated":
            engine.deliver(pay)
            engine.deliver(pay)
            engine.deliver(refund)
            engine.deliver(refund)
        elif mode == "reversed":
            engine.deliver(refund)
            engine.deliver(pay)
        elif mode == "replayed":
            engine.deliver(pay)
            engine.deliver(refund)
            engine.replay()
        else:
            raise ValueError(mode)
        return engine.ledger_state()
    finally:
        engine.close()


def test_four_deliveries_identical_ledger_state(tmp_path: Path):
    states = []
    for i, mode in enumerate(("normal", "duplicated", "reversed", "replayed")):
        states.append(_run(tmp_path.joinpath(f"{mode}_{i}.sqlite"), mode))
    assert states[0] == states[1] == states[2] == states[3]
    assert b"pay_1" in states[0]
    assert b"ref_1" in states[0]
