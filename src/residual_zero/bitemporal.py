"""F46: as-of at audit seq N is the last disposition per credit among entries with seq <= N.

The audit chain already has a total order. This module is two independent folds over that
order: a last-write query and a prefix replay. Equality of the two dicts is the feature.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Mapping, Sequence

PayloadRow = tuple[int, dict]


def as_of_view(conn: sqlite3.Connection, seq: int) -> dict[str, str]:
    """Last disposition per bank_credit_id among audit rows with seq <= N (SQL last-write)."""
    rows = list(
        conn.execute(
            "SELECT seq, payload FROM audit_entry WHERE seq <= ? ORDER BY seq",
            (seq,),
        )
    )
    last: dict[str, tuple[int, str]] = {}
    for seq_i, payload_text in rows:
        payload = json.loads(payload_text)
        cid = str(payload.get("bank_credit_id") or "")
        disp = str(payload.get("disposition") or "")
        if not cid:
            continue
        prev = last.get(cid)
        if prev is None or int(seq_i) >= prev[0]:
            last[cid] = (int(seq_i), disp)
    return {cid: disp for cid, (_seq, disp) in last.items()}


def replay_prefix(entries: Sequence[PayloadRow], seq: int) -> dict[str, str]:
    """Fold dispositions in seq order up to N. Independent of as_of_view's SQL path."""
    last: dict[str, str] = {}
    for seq_i, payload in entries:
        if seq_i > seq:
            continue
        cid = str(payload.get("bank_credit_id") or "")
        disp = str(payload.get("disposition") or "")
        if cid:
            last[cid] = disp
    return last


def load_payloads(conn: sqlite3.Connection) -> list[PayloadRow]:
    rows = list(conn.execute("SELECT seq, payload FROM audit_entry ORDER BY seq"))
    return [(int(seq), json.loads(payload)) for seq, payload in rows]


def sample_seqs(max_seq: int, n: int = 20) -> tuple[int, ...]:
    """n inclusive points from 0..max_seq, including both ends when possible."""
    if max_seq < 0:
        return ()
    if n <= 1 or max_seq == 0:
        return (0,)
    if n >= max_seq + 1:
        return tuple(range(0, max_seq + 1))
    span = max_seq
    out: list[int] = []
    for i in range(n):
        out.append((i * span) // (n - 1))
    return tuple(dict.fromkeys(out))


def views_equal(a: Mapping[str, str], b: Mapping[str, str]) -> bool:
    return dict(a) == dict(b)
