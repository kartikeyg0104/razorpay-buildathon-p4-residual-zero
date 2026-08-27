"""Source adapter protocol. Razorpay is one implementation among CSV adapters."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from residual_zero.models import BankCredit, LedgerItem


class SourceAdapter(Protocol):
    def fetch_credits(self, window: tuple[date, date]) -> tuple[BankCredit, ...]: ...
    def fetch_items(self, window: tuple[date, date]) -> tuple[LedgerItem, ...]: ...
