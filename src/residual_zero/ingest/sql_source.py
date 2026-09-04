"""Read and write an organisation's source financial data in its own storage namespace.

The committed dev corpus is a set of CSV files, and it stays that way — the eval harness,
``make demo`` and every published number read it through :class:`SourceRoot`, and none of
that changes. What this module adds is the *other* way an organisation's data can arrive
once the product is deployed: rows in that organisation's own schema, reachable only by a
connection scoped to it.

Both paths produce identical canonical objects (``BankCredit``, ``LedgerItem``,
``DeclaredLine``), so everything downstream — candidate generation, the solver, the
verifier, the console — cannot tell them apart and does not need to.

No conversion happens to a money value anywhere in this file. ``amount_paise`` is read and
written as the integer it already is; there is no rupee parsing on the way in and no
formatting on the way out.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from residual_zero.ingest.settlement_report import DeclaredLine
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.normalise import normalise_narration

# SQLite equivalent of the source tables in migrations/org/0001_financial.sql. Applied on
# demand rather than folded into residual_zero.db.SCHEMA, so the shape of the committed
# artifacts/dev/ledger.sqlite is unchanged.
SQLITE_SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS bank_credit (
    credit_id TEXT PRIMARY KEY,
    amount_paise INTEGER NOT NULL,
    value_date TEXT NOT NULL,
    account_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    narration_raw TEXT NOT NULL,
    narration_norm TEXT NOT NULL,
    utr TEXT,
    ingested_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ledger_item (
    item_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    account_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    instrument TEXT,
    order_id TEXT,
    parent_id TEXT,
    narration_raw TEXT NOT NULL,
    narration_norm TEXT NOT NULL,
    counterparty_raw TEXT,
    counterparty_id TEXT,
    source TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settlement_line (
    credit_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    instrument TEXT,
    order_id TEXT,
    settlement_id TEXT,
    PRIMARY KEY (credit_id, item_id)
);
"""


def ensure_source_tables(conn) -> None:
    """Create the source tables when the backend is SQLite. No-op on Postgres."""
    from residual_zero.storage.config import Backend, storage_config

    if storage_config().backend is Backend.SQLITE:
        conn.executescript(SQLITE_SOURCE_SCHEMA)


# ---------------------------------------------------------------- reads


def _as_date(raw) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw)[:10])


def _as_datetime(raw) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    moment = datetime.fromisoformat(str(raw))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def load_bank_credits_sql(conn) -> tuple[BankCredit, ...]:
    """Every bank credit in this organisation, ordered so a run is reproducible."""
    rows = list(conn.execute(
        "SELECT credit_id, amount_paise, value_date, account_id, currency, "
        "narration_raw, narration_norm, utr FROM bank_credit ORDER BY credit_id"
    ))
    return tuple(
        BankCredit(
            id=str(r[0]),
            amount_paise=int(r[1]),
            value_date=_as_date(r[2]),
            account_id=str(r[3]),
            currency=str(r[4]).strip().upper(),
            narration_raw=str(r[5]),
            narration_norm=str(r[6]) or normalise_narration(str(r[5])),
            utr=str(r[7]) if r[7] else None,
        )
        for r in rows
    )


def load_ledger_items_sql(conn) -> tuple[LedgerItem, ...]:
    rows = list(conn.execute(
        "SELECT item_id, kind, amount_paise, occurred_at, account_id, currency, instrument, "
        "order_id, parent_id, narration_raw, narration_norm, counterparty_raw, "
        "counterparty_id, source FROM ledger_item ORDER BY item_id"
    ))
    return tuple(
        LedgerItem(
            id=str(r[0]),
            kind=Kind(str(r[1])),
            amount_paise=int(r[2]),
            occurred_at=_as_datetime(r[3]),
            account_id=str(r[4]),
            currency=str(r[5]).strip().upper(),
            instrument=Instrument(str(r[6])) if r[6] else None,
            order_id=str(r[7]) if r[7] else None,
            parent_id=str(r[8]) if r[8] else None,
            narration_raw=str(r[9]),
            narration_norm=str(r[10]) or normalise_narration(str(r[9])),
            counterparty_raw=str(r[11]) if r[11] else None,
            counterparty_id=str(r[12]) if r[12] else None,
            source=Source(str(r[13])),
        )
        for r in rows
    )


def load_settlement_report_sql(conn) -> tuple[DeclaredLine, ...]:
    rows = list(conn.execute(
        "SELECT credit_id, item_id, kind, amount_paise, instrument, order_id "
        "FROM settlement_line ORDER BY credit_id, item_id"
    ))
    return tuple(
        DeclaredLine(
            credit_id=str(r[0]),
            item_id=str(r[1]),
            kind=Kind(str(r[2])),
            amount_paise=int(r[3]),
            instrument=Instrument(str(r[4])) if r[4] else None,
            order_id=str(r[5]) if r[5] else None,
        )
        for r in rows
    )


# ---------------------------------------------------------------- writes


def _write_many(conn, sql: str, rows: list[tuple]) -> int:
    """Insert a batch through whichever bulk path the backend offers.

    Row-at-a-time is a network round-trip per row, which made a 10,000-row corpus
    migration into a hosted database take twenty minutes. Both backends have an
    ``executemany``; the loop is only a fallback for a connection that does not.

    No value is transformed here. The tuples are built by the callers below from
    already-canonical objects, and ``amount_paise`` passes through as the integer it is.
    """
    if not rows:
        conn.commit()
        return 0
    bulk = getattr(conn, "executemany", None)
    if bulk is not None:
        bulk(sql, rows)
    else:  # pragma: no cover - both supported backends provide executemany
        for row in rows:
            conn.execute(sql, row)
    conn.commit()
    return len(rows)


BANK_CREDIT_INSERT = (
    "INSERT OR REPLACE INTO bank_credit (credit_id, amount_paise, value_date, "
    "account_id, currency, narration_raw, narration_norm, utr) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
LEDGER_ITEM_INSERT = (
    "INSERT OR REPLACE INTO ledger_item (item_id, kind, amount_paise, occurred_at, "
    "account_id, currency, instrument, order_id, parent_id, narration_raw, "
    "narration_norm, counterparty_raw, counterparty_id, source) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
SETTLEMENT_LINE_INSERT = (
    "INSERT OR REPLACE INTO settlement_line (credit_id, item_id, kind, amount_paise, "
    "instrument, order_id) VALUES (?, ?, ?, ?, ?, ?)"
)


def write_bank_credits(conn, credits) -> int:
    ensure_source_tables(conn)
    rows = [
        (c.id, c.amount_paise, c.value_date.isoformat(), c.account_id, c.currency,
         c.narration_raw, c.narration_norm, c.utr)
        for c in credits
    ]
    return _write_many(conn, BANK_CREDIT_INSERT, rows)


def write_ledger_items(conn, items) -> int:
    ensure_source_tables(conn)
    rows = [
        (i.id, i.kind.value, i.amount_paise, i.occurred_at.isoformat(), i.account_id,
         i.currency, i.instrument.value if i.instrument else None, i.order_id,
         i.parent_id, i.narration_raw, i.narration_norm, i.counterparty_raw,
         i.counterparty_id, i.source.value)
        for i in items
    ]
    return _write_many(conn, LEDGER_ITEM_INSERT, rows)


def write_settlement_lines(conn, lines) -> int:
    ensure_source_tables(conn)
    rows = [
        (line.credit_id, line.item_id, line.kind.value, line.amount_paise,
         line.instrument.value if line.instrument else None, line.order_id)
        for line in lines
    ]
    return _write_many(conn, SETTLEMENT_LINE_INSERT, rows)


def source_aggregates(conn) -> dict[str, int]:
    """Row counts and signed paise totals, for verifying a migration moved data intact.

    These are storage-side sums used only to compare "before" with "after". No financial
    decision reads them, and the reconciliation engine never sees them.
    """
    def one(sql: str) -> int:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    return {
        "n_bank_credits": one("SELECT COUNT(*) FROM bank_credit"),
        "sum_bank_credit_paise": one("SELECT COALESCE(SUM(amount_paise), 0) FROM bank_credit"),
        "n_ledger_items": one("SELECT COUNT(*) FROM ledger_item"),
        "sum_ledger_item_paise": one("SELECT COALESCE(SUM(amount_paise), 0) FROM ledger_item"),
        "n_settlement_lines": one("SELECT COUNT(*) FROM settlement_line"),
        "sum_settlement_paise": one("SELECT COALESCE(SUM(amount_paise), 0) FROM settlement_line"),
    }
