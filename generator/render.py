"""Stage 4: emit the three source views. Dates in IST, amounts as rupee strings."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Sequence

from residual_zero.models import Regime
from residual_zero.money import format_rupees
from residual_zero.tz import iso_utc, to_ist_display

from .truth import TruthRecord, TruthSet

BANK_FIELDS = (
    "id",
    "amount",
    "value_date",
    "account_id",
    "currency",
    "narration_raw",
    "utr",
)
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
SETTLEMENT_FIELDS = (
    "credit_id",
    "item_id",
    "kind",
    "amount",
    "instrument",
    "order_id",
)


class RenderedViews(NamedTuple):
    bank_rows: tuple[dict[str, str], ...]
    ledger_rows: tuple[dict[str, str], ...]
    settlement_rows: tuple[dict[str, str], ...]


class SplitManifest(NamedTuple):
    split: str
    seeds: tuple[int, ...]
    n_credits: int
    n_items: int
    n_records: int
    n_ledger_rows: int
    profile_name: str
    generated_at: str


def render(truth: TruthSet) -> RenderedViews:
    """Emit the three source views, dates in IST, amounts as rupee strings, before corruption."""
    items_by_id = {item.id: item for item in truth.items}
    bank_rows = []
    for credit in sorted(truth.credits, key=lambda c: (c.value_date, c.id)):
        bank_rows.append(
            {
                "id": credit.id,
                "amount": format_rupees(credit.amount_paise),
                "value_date": credit.value_date.isoformat(),
                "account_id": credit.account_id,
                "currency": credit.currency,
                "narration_raw": credit.narration_raw,
                "utr": credit.utr or "",
            }
        )
    ledger_rows = []
    for item in sorted(truth.items, key=lambda i: (i.occurred_at, i.id)):
        ledger_rows.append(
            {
                "id": item.id,
                "kind": item.kind.value,
                "amount": format_rupees(item.amount_paise),
                "occurred_at": to_ist_display(item.occurred_at),
                "account_id": item.account_id,
                "currency": item.currency,
                "instrument": item.instrument.value if item.instrument else "",
                "order_id": item.order_id or "",
                "parent_id": item.parent_id or "",
                "narration_raw": item.narration_raw,
                "counterparty_raw": item.counterparty_raw or "",
                "source": item.source.value,
            }
        )
    record_by_credit = {r.bank_credit_id: r for r in truth.records}
    settlement_rows = []
    for credit in sorted(truth.credits, key=lambda c: (c.value_date, c.id)):
        record = record_by_credit[credit.id]
        if record.regime != Regime.A_DECLARED:
            continue
        for member_id in record.member_ids:
            item = items_by_id[member_id]
            settlement_rows.append(
                {
                    "credit_id": credit.id,
                    "item_id": item.id,
                    "kind": item.kind.value,
                    "amount": format_rupees(item.amount_paise),
                    "instrument": item.instrument.value if item.instrument else "",
                    "order_id": item.order_id or "",
                }
            )
    return RenderedViews(
        bank_rows=tuple(bank_rows),
        ledger_rows=tuple(ledger_rows),
        settlement_rows=tuple(settlement_rows),
    )


def write_split(
    split: str,
    views: RenderedViews,
    records: Sequence[TruthRecord],
    out_root: Path,
    *,
    seeds: tuple[int, ...] = (),
    n_items: int = 0,
    profile_name: str = "",
) -> SplitManifest:
    """Write data/{split}/rendered/*.csv and data/{split}/truth.jsonl. Two different roots."""
    split_dir = out_root.joinpath(split)
    rendered = split_dir.joinpath("rendered")
    rendered.mkdir(parents=True, exist_ok=True)
    _write_csv(rendered.joinpath("bank.csv"), BANK_FIELDS, views.bank_rows)
    _write_csv(rendered.joinpath("ledger.csv"), LEDGER_FIELDS, views.ledger_rows)
    _write_csv(rendered.joinpath("settlement.csv"), SETTLEMENT_FIELDS, views.settlement_rows)
    truth_path = split_dir.joinpath("truth.jsonl")
    with truth_path.open("w", encoding="utf-8") as handle:
        for record in sorted(records, key=lambda r: r.bank_credit_id):
            handle.write(record.model_dump_json() + "\n")
    generated_at = iso_utc(datetime.now(timezone.utc))
    manifest = SplitManifest(
        split=split,
        seeds=seeds,
        n_credits=len(views.bank_rows),
        n_items=n_items,
        n_records=len(records),
        n_ledger_rows=len(views.ledger_rows),
        profile_name=profile_name,
        generated_at=generated_at,
    )
    manifest_path = split_dir.joinpath("manifest.json")
    manifest_path.write_text(
        json.dumps(
            {
                "split": manifest.split,
                "seeds": list(manifest.seeds),
                "n_credits": manifest.n_credits,
                "n_items": manifest.n_items,
                "n_records": manifest.n_records,
                "n_ledger_rows": manifest.n_ledger_rows,
                "profile_name": manifest.profile_name,
                "generated_at": manifest.generated_at,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def _write_csv(path: Path, fields: tuple[str, ...], rows: Sequence[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
