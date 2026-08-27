"""§5.12: _open_readwrite is private and the three owners are the only importers."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.db import TABLE_OWNERS, _open_readwrite, init_db, open_readonly


def test_only_verify_writes_reconciliation():
    src = Path("src/residual_zero")
    importers = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "_open_readwrite" in text and path.name != "db.py":
            importers.append(path.parent.name if path.name == "__init__.py" else path.stem)
    assert set(importers) == {"verify", "audit", "exceptions"}
    assert set(TABLE_OWNERS) == {"verify", "audit", "exceptions"}


def test_readonly_connection_rejects_write(tmp_path: Path):
    db = tmp_path.joinpath("ledger.sqlite")
    init_db(db)
    rw = _open_readwrite(db, "audit")
    try:
        pass
    finally:
        rw.close()
    conn = open_readonly(db)
    try:
        with pytest.raises(Exception):
            conn.execute("INSERT INTO audit_entry (seq, payload, metrics, prev_hash, entry_hash) VALUES (0,'{}','{}','x','y')")
            conn.commit()
    finally:
        conn.close()
