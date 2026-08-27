"""F47: webhook event store with idempotency, out-of-order buffer, and replay."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from residual_zero.canonical import canonical_json
from residual_zero.models import Instrument, Kind, LedgerItem, Source

SCHEMA = """
CREATE TABLE IF NOT EXISTS webhook_event (
    seq INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applied_item (
    item_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS buffer_event (
    event_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
"""


def _item_from_payload(payload: Mapping[str, Any]) -> LedgerItem | None:
    event = str(payload.get("event") or "")
    body = payload.get("payload")
    if not isinstance(body, dict):
        return None
    item_id = str(body.get("id") or "")
    amount = body.get("amount_paise")
    account_id = str(body.get("account_id") or "")
    if not item_id or not isinstance(amount, int) or amount == 0 or not account_id:
        return None
    if event == "payment.captured":
        kind = Kind.PAYMENT
        parent_id = None
        if amount < 0:
            return None
    elif event == "refund.processed":
        kind = Kind.REFUND
        parent_id = str(body.get("parent_id") or "") or None
        if parent_id is None:
            return None
        if amount > 0:
            amount = -amount
    else:
        return None
    occurred = body.get("occurred_at")
    if isinstance(occurred, str):
        at = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
    else:
        at = datetime(2025, 1, 9, 6, 0, tzinfo=timezone.utc)
    instrument_raw = body.get("instrument")
    instrument = Instrument(instrument_raw) if instrument_raw else Instrument.UPI
    narration = str(body.get("narration_raw") or kind.value)
    return LedgerItem(
        id=item_id,
        kind=kind,
        amount_paise=amount,
        occurred_at=at,
        account_id=account_id,
        currency=str(body.get("currency") or "INR"),
        instrument=instrument,
        order_id=str(body.get("order_id") or "") or None,
        parent_id=parent_id,
        narration_raw=narration,
        narration_norm=narration.lower(),
        source=Source.API,
    )


class WebhookEngine:
    """Persist every distinct event_id. Apply payments immediately; buffer refunds until parent exists."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def deliver(self, event: Mapping[str, Any]) -> None:
        event_id = str(event.get("event_id") or event.get("id") or "")
        if not event_id:
            raise ValueError("webhook missing event id")
        existing = self._conn.execute(
            "SELECT 1 FROM webhook_event WHERE event_id = ?", (event_id,)
        ).fetchone()
        if existing is not None:
            return
        blob = json.dumps(dict(event), sort_keys=True, separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO webhook_event (event_id, payload) VALUES (?, ?)",
            (event_id, blob),
        )
        self._conn.commit()
        self._try_apply(dict(event))

    def _applied_ids(self) -> set[str]:
        rows = self._conn.execute("SELECT item_id FROM applied_item").fetchall()
        return {str(r[0]) for r in rows}

    def _write_item(self, item: LedgerItem) -> None:
        dump = item.model_dump(mode="json")
        blob = json.dumps(dump, sort_keys=True, separators=(",", ":"))
        self._conn.execute(
            "INSERT OR REPLACE INTO applied_item (item_id, payload) VALUES (?, ?)",
            (item.id, blob),
        )
        self._conn.commit()

    def _try_apply(self, event: Mapping[str, Any]) -> None:
        item = _item_from_payload(event)
        if item is None:
            return
        applied = self._applied_ids()
        if item.kind == Kind.REFUND and item.parent_id is not None and item.parent_id not in applied:
            event_id = str(event.get("event_id") or "")
            blob = json.dumps(dict(event), sort_keys=True, separators=(",", ":"))
            self._conn.execute(
                "INSERT OR REPLACE INTO buffer_event (event_id, payload) VALUES (?, ?)",
                (event_id, blob),
            )
            self._conn.commit()
            return
        if item.id in applied:
            return
        self._write_item(item)
        self._flush_buffer()

    def _flush_buffer(self) -> None:
        rows = list(self._conn.execute("SELECT event_id, payload FROM buffer_event ORDER BY event_id"))
        applied = self._applied_ids()
        for event_id, payload_text in rows:
            event = json.loads(payload_text)
            item = _item_from_payload(event)
            if item is None:
                continue
            if item.kind == Kind.REFUND and item.parent_id is not None and item.parent_id not in applied:
                continue
            if item.id not in applied:
                self._write_item(item)
                applied.add(item.id)
            self._conn.execute("DELETE FROM buffer_event WHERE event_id = ?", (event_id,))
            self._conn.commit()

    def replay(self) -> None:
        """Wipe applied state and fold the stored log in seq order."""
        self._conn.execute("DELETE FROM applied_item")
        self._conn.execute("DELETE FROM buffer_event")
        self._conn.commit()
        rows = list(self._conn.execute("SELECT payload FROM webhook_event ORDER BY seq"))
        for (payload_text,) in rows:
            self._try_apply(json.loads(payload_text))

    def ledger_state(self) -> bytes:
        """Canonical snapshot of applied items. The F47 equality object."""
        rows = list(self._conn.execute("SELECT item_id, payload FROM applied_item ORDER BY item_id"))
        items = [json.loads(payload) for _item_id, payload in rows]
        return canonical_json({"items": items})
