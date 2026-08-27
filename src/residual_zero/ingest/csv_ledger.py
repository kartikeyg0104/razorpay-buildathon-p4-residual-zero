"""Internal-ledger CSV adapter. Produces ``LedgerItem`` rows and nothing else."""

from __future__ import annotations

import csv
from datetime import datetime
from typing import Iterable

from residual_zero.models import Instrument, Kind, LedgerItem, Source
from residual_zero.normalise import normalise_narration, parse_rupee_display
from residual_zero.tz import IST, ensure_utc

from . import IngestError
from .source_root import SourceRoot

LEDGER_FIELDS = (
    "id",
    "kind",
    "amount",
    "occurred_at",
    "account_id",
    "currency",
    "instrument",
    "order_id",
    "parent_id",
    "narration_raw",
    "counterparty_raw",
    "source",
)


def load_ledger_items(root: SourceRoot, relative_name: str = "ledger.csv") -> tuple[LedgerItem, ...]:
    """Load every ledger item, or raise. Never returns a prefix of the file."""
    rows: list[LedgerItem] = []
    try:
        handle = root.open(relative_name)
    except FileNotFoundError as exc:
        raise IngestError(str(exc), path=relative_name, line=None) from exc
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise IngestError("missing header", path=relative_name, line=1)
        missing = [f for f in LEDGER_FIELDS if f not in reader.fieldnames]
        if missing:
            raise IngestError(f"missing column(s) {missing}", path=relative_name, line=1)
        for line_no, raw in enumerate(reader, start=2):
            try:
                rows.append(_row_to_item(raw))
            except Exception as exc:
                raise IngestError(str(exc), path=relative_name, line=line_no) from exc
    return tuple(rows)


def _row_to_item(raw: dict[str, str]) -> LedgerItem:
    instrument_raw = (raw.get("instrument") or "").strip()
    order_id = (raw.get("order_id") or "").strip()
    parent_id = (raw.get("parent_id") or "").strip()
    counterparty = (raw.get("counterparty_raw") or "").strip()
    source_raw = (raw.get("source") or "INTERNAL_LEDGER").strip()
    narration = raw["narration_raw"]
    return LedgerItem(
        id=raw["id"].strip(),
        kind=Kind(raw["kind"].strip()),
        amount_paise=parse_rupee_display(raw["amount"]),
        occurred_at=_parse_occurred_at(raw["occurred_at"]),
        account_id=raw["account_id"].strip(),
        currency=raw["currency"].strip(),
        instrument=Instrument(instrument_raw) if instrument_raw else None,
        order_id=order_id or None,
        parent_id=parent_id or None,
        narration_raw=narration,
        narration_norm=normalise_narration(narration),
        counterparty_raw=counterparty or None,
        counterparty_id=None,
        source=Source(source_raw) if source_raw else Source.INTERNAL_LEDGER,
    )


def _parse_occurred_at(text: str) -> datetime:
    raw = text.strip()
    if raw.endswith(" IST"):
        raw = raw[: -len(" IST")]
        naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        return ensure_utc(naive.replace(tzinfo=IST))
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return ensure_utc(datetime.fromisoformat(raw))


def items_from_rows(rows: Iterable[dict[str, str]]) -> tuple[LedgerItem, ...]:
    return tuple(_row_to_item(r) for r in rows)
