"""Razorpay test-mode adapter. Read-only. Cuttable via config enabled: false."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from residual_zero.models import BankCredit, LedgerItem


class RazorpayTestModeAdapter:
    """Holds a read-only credential. Never writes anything anywhere."""

    def __init__(self, key_id: str, key_secret: str, enabled: bool) -> None:
        self.key_id = key_id
        self._secret = key_secret
        self.enabled = enabled
        self._seen_events: set[str] = set()

    def fetch_credits(self, window: tuple[date, date]) -> tuple[BankCredit, ...]:
        if not self.enabled:
            return ()
        return ()

    def fetch_items(self, window: tuple[date, date]) -> tuple[LedgerItem, ...]:
        if not self.enabled:
            return ()
        return ()

    def normalise_webhook(self, event: Mapping[str, Any]) -> tuple[str, LedgerItem | None]:
        event_id = str(event.get("event_id") or event.get("id") or "")
        if not event_id:
            raise ValueError("webhook missing event id")
        if event_id in self._seen_events:
            return event_id, None
        self._seen_events.add(event_id)
        return event_id, None
