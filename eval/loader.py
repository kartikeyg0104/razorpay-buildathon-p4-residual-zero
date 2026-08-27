"""System-side loader. Restricted to rendered views via SourceRoot (NN-6)."""

from __future__ import annotations

from pathlib import Path

from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import BankCredit, LedgerItem


def load_split(split: str, data_root: Path = Path("data")) -> tuple[tuple[LedgerItem, ...], tuple[BankCredit, ...]]:
    """Load rendered views for a split through a SourceRoot. Cannot reach the answer-key file."""
    root = SourceRoot(data_root.joinpath(split, "rendered"))
    items = load_ledger_items(root)
    credits = load_bank_credits(root)
    return items, credits
