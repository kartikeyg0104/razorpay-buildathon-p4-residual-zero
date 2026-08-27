"""Settlement-report CSV adapter. Declared composition, not a second item universe.

Each row names a ledger item id that already exists in the internal ledger. This adapter
does not emit ``LedgerItem``s — doing so would duplicate members and break conservation.
"""

from __future__ import annotations

import csv
from typing import NamedTuple

from residual_zero.models import Instrument, Kind
from residual_zero.normalise import parse_rupee_display

from . import IngestError
from .source_root import SourceRoot

SETTLEMENT_FIELDS = (
    "credit_id",
    "item_id",
    "kind",
    "amount",
    "instrument",
    "order_id",
)


class DeclaredLine(NamedTuple):
    credit_id: str
    item_id: str
    kind: Kind
    amount_paise: int
    instrument: Instrument | None
    order_id: str | None


def load_settlement_report(
    root: SourceRoot, relative_name: str = "settlement.csv",
) -> tuple[DeclaredLine, ...]:
    """Load the declared composition, or raise. An empty file is legal (all Regime B)."""
    try:
        handle = root.open(relative_name)
    except FileNotFoundError as exc:
        raise IngestError(str(exc), path=relative_name, line=None) from exc
    lines: list[DeclaredLine] = []
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise IngestError("missing header", path=relative_name, line=1)
        missing = [f for f in SETTLEMENT_FIELDS if f not in reader.fieldnames]
        if missing:
            raise IngestError(f"missing column(s) {missing}", path=relative_name, line=1)
        for line_no, raw in enumerate(reader, start=2):
            try:
                instrument_raw = (raw.get("instrument") or "").strip()
                order_id = (raw.get("order_id") or "").strip()
                lines.append(
                    DeclaredLine(
                        credit_id=raw["credit_id"].strip(),
                        item_id=raw["item_id"].strip(),
                        kind=Kind(raw["kind"].strip()),
                        amount_paise=parse_rupee_display(raw["amount"]),
                        instrument=Instrument(instrument_raw) if instrument_raw else None,
                        order_id=order_id or None,
                    )
                )
            except Exception as exc:
                raise IngestError(str(exc), path=relative_name, line=line_no) from exc
    return tuple(lines)
