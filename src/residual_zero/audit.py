"""Hash-chained audit log. Timings live in metrics, never in the hashed payload (NN-9)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.canonical import canonical_json, payload_digest
from residual_zero.db import _open_readwrite

_STRICT = ConfigDict(frozen=True, extra="forbid")

GENESIS_PREV_HASH: str = "0" * 64


class AuditEntry(BaseModel):
    model_config = _STRICT

    seq: int
    payload: dict[str, Any]
    metrics: dict[str, Any]
    prev_hash: str
    entry_hash: str


def _entry_hash(payload: Mapping[str, Any], prev_hash: str) -> str:
    import hashlib
    blob = canonical_json(payload) + b"\x00" + prev_hash.encode("ascii")
    return hashlib.sha256(blob).hexdigest()


def append_entry(
    conn: sqlite3.Connection, payload: Mapping[str, Any], metrics: Mapping[str, Any],
) -> AuditEntry:
    """entry_hash = sha256(canonical_json(payload) || 0x00 || prev_hash_ascii). D11 pins it."""
    cur = conn.execute("SELECT MAX(seq), entry_hash FROM audit_entry")
    row = cur.fetchone()
    if row is None or row[0] is None:
        seq = 0
        prev = GENESIS_PREV_HASH
    else:
        seq = int(row[0]) + 1
        prev = str(row[1])
    entry_hash = _entry_hash(payload, prev)
    conn.execute(
        "INSERT INTO audit_entry (seq, payload, metrics, prev_hash, entry_hash) VALUES (?, ?, ?, ?, ?)",
        (
            seq,
            canonical_json(payload).decode("utf-8"),
            json.dumps(dict(metrics), sort_keys=True, separators=(",", ":")),
            prev,
            entry_hash,
        ),
    )
    conn.commit()
    return AuditEntry(
        seq=seq,
        payload=dict(payload),
        metrics=dict(metrics),
        prev_hash=prev,
        entry_hash=entry_hash,
    )


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, int | None, str]:
    """Walk the chain. Returns (ok, first_broken_seq, head_hash)."""
    rows = list(conn.execute(
        "SELECT seq, payload, prev_hash, entry_hash FROM audit_entry ORDER BY seq"
    ))
    if not rows:
        return True, None, GENESIS_PREV_HASH
    expected_prev = GENESIS_PREV_HASH
    head = GENESIS_PREV_HASH
    for seq, payload_text, prev_hash, entry_hash in rows:
        if prev_hash != expected_prev:
            return False, int(seq), head
        payload = json.loads(payload_text)
        recomputed = _entry_hash(payload, prev_hash)
        if recomputed != entry_hash:
            return False, int(seq), head
        expected_prev = entry_hash
        head = entry_hash
    return True, None, head


def open_audit(path: "Path") -> sqlite3.Connection:
    from pathlib import Path as P
    if not isinstance(path, P):
        path = P(path)
    return _open_readwrite(path, "audit")
