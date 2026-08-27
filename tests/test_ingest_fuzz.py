"""F48: malformed fixtures raise IngestError and never return a prefix."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from residual_zero.ingest import IngestError
from residual_zero.ingest.camt053 import load_camt053
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.mt940 import load_mt940
from residual_zero.ingest.source_root import SourceRoot

FIX = Path("fixtures").joinpath("malformed")


def _count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM c").fetchone()[0])


@pytest.mark.parametrize(
    "name,loader",
    [
        ("truncated.xml", lambda p: load_camt053(p)),
        ("latin1.xml", lambda p: load_camt053(p)),
        ("camt_missing_amount.xml", lambda p: load_camt053(p)),
        ("mt940_bad_date.sta", lambda p: load_mt940(p)),
        ("bom.csv", lambda p: load_bank_credits(SourceRoot(p.parent), p.name)),
        ("mixed_newlines.csv", lambda p: load_bank_credits(SourceRoot(p.parent), p.name)),
        ("dup_header.csv", lambda p: load_bank_credits(SourceRoot(p.parent), p.name)),
    ],
)
def test_malformed_is_typed_and_empty(name, loader, tmp_path: Path):
    path = FIX.joinpath(name)
    conn = sqlite3.connect(str(tmp_path.joinpath("t.sqlite")))
    try:
        conn.execute("CREATE TABLE c (id TEXT)")
        conn.commit()
        before = _count(conn)
        with pytest.raises(IngestError) as excinfo:
            rows = loader(path)
            for row in rows:
                conn.execute("INSERT INTO c VALUES (?)", (row.id,))
            conn.commit()
        err = excinfo.value
        assert err.line is not None or err.element is not None or err.path
        assert _count(conn) == before
    finally:
        conn.close()
