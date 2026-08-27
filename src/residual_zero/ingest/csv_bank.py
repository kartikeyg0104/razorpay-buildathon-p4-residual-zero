"""Bank-statement CSV adapter. Produces ``BankCredit`` rows and nothing else."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Iterable

from residual_zero.models import BankCredit
from residual_zero.normalise import normalise_narration, parse_rupee_display

from . import IngestError
from .guard import reject_malformed_text
from .source_root import SourceRoot

BANK_FIELDS = (
    "id",
    "amount",
    "value_date",
    "account_id",
    "currency",
    "narration_raw",
    "utr",
)


def load_bank_credits(root: SourceRoot, relative_name: str = "bank.csv") -> tuple[BankCredit, ...]:
    """Load every bank credit, or raise. Never returns a prefix of the file."""
    rows: list[BankCredit] = []
    try:
        handle = root.open(relative_name)
    except FileNotFoundError as exc:
        raise IngestError(str(exc), path=relative_name, line=None) from exc
    with handle:
        text = handle.read()
        reject_malformed_text(text, path=relative_name)
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise IngestError("missing header", path=relative_name, line=1)
        missing = [f for f in BANK_FIELDS if f not in reader.fieldnames]
        if missing:
            raise IngestError(
                f"missing column(s) {missing}", path=relative_name, line=1,
            )
        for line_no, raw in enumerate(reader, start=2):
            try:
                rows.append(_row_to_credit(raw))
            except Exception as exc:
                raise IngestError(str(exc), path=relative_name, line=line_no) from exc
    return tuple(rows)


def _row_to_credit(raw: dict[str, str]) -> BankCredit:
    utr = (raw.get("utr") or "").strip()
    narration = raw["narration_raw"]
    return BankCredit(
        id=raw["id"].strip(),
        amount_paise=parse_rupee_display(raw["amount"]),
        value_date=_parse_iso_date(raw["value_date"]),
        account_id=raw["account_id"].strip(),
        currency=raw["currency"].strip(),
        narration_raw=narration,
        narration_norm=normalise_narration(narration),
        utr=utr or None,
    )


def _parse_iso_date(text: str) -> date:
    return date.fromisoformat(text.strip())


def credits_from_rows(rows: Iterable[dict[str, str]]) -> tuple[BankCredit, ...]:
    """Used by tests that already have dict rows and do not want a filesystem."""
    return tuple(_row_to_credit(r) for r in rows)
