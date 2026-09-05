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


AUDIT_LOCK = "residual_zero.audit_entry"


def append_entry(
    conn: sqlite3.Connection,
    payload: Mapping[str, Any],
    metrics: Mapping[str, Any],
    run_id: str | None = None,
) -> AuditEntry:
    """entry_hash = sha256(canonical_json(payload) || 0x00 || prev_hash_ascii). D11 pins it.

    Appending is a read-modify-write: read the head, hash against its hash, insert the
    successor. Two writers interleaving that would either collide on ``seq`` or fork the
    chain into two branches claiming the same predecessor, so on a backend that has more
    than one writer the whole sequence takes a lock first. It is transaction-scoped, so a
    crashed writer releases it rather than wedging the log.

    The two ``UNIQUE`` constraints on the production table (``entry_hash``, ``prev_hash``)
    are the backstop: even without the lock, a fork is a constraint violation rather than a
    silently branched audit trail.
    """
    locker = getattr(conn, "lock_for_append", None)
    if locker is not None:
        locker(AUDIT_LOCK)
    # `SELECT MAX(seq), entry_hash` relied on SQLite's bare-column-with-aggregate
    # extension, which returns the row that produced the maximum. Standard SQL rejects it,
    # so the head is selected explicitly — same row, same result, portable.
    cur = conn.execute("SELECT seq, entry_hash FROM audit_entry ORDER BY seq DESC LIMIT 1")
    row = cur.fetchone()
    if row is None or row[0] is None:
        seq = 0
        prev = GENESIS_PREV_HASH
    else:
        seq = int(row[0]) + 1
        prev = str(row[1])
    entry_hash = _entry_hash(payload, prev)
    # run_id sits outside the hashed payload deliberately: entry_hash covers what the
    # engine decided, not which execution recorded it, so linking an entry to a run cannot
    # change a hash and an existing chain still verifies.
    conn.execute(
        "INSERT INTO audit_entry (seq, payload, metrics, prev_hash, entry_hash, run_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            seq,
            canonical_json(payload).decode("utf-8"),
            json.dumps(dict(metrics), sort_keys=True, separators=(",", ":")),
            prev,
            entry_hash,
            run_id,
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


def open_audit(path: "Path | None" = None) -> sqlite3.Connection:
    """Write connection for the audit chain and the run record.

    ``None`` means "wherever the current organisation's rows live", which is what a
    recorded run wants. An explicit path is the single-tenant CLI and test route, and it
    always wins — so passing a placeholder here would send a tenant's run to that file
    instead of its own ledger.
    """
    from pathlib import Path as P

    if path is not None and not isinstance(path, P):
        path = P(path)
    return _open_readwrite(path, "audit")


# ---------------------------------------------------------------- recorded runs
#
# A run record says a deterministic execution happened: over which dataset, under which
# configuration, and whether it finished. The per-credit results were always persisted —
# audit_entry carries the uniqueness, residual and disposition the engine decided, on
# either backend. What was missing was the run, and without it a reader cannot tell
# "searched and found nothing" from "never searched".
#
# These live in audit.py because ``reconciliation_run`` is owned by the audit writer.
# Adding a fourth module that opens a write connection would break the rule that exactly
# three do (§5.12), and a run record is an audit fact, not a new kind of authority.
#
# Nothing here computes a financial value. The engine decides; this records that it ran.

RUN_RUNNING = "RUNNING"
RUN_COMPLETED = "COMPLETED"
#: The engine finished but did not cover the dataset. A real outcome, not a failure: the
#: results are genuine and a retry completes it. Never to be read as COMPLETED.
RUN_PARTIAL = "PARTIAL"
RUN_FAILED = "FAILED"

#: Statuses whose per-credit results a reader should believe. A run still in flight has
#: not finished deciding, and a failed one produced no result at all.
RUN_READABLE = (RUN_COMPLETED, RUN_PARTIAL)


class RunConflict(RuntimeError):
    """A completed run already exists for this identity. Re-running would duplicate it."""


def derive_run_id(
    org_id: str,
    split: str,
    dataset_root: str,
    dataset_digest: str,
    config_digest: str,
    limit: int = 0,
) -> str:
    """A stable identity for "this organisation, this data, this configuration".

    Deliberately not a timestamp: the same run executed twice must collide so the second
    can be refused, and a clock makes every execution unique by construction. Same inputs
    in, same id out, on any machine.
    """
    import hashlib

    material = canonical_json(
        {
            "org_id": org_id,
            "split": split,
            "dataset_root": dataset_root,
            "dataset_digest": dataset_digest,
            "config_digest": config_digest,
            "limit": int(limit),
        }
    )
    # canonical_json already returns bytes, and its ordering is what makes the id stable.
    return "run_" + hashlib.sha256(material).hexdigest()[:24]


_RUN_KEYS = (
    "run_id", "org_id", "split", "dataset_digest", "config_digest", "status",
    "n_credits", "n_computed", "n_reused", "n_persisted",
    "started_at", "finished_at", "error",
)
_RUN_COLUMNS = ", ".join(_RUN_KEYS)


def _run_row(row) -> dict[str, Any]:
    """One shape regardless of backend.

    PostgreSQL hands back TIMESTAMPTZ as ``datetime`` and SQLite hands back the TEXT it
    was given. A caller serialising the result should not have to know which database it
    is talking to, so the timestamps leave here as ISO strings either way.
    """
    from datetime import date, datetime

    out = dict(zip(_RUN_KEYS, row))
    for key in ("started_at", "finished_at"):
        value = out.get(key)
        if isinstance(value, (datetime, date)):
            out[key] = value.isoformat()
    # Completeness is coverage against the dataset, never the invocation's own count.
    out["complete"] = bool(out["n_credits"]) and out["n_persisted"] == out["n_credits"]
    return out


def find_run(conn, run_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {_RUN_COLUMNS} FROM reconciliation_run WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return _run_row(row)


def latest_completed_run(conn) -> dict[str, Any] | None:
    """The run a reader should believe, by an explicit rule.

    1. A COMPLETED run for this organisation, most recent first.
    2. Failing that, a PARTIAL one — it finished deciding and its results are real.
    3. Never RUNNING (has not finished) and never FAILED (produced nothing).

    Rank before recency, so a later PARTIAL run cannot displace an earlier COMPLETED one
    and make the desk report less than it can prove.

    Organisation scoping is the connection: this reads one schema and cannot see another
    organisation's runs.
    """
    row = conn.execute(
        f"SELECT {_RUN_COLUMNS} FROM reconciliation_run WHERE status IN (?, ?) "
        # A covered run outranks an uncovered one regardless of age. Ordering by time
        # alone would let a later PARTIAL run displace an earlier COMPLETED one, which
        # would make the desk report less than it can prove. Time only breaks ties within
        # a rank.
        "ORDER BY CASE WHEN status = 'COMPLETED' THEN 0 ELSE 1 END, "
        "started_at DESC, run_id DESC LIMIT 1",
        RUN_READABLE,
    ).fetchone()
    if row is None:
        return None
    return _run_row(row)


def begin_run(
    conn,
    *,
    run_id: str,
    org_id: str,
    split: str,
    dataset_root: str,
    dataset_digest: str,
    config_digest: str,
    engine_version: str,
    n_credits: int,
    started_at: str,
) -> None:
    """Open a run as RUNNING. Refuses to reopen one that already covers its dataset.

    The refusal is the idempotency guarantee: the same organisation, dataset and
    configuration derive the same id, so a second execution raises instead of writing a
    second set of results for the same facts. Coverage is the test, not status — a run
    that stopped short still has credits nobody has computed.
    """
    existing = find_run(conn, run_id)
    # Covered, not merely COMPLETED. This refusal exists to stop a second set of results
    # describing facts already recorded — which is only true once coverage is there. A
    # PARTIAL run, or one whose coverage was never recorded, has work left to do.
    if existing is not None and existing["complete"]:
        raise RunConflict(
            f"run {run_id} already covers organisation {existing['org_id']!r} "
            f"({existing['n_persisted']}/{existing['n_credits']} credits "
            f"at {existing['finished_at']}). "
            f"Re-running the same dataset under the same configuration would duplicate it."
        )
    # A previous RUNNING or FAILED attempt is replaced: it never became a result.
    conn.execute("DELETE FROM reconciliation_run WHERE run_id = ?", (run_id,))
    conn.execute(
        "INSERT INTO reconciliation_run "
        "(run_id, org_id, split, dataset_root, dataset_digest, config_digest, "
        " engine_version, status, n_credits, n_computed, n_reused, n_persisted, "
        " started_at, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, org_id, split, dataset_root, dataset_digest, config_digest,
         engine_version, RUN_RUNNING, int(n_credits), 0, 0, 0, started_at, ""),
    )
    conn.commit()


def persisted_coverage(conn, run_id: str) -> int:
    """How many distinct credits carry a persisted result for this run.

    Counted from the rows, never accumulated in Python. A counter and the rows it claims
    to describe can disagree — that is exactly how a run covering 248 credits reported
    231 — and when they do, the rows are the ones that are true.

    DISTINCT because a credit reprocessed by a retry has more than one entry: coverage is
    credits, not entries.
    """
    row = conn.execute(
        "SELECT COUNT(DISTINCT json_extract(payload, '$.bank_credit_id')) "
        "FROM audit_entry WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def complete_run(
    conn,
    run_id: str,
    *,
    n_computed: int,
    n_credits: int,
    finished_at: str,
) -> str:
    """Close the run against its actual persisted coverage. Returns the status recorded.

    COMPLETED is a claim that the dataset is covered, so it is decided by counting rows,
    not by trusting the loop's own tally. A run that finished without covering the dataset
    is PARTIAL: its results are real, and calling it complete would be the lie this whole
    exercise exists to remove. The database restates the rule as a CHECK constraint.
    """
    n_persisted = persisted_coverage(conn, run_id)
    n_reused = max(0, n_persisted - int(n_computed))
    status = RUN_COMPLETED if n_persisted == int(n_credits) else RUN_PARTIAL
    conn.execute(
        "UPDATE reconciliation_run SET status = ?, n_computed = ?, n_reused = ?, "
        "n_persisted = ?, n_credits = ?, finished_at = ? WHERE run_id = ?",
        (status, int(n_computed), n_reused, n_persisted, int(n_credits),
         finished_at, run_id),
    )
    conn.commit()
    return status


def discard_run(conn, run_id: str, *, error: str, finished_at: str) -> None:
    """Undo a run that did not finish, then record why.

    The audit entries this run wrote are deleted rather than left behind: a partial run is
    not a smaller run, and counting its rows would report a search that never completed.
    The run row survives as FAILED so the failure is visible instead of silent.
    """
    conn.execute("DELETE FROM audit_entry WHERE run_id = ?", (run_id,))
    conn.execute(
        "UPDATE reconciliation_run SET status = ?, finished_at = ?, error = ? "
        "WHERE run_id = ?",
        (RUN_FAILED, finished_at, error[:500], run_id),
    )
    conn.commit()
