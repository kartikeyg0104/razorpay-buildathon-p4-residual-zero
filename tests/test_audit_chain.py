"""Hash chain: genesis of zeroes, payload hash, metrics do not affect the hash, edits break it."""

from __future__ import annotations

from pathlib import Path

from residual_zero.audit import GENESIS_PREV_HASH, append_entry, open_audit, verify_chain
from residual_zero.canonical import canonical_json
from residual_zero.db import init_db, open_readonly


def test_chain_verifies_end_to_end(tmp_path: Path):
    db = tmp_path.joinpath("ledger.sqlite")
    init_db(db)
    conn = open_audit(db)
    try:
        append_entry(conn, {"n": 1}, {"t": 1})
        append_entry(conn, {"n": 2}, {"t": 2})
        ok, broken, _head = verify_chain(conn)
        assert ok is True
        assert broken is None
    finally:
        conn.close()


def test_edit_breaks_chain_at_that_entry(tmp_path: Path):
    db = tmp_path.joinpath("ledger.sqlite")
    init_db(db)
    conn = open_audit(db)
    try:
        append_entry(conn, {"n": 1}, {})
        append_entry(conn, {"n": 2}, {})
        conn.execute("UPDATE audit_entry SET payload = ? WHERE seq = 1", ('{"n":99}',))
        conn.commit()
        ok, broken, _head = verify_chain(conn)
        assert ok is False
        assert broken == 1
    finally:
        conn.close()


def test_genesis_seeds_with_zeroes(tmp_path: Path):
    db = tmp_path.joinpath("ledger.sqlite")
    init_db(db)
    conn = open_audit(db)
    try:
        entry = append_entry(conn, {"n": 0}, {})
        assert entry.prev_hash == GENESIS_PREV_HASH
        assert len(entry.prev_hash) == 64
    finally:
        conn.close()


def test_canonical_json_is_byte_stable():
    payload = {"b": "café", "a": 1}
    assert canonical_json(payload) == canonical_json(payload)


def test_metrics_do_not_affect_entry_hash(tmp_path: Path):
    db = tmp_path.joinpath("ledger.sqlite")
    init_db(db)
    conn = open_audit(db)
    try:
        a = append_entry(conn, {"n": 1}, {"t": 1})
        conn.execute("DELETE FROM audit_entry")
        conn.commit()
        b = append_entry(conn, {"n": 1}, {"t": 999})
        assert a.entry_hash == b.entry_hash
    finally:
        conn.close()
