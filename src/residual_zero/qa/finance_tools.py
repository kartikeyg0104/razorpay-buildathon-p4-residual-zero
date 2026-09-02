"""Read-only structured finance tools. The LLM never queries tables or writes CLEARED."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from residual_zero.console.facts import credit_forensic, t04_fields, track04_snapshot
from residual_zero.money import format_rupees
from residual_zero.normalise import parse_rupee_display
from residual_zero.storage.errors import QUERY_ERRORS, rollback_quietly

TOOL_NAMES = (
    "get_transaction",
    "get_reconciliation",
    "get_batch_summary",
    "get_exceptions",
    "get_unreconciled_amount",
    "get_ambiguous_transactions",
    "get_unmatched_transactions",
    "get_verified_transactions",
    "get_settlement_details",
    "get_match_candidates",
    "get_tax_breakdown",
    "get_audit_trail",
    "get_transaction_evidence",
    "get_reconciliation_statistics",
    "get_top_exceptions",
    "extract_evidence",
    "validate_extraction",
    "get_evidence_graph",
    "get_evidence_level",
    "get_review_priority",
    "get_next_best_action",
    "get_root_cause",
    "get_potentially_recoverable",
    "explorer_query",
    "investigate_transaction",
    "exception_intelligence",
    "find_by_reference",
    "find_by_settlement",
    "find_by_invoice",
    "find_by_member",
    "find_by_account",
    "find_by_date",
    "compare_sources",
    "explain_verification_failure",
    "get_candidate_equations",
    "get_missing_records",
    "get_transaction_timeline",
    "compare_solutions",
    "get_proof_explorer",
    "explain_candidate_rejection",
    "get_exposure_queue",
    "get_duplicate_utrs",
    "get_standup",
)

_LIST_CAP = 20
_ID_CAP = 40
_TAX_KINDS = frozenset({"FEE", "TAX_GST", "TAX_WITHHOLDING", "RESERVE_HOLD", "BANK_CHARGE"})


def _cite(eid: str, source_type: str, source_record_id: str, field: str, value: Any) -> dict[str, Any]:
    return {
        "evidence_id": eid,
        "source_type": source_type,
        "source_record_id": source_record_id,
        "field": field,
        "value": value,
    }


def _cap(values: tuple[str, ...] | list[str], limit: int = _ID_CAP) -> list[str]:
    return list(values[:limit])


def _limit_n(limit: int | None) -> int:
    if limit is None:
        return _LIST_CAP
    if limit < 0:
        return 0
    if limit > 100:
        return 100
    return limit


def _desk():
    from residual_zero.console.app import _credit_lookup, _db, _overlay, _split

    return _split(), _overlay(), _credit_lookup(), _db()


def _audits(conn: sqlite3.Connection | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if conn is None:
        return out
    try:
        for (payload,) in conn.execute("SELECT payload FROM audit_entry"):
            blob = json.loads(payload)
            cid = blob.get("bank_credit_id")
            if cid:
                out[str(cid)] = blob
    # QUERY_ERRORS, not sqlite3.OperationalError: the equivalent PostgreSQL error is a
    # different class, so a name-based except stopped degrading the moment Postgres
    # became a backend and a missing table became a 500. rollback_quietly clears the
    # aborted transaction Postgres leaves behind, so the next query on this connection
    # can still run.
    except QUERY_ERRORS:
        rollback_quietly(conn)
        return {}
    return out


def _exceptions_map(conn: sqlite3.Connection | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if conn is None:
        return out
    try:
        for cid, cls in conn.execute("SELECT bank_credit_id, exception_class FROM exception"):
            out[str(cid)] = str(cls)
    except QUERY_ERRORS:
        rollback_quietly(conn)
        return {}
    return out


def _recon_row(conn: sqlite3.Connection | None, credit_id: str) -> dict[str, Any] | None:
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT bank_credit_id, claimed_total_paise, residual_paise, uniqueness, disposition, pool_scope "
            "FROM reconciliation WHERE bank_credit_id = ?",
            (credit_id,),
        ).fetchone()
    except QUERY_ERRORS:
        rollback_quietly(conn)
        return None
    if row is None:
        return None
    return {
        "bank_credit_id": row[0],
        "claimed_total_paise": row[1],
        "residual_paise": row[2],
        "uniqueness": row[3],
        "disposition": row[4],
        "pool_scope": row[5] if len(row) > 5 else "FULL",
    }


def _status(uniqueness: str, disposition: str, gate_ok: bool) -> str:
    if disposition == "CLEARED":
        return "CLEARED"
    if uniqueness == "NONE_FOUND":
        return "UNMATCHED"
    if uniqueness == "BUDGET_EXCEEDED":
        return "BUDGET_EXCEEDED"
    if uniqueness == "AMBIGUOUS":
        return "REVIEW_REQUIRED"
    if uniqueness == "UNIQUE" and disposition != "CLEARED":
        return "REVIEW_REQUIRED"
    if gate_ok:
        return "RESIDUAL_ZERO_NOT_CLEARED"
    return "REVIEW_REQUIRED"


def _solution_count(uniqueness: str, alternate_count: int | None) -> int:
    if uniqueness == "UNIQUE":
        return 1
    if uniqueness in {"NONE_FOUND", "BUDGET_EXCEEDED", ""}:
        if uniqueness == "NONE_FOUND":
            return 0
        if uniqueness == "BUDGET_EXCEEDED":
            return 0
        return 0
    if uniqueness == "AMBIGUOUS":
        if alternate_count is not None and alternate_count >= 2:
            return alternate_count
        return 2
    return 0


def get_transaction(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    split, overlay, lookup, conn = _desk()
    try:
        credit = lookup.get(cid)
        if credit is None:
            return {
                "found": False,
                "transaction_id": cid,
                "error": "not_found",
                "writes_cleared": False,
            }
        gate = overlay.by_id.get(cid) if overlay is not None else None
        declared = ()
        if split is not None:
            declared = tuple(split[2].get(cid) or ())
        member_ids = tuple(r.item_id for r in declared)
        evidence = [
            _cite("txn.id", "bank_credit", cid, "id", cid),
            _cite("txn.amount", "bank_credit", cid, "amount_paise", credit.amount_paise),
            _cite("txn.date", "bank_credit", cid, "value_date", credit.value_date.isoformat()),
            _cite("txn.account", "bank_credit", cid, "account_id", credit.account_id),
        ]
        return {
            "found": True,
            "transaction_id": cid,
            "bank_amount_paise": credit.amount_paise,
            "bank_amount_display": format_rupees(credit.amount_paise),
            "currency": credit.currency,
            "account_id": credit.account_id,
            "value_date": credit.value_date.isoformat(),
            "narration": credit.narration_raw,
            "utr": credit.utr or "",
            "declared_count": len(member_ids),
            "matched_record_ids": _cap(member_ids),
            "gate_a_ok": bool(gate is not None and gate.ok),
            "writes_cleared": False,
            "evidence": evidence,
        }
    finally:
        if conn is not None:
            conn.close()


def get_reconciliation(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    split, overlay, lookup, conn = _desk()
    try:
        credit = lookup.get(cid)
        if credit is None:
            return {
                "found": False,
                "transaction_id": cid,
                "error": "not_found",
                "writes_cleared": False,
            }
        gate = overlay.by_id.get(cid) if overlay is not None else None
        rec = _recon_row(conn, cid)
        audits = _audits(conn)
        audit = audits.get(cid) or {}
        uniqueness = str((rec or {}).get("uniqueness") or audit.get("uniqueness") or "AMBIGUOUS")
        disposition = str((rec or {}).get("disposition") or audit.get("disposition") or "FLAGGED")
        residual_paise = credit.amount_paise
        if rec is not None and rec.get("residual_paise") is not None:
            residual_paise = int(rec["residual_paise"])
        elif gate is not None:
            residual_paise = gate.residual_paise
        declared = ()
        if split is not None:
            declared = tuple(split[2].get(cid) or ())
        member_ids = tuple(r.item_id for r in declared)
        alt = audit.get("alternate_count")
        alt_n = int(alt) if isinstance(alt, int) else None
        solutions = _solution_count(uniqueness, alt_n)
        gate_ok = bool(gate is not None and gate.ok)
        status = _status(uniqueness, disposition, gate_ok)
        forensic = credit_forensic(cid) or {}
        evidence = [
            _cite("recon.residual", "overlay" if gate is not None else "sqlite", cid, "residual_paise", residual_paise),
            _cite("recon.uniqueness", "audit", cid, "uniqueness", uniqueness),
            _cite("recon.disposition", "audit", cid, "disposition", disposition),
            _cite("recon.solutions", "search", cid, "solution_count", solutions),
            _cite("recon.gate_a", "overlay", cid, "ok", gate_ok),
        ]
        from residual_zero.console.clear_gate import auto_clear_decision

        pool_scope = "FULL"
        if rec is not None and rec.get("pool_scope"):
            pool_scope = str(rec["pool_scope"])
        elif audit.get("pool_scope"):
            pool_scope = str(audit["pool_scope"])
        decision = auto_clear_decision(
            residual_paise=residual_paise,
            uniqueness=uniqueness,
            pool_scope=pool_scope,
            ordering_score=str(audit.get("ordering_score") or "") or None,
            disposition=disposition,
        )
        return {
            "found": True,
            "transaction_id": cid,
            "bank_amount_paise": credit.amount_paise,
            "bank_amount_display": format_rupees(credit.amount_paise),
            "matched_record_ids": _cap(member_ids),
            "matched_count": len(member_ids),
            "residual_paise": residual_paise,
            "residual_display": format_rupees(residual_paise),
            "solution_count": solutions,
            "uniqueness": uniqueness,
            "disposition": disposition,
            "status": status,
            "verification_method": "verify_declared" if gate_ok else "NONE",
            "gate_a_ok": gate_ok,
            "auto_cleared": disposition == "CLEARED",
            "writes_cleared": False,
            "auto_clear_decision": decision,
            "recovery": forensic.get("recovery"),
            "exception_class": str(audit.get("exception_class") or ""),
            "evidence": evidence,
        }
    finally:
        if conn is not None:
            conn.close()


def get_batch_summary() -> dict[str, Any]:
    snap = track04_snapshot()
    dev = t04_fields("dev")
    test = t04_fields("test")
    _, overlay, _, conn = _desk()
    try:
        n_overlay_ok = overlay.n_ok if overlay is not None else 0
        n_overlay_rz = overlay.n_residual_zero if overlay is not None else 0
        return {
            "split": "dev",
            "scored": int(dev.get("n_scored") or snap.scored or 0),
            "residual_zero": dev.get("residual-zero") or snap.residual_zero,
            "settlement_linked": dev.get("settlement-linked / member-identified") or snap.settlement_linked,
            "verified_linked": dev.get("verified-linked (ids + residual 0)") or "",
            "unique": int(dev.get("unique") or 0),
            "ambiguous": int(dev.get("ambiguous") or 0),
            "none_found": int(dev.get("none_found") or 0),
            "budget_exceeded": int(dev.get("budget_exceeded_search") or snap.budget_dev or 0),
            "auto_clear": int(dev.get("auto-clear") or snap.search_cleared or 0),
            "false_clears": int(dev.get("false_clears") or 0),
            "search_coverage": dev.get("search_coverage") or "",
            "flagged": int(dev.get("flagged") or snap.flagged or 0),
            "unreconciled_display": snap.unreconciled,
            "throughput_per_1000s": snap.throughput_per_1000s,
            "wall_ns": snap.wall_ns,
            "wall_clock_ms": dev.get("wall_clock_ms") or "",
            "overlay_gate_a": n_overlay_ok,
            "overlay_residual_zero": n_overlay_rz,
            "writes_cleared": False,
            "test": {
                "scored": int(test.get("n_scored") or 0),
                "residual_zero": test.get("residual-zero") or "",
                "settlement_linked": test.get("settlement-linked / member-identified") or snap.test_exact,
                "ambiguous": int(test.get("ambiguous") or 0),
                "none_found": int(test.get("none_found") or 0),
                "auto_clear": int(test.get("auto-clear") or 0),
                "false_clears": int(test.get("false_clears") or 0),
                "search_coverage": test.get("search_coverage") or snap.test_search_completed,
                "budget_exceeded": int(test.get("budget_exceeded_search") or snap.test_budget or 0),
                "wall_clock_ms": test.get("wall_clock_ms") or "",
            },
            "evidence": [
                _cite("batch.residual_zero", "t04.md", "dev", "residual-zero", dev.get("residual-zero") or snap.residual_zero),
                _cite("batch.ambiguous", "t04.md", "dev", "ambiguous", int(dev.get("ambiguous") or 0)),
                _cite("batch.auto_clear", "t04.md", "dev", "auto-clear", 0),
                _cite("batch.false_clears", "t04.md", "dev", "false_clears", 0),
            ],
        }
    finally:
        if conn is not None:
            conn.close()


def get_reconciliation_statistics() -> dict[str, Any]:
    return get_batch_summary()


def get_unreconciled_amount() -> dict[str, Any]:
    snap = track04_snapshot()
    _, overlay, lookup, conn = _desk()
    try:
        books_paise = 0
        try:
            books_paise = parse_rupee_display(snap.unreconciled)
        except ValueError:
            books_paise = 0
        overlay_paise = 0
        if overlay is not None:
            for cid, credit in lookup.items():
                gate = overlay.by_id.get(cid)
                if gate is None:
                    overlay_paise += credit.amount_paise
                elif not gate.ok:
                    residual = gate.residual_paise
                    overlay_paise += residual if residual >= 0 else -residual
        return {
            "unreconciled_display": snap.unreconciled,
            "unreconciled_paise": books_paise,
            "overlay_open_paise": overlay_paise,
            "overlay_open_display": format_rupees(overlay_paise),
            "auto_clear": 0,
            "writes_cleared": False,
            "evidence": [
                _cite("books.unreconciled", "books.md", "dev", "unreconciled_value", snap.unreconciled),
                _cite("overlay.open", "overlay", "posted", "open_paise", overlay_paise),
            ],
        }
    finally:
        if conn is not None:
            conn.close()


def _list_credits(
    predicate: Callable[[str, Any, dict[str, Any], dict[str, Any]], bool],
    limit: int | None,
) -> dict[str, Any]:
    n = _limit_n(limit)
    split, overlay, lookup, conn = _desk()
    rows: list[dict[str, Any]] = []
    try:
        audits = _audits(conn)
        for cid, credit in lookup.items():
            gate = overlay.by_id.get(cid) if overlay is not None else None
            audit = audits.get(cid) or {}
            if not predicate(cid, gate, audit, {"credit": credit}):
                continue
            uniqueness = str(audit.get("uniqueness") or "AMBIGUOUS")
            rows.append(
                {
                    "transaction_id": cid,
                    "bank_amount_display": format_rupees(credit.amount_paise),
                    "account_id": credit.account_id,
                    "uniqueness": uniqueness,
                    "gate_a_ok": bool(gate is not None and gate.ok),
                    "residual_display": format_rupees(gate.residual_paise) if gate is not None else format_rupees(credit.amount_paise),
                    "href": "/credit/" + cid,
                }
            )
            if len(rows) >= n:
                break
        return {
            "n": len(rows),
            "limit": n,
            "rows": rows,
            "writes_cleared": False,
        }
    finally:
        if conn is not None:
            conn.close()


def get_ambiguous_transactions(limit: int | None = None) -> dict[str, Any]:
    stats = get_batch_summary()

    def pred(_cid: str, _gate: Any, audit: dict[str, Any], _extra: dict[str, Any]) -> bool:
        return str(audit.get("uniqueness") or "AMBIGUOUS") == "AMBIGUOUS"

    got = _list_credits(pred, limit)
    got["count_official"] = stats["ambiguous"]
    got["split"] = "dev"
    got["evidence"] = stats["evidence"]
    return got


def get_unmatched_transactions(limit: int | None = None) -> dict[str, Any]:
    stats = get_batch_summary()

    def pred(cid: str, gate: Any, audit: dict[str, Any], _extra: dict[str, Any]) -> bool:
        uniqueness = str(audit.get("uniqueness") or "")
        if uniqueness == "NONE_FOUND":
            return True
        forensic = credit_forensic(cid) or {}
        return forensic.get("recovery") == "GENUINELY_UNMATCHED" and gate is None

    got = _list_credits(pred, limit)
    got["count_official"] = stats["none_found"]
    got["evidence"] = [
        _cite("batch.none_found", "t04.md", "dev", "none_found", stats["none_found"]),
    ]
    return got


def get_verified_transactions(limit: int | None = None) -> dict[str, Any]:
    stats = get_batch_summary()

    def pred(_cid: str, gate: Any, _audit: dict[str, Any], _extra: dict[str, Any]) -> bool:
        return gate is not None and gate.ok

    got = _list_credits(pred, limit)
    got["count_official"] = stats["residual_zero"]
    got["note"] = "residual-zero is verify_declared.ok, not auto-clear"
    got["evidence"] = stats["evidence"]
    return got


def get_exceptions(exception_type: str | None = None) -> dict[str, Any]:
    wanted = str(exception_type or "").strip().upper()
    split, overlay, lookup, conn = _desk()
    try:
        audits = _audits(conn)
        by_class: dict[str, int] = {}
        sample: list[dict[str, Any]] = []
        for cid, credit in lookup.items():
            audit = audits.get(cid) or {}
            uniqueness = str(audit.get("uniqueness") or "AMBIGUOUS")
            cls = str(audit.get("exception_class") or uniqueness)
            gate = overlay.by_id.get(cid) if overlay is not None else None
            if wanted:
                if wanted == "AMBIGUOUS" and uniqueness != "AMBIGUOUS":
                    continue
                if wanted == "NONE_FOUND" and uniqueness != "NONE_FOUND":
                    continue
                if wanted not in {"AMBIGUOUS", "NONE_FOUND"} and wanted not in cls:
                    forensic = credit_forensic(cid) or {}
                    blob = " ".join(
                        (
                            cls,
                            uniqueness,
                            str(forensic.get("bucket") or ""),
                            str(forensic.get("recovery") or ""),
                        )
                    )
                    if wanted not in blob:
                        continue
            by_class[cls or uniqueness] = by_class.get(cls or uniqueness, 0) + 1
            if len(sample) < _LIST_CAP:
                sample.append(
                    {
                        "transaction_id": cid,
                        "exception_class": cls,
                        "uniqueness": uniqueness,
                        "gate_a_ok": bool(gate is not None and gate.ok),
                        "amount_display": format_rupees(credit.amount_paise),
                        "href": "/credit/" + cid,
                    }
                )
        stats = get_batch_summary()
        count = len(sample)
        if wanted == "AMBIGUOUS":
            count = stats["ambiguous"]
        elif wanted == "NONE_FOUND":
            count = stats["none_found"]
        return {
            "exception_type": wanted or None,
            "count": count,
            "by_class": by_class,
            "rows": sample,
            "official_ambiguous": stats["ambiguous"],
            "official_none_found": stats["none_found"],
            "writes_cleared": False,
            "evidence": [
                _cite("exc.count", "t04.md", "dev", wanted or "exceptions", count),
            ],
        }
    finally:
        if conn is not None:
            conn.close()


def get_top_exceptions(limit: int = 10) -> dict[str, Any]:
    n = _limit_n(limit)
    split, overlay, lookup, conn = _desk()
    try:
        audits = _audits(conn)
        by_class: dict[str, int] = {}
        by_account: dict[str, int] = {}
        amounts: list[tuple[int, str, str]] = []
        for cid, credit in lookup.items():
            audit = audits.get(cid) or {}
            uniqueness = str(audit.get("uniqueness") or "AMBIGUOUS")
            cls = str(audit.get("exception_class") or uniqueness)
            by_class[cls] = by_class.get(cls, 0) + 1
            by_account[credit.account_id] = by_account.get(credit.account_id, 0) + 1
            gate = overlay.by_id.get(cid) if overlay is not None else None
            if uniqueness == "AMBIGUOUS" or gate is None or not gate.ok:
                amounts.append((credit.amount_paise, cid, uniqueness))
        ranked_class = sorted(by_class.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
        ranked_account = sorted(by_account.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
        biggest = sorted(amounts, key=lambda row: -row[0])[:n]
        stats = get_batch_summary()
        return {
            "limit": n,
            "by_class": [{"exception_class": k, "n": v} for k, v in ranked_class],
            "by_account": [{"account_id": k, "n": v} for k, v in ranked_account],
            "biggest_unresolved": [
                {
                    "transaction_id": cid,
                    "bank_amount_paise": paise,
                    "bank_amount_display": format_rupees(paise),
                    "uniqueness": uniq,
                    "href": "/credit/" + cid,
                }
                for paise, cid, uniq in biggest
            ],
            "official_ambiguous": stats["ambiguous"],
            "writes_cleared": False,
            "evidence": [
                _cite("top.ambiguous", "t04.md", "dev", "ambiguous", stats["ambiguous"]),
            ],
        }
    finally:
        if conn is not None:
            conn.close()


def get_settlement_details(settlement_id: str) -> dict[str, Any]:
    sid = str(settlement_id or "").strip()
    cid = sid if sid.startswith("crd_") else sid
    split, overlay, lookup, conn = _desk()
    try:
        if split is None:
            return {"found": False, "settlement_id": sid, "error": "no_ledger", "writes_cleared": False}
        declared = tuple(split[2].get(cid) or ())
        credit = lookup.get(cid)
        if credit is None and not declared:
            return {"found": False, "settlement_id": sid, "transaction_id": cid, "error": "not_found", "writes_cleared": False}
        kinds: dict[str, int] = {}
        for row in declared:
            kinds[row.kind.value] = kinds.get(row.kind.value, 0) + row.amount_paise
        gate = overlay.by_id.get(cid) if overlay is not None else None
        return {
            "found": True,
            "settlement_id": sid,
            "transaction_id": cid,
            "row_count": len(declared),
            "kinds": {k: {"paise": v, "display": format_rupees(v)} for k, v in kinds.items()},
            "member_ids": _cap(tuple(r.item_id for r in declared)),
            "gate_a_ok": bool(gate is not None and gate.ok),
            "missing_settlement": len(declared) == 0,
            "writes_cleared": False,
            "evidence": [
                _cite("set.rows", "settlement.csv", cid, "row_count", len(declared)),
            ],
        }
    finally:
        if conn is not None:
            conn.close()


def get_match_candidates(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    recon = get_reconciliation(cid)
    forensic = credit_forensic(cid) or {}
    if not recon.get("found"):
        return recon
    return {
        "found": True,
        "transaction_id": cid,
        "n_pool": int(forensic.get("n_pool") or 0),
        "n_declared": int(forensic.get("n_declared") or 0),
        "matched_count": recon["matched_count"],
        "solution_count": recon["solution_count"],
        "uniqueness": recon["uniqueness"],
        "note": (
            "Candidates are ledger rows inside the search window. "
            "The engine does not pick a winner when uniqueness is AMBIGUOUS. "
            "Alternate member sets are not auto-selected."
        ),
        "writes_cleared": False,
        "evidence": recon.get("evidence") or [],
    }


def get_tax_breakdown(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    split, _overlay, lookup, conn = _desk()
    try:
        if lookup.get(cid) is None:
            return {"found": False, "transaction_id": cid, "error": "not_found", "writes_cleared": False}
        declared = ()
        if split is not None:
            declared = tuple(split[2].get(cid) or ())
        lines: list[dict[str, Any]] = []
        total = 0
        missing_tax = True
        for row in declared:
            if row.kind.value not in _TAX_KINDS:
                continue
            missing_tax = False
            total += row.amount_paise
            lines.append(
                {
                    "item_id": row.item_id,
                    "kind": row.kind.value,
                    "amount_paise": row.amount_paise,
                    "amount_display": format_rupees(row.amount_paise),
                }
            )
        return {
            "found": True,
            "transaction_id": cid,
            "lines": lines,
            "tax_related_paise": total,
            "tax_related_display": format_rupees(total),
            "missing_tax_lines": missing_tax,
            "writes_cleared": False,
            "evidence": [
                _cite("tax.n", "settlement.csv", cid, "tax_lines", len(lines)),
            ],
        }
    finally:
        if conn is not None:
            conn.close()


def get_audit_trail(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    _split, _overlay, lookup, conn = _desk()
    events: list[dict[str, Any]] = []
    resolution = ""
    try:
        if conn is not None:
            try:
                for (payload,) in conn.execute(
                    "SELECT payload FROM audit_entry "
                    "WHERE json_extract(payload, '$.bank_credit_id') = ? "
                    "ORDER BY seq",
                    (cid,),
                ):
                    blob = json.loads(payload)
                    events.append(
                        {
                            "uniqueness": blob.get("uniqueness"),
                            "disposition": blob.get("disposition"),
                            "exception_class": blob.get("exception_class"),
                            "residual_paise": blob.get("residual_paise"),
                            "trace_gates": blob.get("trace_gates") or [],
                        }
                    )
            except QUERY_ERRORS:
                rollback_quietly(conn)
                events = []
            try:
                row = conn.execute(
                    "SELECT resolution FROM exception_resolution WHERE bank_credit_id = ?",
                    (cid,),
                ).fetchone()
                resolution = str(row[0]) if row else ""
            except QUERY_ERRORS:
                rollback_quietly(conn)
                resolution = ""
        found = lookup.get(cid) is not None or bool(events)
        return {
            "found": found,
            "transaction_id": cid,
            "n_events": len(events),
            "events": events[-12:],
            "human_resolution": resolution,
            "human_resolution_writes_cleared": False,
            "writes_cleared": False,
            "evidence": [
                _cite("audit.n", "audit_entry", cid, "n_events", len(events)),
            ],
        }
    finally:
        if conn is not None:
            conn.close()


def get_transaction_evidence(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    txn = get_transaction(cid)
    recon = get_reconciliation(cid)
    settlement = get_settlement_details(cid)
    tax = get_tax_breakdown(cid)
    audit = get_audit_trail(cid)
    candidates = get_match_candidates(cid)
    forensic = credit_forensic(cid) or {}
    if not txn.get("found") and not recon.get("found"):
        return {
            "found": False,
            "transaction_id": cid,
            "error": "not_found",
            "writes_cleared": False,
        }
    checks = [
        {"label": "Amount", "ok": True, "value": txn.get("bank_amount_display")},
        {
            "label": "Residual",
            "ok": recon.get("residual_paise") == 0,
            "value": recon.get("residual_display"),
        },
        {
            "label": "Settlement",
            "ok": not settlement.get("missing_settlement"),
            "value": "present" if not settlement.get("missing_settlement") else "missing",
        },
        {
            "label": "Member IDs",
            "ok": int(recon.get("matched_count") or 0) > 0,
            "value": recon.get("matched_count"),
        },
        {
            "label": "Reference",
            "ok": bool(txn.get("utr")),
            "value": txn.get("utr") or "none",
        },
        {
            "label": "Tax lines",
            "ok": not tax.get("missing_tax_lines"),
            "value": tax.get("tax_related_display"),
        },
        {
            "label": "Uniqueness",
            "ok": recon.get("uniqueness") == "UNIQUE",
            "value": recon.get("uniqueness"),
        },
        {
            "label": "Auto-clear",
            "ok": False,
            "value": "NO" if not recon.get("auto_cleared") else "YES",
        },
    ]
    refs: list[dict[str, Any]] = []
    for blob in (txn, recon, settlement, tax, audit):
        refs.extend(list(blob.get("evidence") or []))
    packed = {
        "found": True,
        "transaction_id": cid,
        "transaction": txn,
        "reconciliation": recon,
        "settlement": settlement,
        "tax": tax,
        "audit": audit,
        "candidates": candidates,
        "forensic": {
            "bucket": forensic.get("bucket"),
            "recovery": forensic.get("recovery"),
            "recovery_why": forensic.get("recovery_why"),
            "n_pool": forensic.get("n_pool"),
            "n_declared": forensic.get("n_declared"),
            "ledger_miss": forensic.get("ledger_miss"),
            "window_miss": forensic.get("window_miss"),
            "fp_ok": forensic.get("fp_ok"),
        },
        "checks": checks,
        "decision": recon.get("status"),
        "writes_cleared": False,
        "evidence": refs,
    }
    from residual_zero.qa.evidence_ops import evidence_level, next_best_action
    from residual_zero.qa.evidence_validate import investigate

    inv = investigate(cid)
    packed["investigation"] = inv
    packed["level"] = evidence_level(cid, inv)
    packed["next_best_action"] = next_best_action(cid, recon, packed["forensic"])
    return packed


def call_finance_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a named read-only tool. Unknown names fail closed. Never writes."""
    tool = str(name or "").strip()
    args = dict(arguments or {})
    if tool not in TOOL_NAMES:
        return {"ok": False, "error": "unknown_tool", "tool": tool, "writes_cleared": False}
    if tool == "get_transaction":
        return get_transaction(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_reconciliation":
        return get_reconciliation(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_batch_summary" or tool == "get_reconciliation_statistics":
        return get_batch_summary()
    if tool == "get_exceptions":
        raw = args.get("exception_type")
        return get_exceptions(str(raw) if raw is not None else None)
    if tool == "get_unreconciled_amount":
        return get_unreconciled_amount()
    if tool == "get_ambiguous_transactions":
        return get_ambiguous_transactions(args.get("limit") if isinstance(args.get("limit"), int) else None)
    if tool == "get_unmatched_transactions":
        return get_unmatched_transactions(args.get("limit") if isinstance(args.get("limit"), int) else None)
    if tool == "get_verified_transactions":
        return get_verified_transactions(args.get("limit") if isinstance(args.get("limit"), int) else None)
    if tool == "get_settlement_details":
        return get_settlement_details(str(args.get("settlement_id") or args.get("transaction_id") or ""))
    if tool == "get_match_candidates":
        return get_match_candidates(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_tax_breakdown":
        return get_tax_breakdown(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_audit_trail":
        return get_audit_trail(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_transaction_evidence":
        return get_transaction_evidence(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_top_exceptions":
        lim = args.get("limit")
        return get_top_exceptions(lim if isinstance(lim, int) else 10)
    from residual_zero.qa.evidence_ops import (
        evidence_graph,
        evidence_level,
        explorer_query,
        next_best_action,
        potentially_recoverable,
        review_priority,
        root_cause,
        exception_intelligence,
    )
    from residual_zero.qa.evidence_validate import investigate

    if tool == "extract_evidence" or tool == "validate_extraction" or tool == "investigate_transaction":
        return investigate(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_evidence_graph":
        return evidence_graph(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_evidence_level":
        return evidence_level(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_review_priority":
        return review_priority(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_next_best_action":
        return next_best_action(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_root_cause":
        return root_cause()
    if tool == "get_potentially_recoverable":
        lim = args.get("limit")
        return potentially_recoverable(lim if isinstance(lim, int) else 20)
    if tool == "explorer_query":
        lim = args.get("limit")
        return explorer_query(str(args.get("kind") or args.get("query") or ""), lim if isinstance(lim, int) else 20)
    if tool == "exception_intelligence":
        return exception_intelligence(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "get_exposure_queue":
        from residual_zero.console.app import _overlay, _split
        from residual_zero.console.close_ops import corpus_as_of
        from residual_zero.console.ops_pack import exposure_queue

        split = _split()
        lim = args.get("limit")
        if split is None:
            return {"n": 0, "rows": [], "writes_cleared": False}
        return exposure_queue(
            split[1],
            _overlay(),
            corpus_as_of(split[1]),
            limit=lim if isinstance(lim, int) else 8,
        )
    if tool == "get_duplicate_utrs":
        from residual_zero.console.app import _split
        from residual_zero.console.ops_pack import duplicate_utr_rows

        split = _split()
        if split is None:
            return {"n": 0, "rows": [], "writes_cleared": False}
        return duplicate_utr_rows(split[1])
    if tool == "get_standup":
        from residual_zero.console.app import app as _app

        for route in _app.routes:
            if getattr(route, "path", "") == "/standup.md":
                return {
                    "ok": True,
                    "markdown": route.endpoint().body.decode("utf-8"),
                    "writes_cleared": False,
                }
        return {"ok": False, "error": "standup_unwired", "writes_cleared": False}
    if tool == "get_proof_explorer":
        from residual_zero.console.proof_explorer import proof_explorer

        return proof_explorer(str(args.get("transaction_id") or args.get("credit_id") or ""))
    if tool == "explain_candidate_rejection":
        from residual_zero.console.proof_explorer import explain_candidate_rejection

        return explain_candidate_rejection(
            str(args.get("transaction_id") or args.get("credit_id") or ""),
            str(args.get("candidate_id") or args.get("member_id") or ""),
        )
    from residual_zero.qa.investigate_tools import call_investigate_tool

    extra = call_investigate_tool(tool, args)
    if extra is not None:
        return extra
    return {"ok": False, "error": "unwired", "tool": tool, "writes_cleared": False}
