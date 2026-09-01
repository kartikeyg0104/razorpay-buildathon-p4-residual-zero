"""Evidence graph, levels, recoverable queue, priority, explorer, root cause.

LEVEL 4/5 may influence coverage. LEVEL 0–3 never count as reconciled.
"""

from __future__ import annotations

from typing import Any

from residual_zero.console.facts import credit_forensic, forensic_summary, t04_fields
from residual_zero.money import format_rupees
from residual_zero.qa.evidence_validate import investigate
from residual_zero.qa.finance_tools import get_reconciliation, get_top_exceptions


def evidence_graph(transaction_id: str, investigation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Structured edges plus verified extracted identifiers. No unsupported AI edges."""
    from residual_zero.console.app import _credit_lookup, _overlay, _split

    lookup = _credit_lookup()
    credit = lookup.get(transaction_id)
    split = _split()
    overlay = _overlay()
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    if credit is None:
        return {"found": False, "transaction_id": transaction_id, "nodes": [], "edges": [], "writes_cleared": False}
    nodes.append({"id": transaction_id, "kind": "BANK_CREDIT"})
    nodes.append({"id": credit.account_id, "kind": "ACCOUNT"})
    edges.append({"src": transaction_id, "rel": "account", "dst": credit.account_id})
    nodes.append({"id": credit.value_date.isoformat(), "kind": "DATE"})
    edges.append({"src": transaction_id, "rel": "date", "dst": credit.value_date.isoformat()})
    if credit.utr:
        nodes.append({"id": credit.utr, "kind": "REFERENCE"})
        edges.append({"src": transaction_id, "rel": "reference", "dst": credit.utr})
    declared = ()
    if split is not None:
        declared = tuple(split[2].get(transaction_id) or ())
    if declared:
        nodes.append({"id": "set:" + transaction_id, "kind": "SETTLEMENT"})
        edges.append({"src": transaction_id, "rel": "settlement", "dst": "set:" + transaction_id})
        for row in declared[:40]:
            nodes.append({"id": row.item_id, "kind": "LEDGER_ITEM"})
            edges.append({"src": "set:" + transaction_id, "rel": "ledger_item", "dst": row.item_id})
            nodes.append({"id": row.kind.value, "kind": "KIND"})
            edges.append({"src": row.item_id, "rel": "kind", "dst": row.kind.value})
    blob = investigation if investigation is not None else investigate(transaction_id)
    for row in blob.get("validated_fields") or []:
        if not row.get("verified"):
            continue
        value = str(row.get("value") or "")
        field = str(row.get("field") or "")
        if not value:
            continue
        nodes.append({"id": value, "kind": "EXTRACTED_" + field.upper()})
        edges.append({"src": transaction_id, "rel": "extracted_" + field, "dst": value})
    gate = overlay.by_id.get(transaction_id) if overlay is not None else None
    v2 = []
    from residual_zero.console.proof_explorer import graph_edges_v2

    v2 = graph_edges_v2(transaction_id)
    for row in blob.get("validated_fields") or []:
        if row.get("verified"):
            continue
        value = str(row.get("value") or "")
        field = str(row.get("field") or "")
        if not value:
            continue
        v2.append(
            {
                "source_record_id": transaction_id,
                "source_field": field,
                "target_record_id": value,
                "target_field": field,
                "relationship_type": "extracted",
                "rel": "extracted",
                "method": "LLM",
                "verified": False,
                "evidence_level": 1,
            }
        )
    return {
        "found": True,
        "transaction_id": transaction_id,
        "nodes": nodes,
        "edges": edges,
        "edges_v2": v2,
        "gate_a_ok": bool(gate is not None and gate.ok),
        "writes_cleared": False,
        "note": "LLM edges if any would be method=LLM verified=false. This graph is deterministic.",
    }


def evidence_level(transaction_id: str, investigation: dict[str, Any] | None = None) -> dict[str, Any]:
    recon = get_reconciliation(transaction_id)
    blob = investigation if investigation is not None else investigate(transaction_id)
    forensic = credit_forensic(transaction_id) or {}
    verified_n = int(blob.get("verified_field_count") or 0)
    extracted_n = len(blob.get("validated_fields") or [])
    new_rel = any(
        r.get("relationship") == "DECLARED_LOOKUP" for r in (blob.get("validated_fields") or [])
    )
    declared = int(forensic.get("n_declared") or recon.get("matched_count") or 0)
    residual0 = recon.get("found") and recon.get("residual_paise") == 0
    unique = recon.get("uniqueness") == "UNIQUE"
    level = 0
    if extracted_n:
        level = 1
    if verified_n:
        level = 2
    if declared > 0:
        level = 3
    if residual0:
        level = 4
    if residual0 and unique:
        level = 5
    label = {
        0: "NO_EVIDENCE",
        1: "AI_CANDIDATE",
        2: "AI_VERIFIED_LOOKUP",
        3: "EXPLICIT_SOURCE",
        4: "EQUATION_VERIFIED",
        5: "UNIQUE_VERIFIED",
    }[level]
    recoverable = (new_rel or int((blob.get("recon") or {}).get("extracted_added") or 0) > 0) and not residual0
    return {
        "transaction_id": transaction_id,
        "level": level,
        "label": label,
        "potentially_recoverable": recoverable,
        "residual_zero": bool(residual0),
        "uniqueness": recon.get("uniqueness"),
        "extracted_n": extracted_n,
        "verified_n": verified_n,
        "declared_n": declared,
        "writes_cleared": False,
        "note": "Only LEVEL 4/5 influence reconciliation coverage. LEVEL 1–3 are evidence only.",
    }


def review_priority(transaction_id: str) -> dict[str, Any]:
    recon = get_reconciliation(transaction_id)
    if not recon.get("found"):
        return {"found": False, "transaction_id": transaction_id, "writes_cleared": False}
    forensic = credit_forensic(transaction_id) or {}
    amount = int(recon.get("bank_amount_paise") or 0)
    solutions = int(recon.get("solution_count") or 0)
    missing_set = int(forensic.get("n_declared") or 0) == 0
    missing_ledger = int(forensic.get("ledger_miss") or 0) > 0
    band = "LOW"
    if amount >= 10000000 or solutions >= 2:
        band = "MEDIUM"
    if missing_set or missing_ledger or amount >= 50000000:
        band = "HIGH"
    if recon.get("uniqueness") == "AMBIGUOUS" and amount >= 1000000:
        band = "HIGH"
    action = next_best_action(transaction_id, recon, forensic)
    age = int(forensic.get("age_days") or 0)
    missing_n = (1 if missing_set else 0) + (1 if missing_ledger else 0)
    score = abs(amount) * (age + 1) + (solutions * 1000) + (missing_n * 1000000)
    factors = [
        {"factor": "absolute_amount_paise", "value": amount},
        {"factor": "age_days", "value": age},
        {"factor": "solution_count", "value": solutions},
        {"factor": "missing_source_count", "value": missing_n},
        {"factor": "uniqueness", "value": recon.get("uniqueness")},
    ]
    return {
        "found": True,
        "transaction_id": transaction_id,
        "priority": band,
        "score": score,
        "factors": factors,
        "financial_decision": False,
        "amount_display": recon.get("bank_amount_display"),
        "solution_count": solutions,
        "settlement_available": not missing_set,
        "ledger_miss": int(forensic.get("ledger_miss") or 0),
        "recommendation": action["action"],
        "writes_cleared": False,
        "not_ai_confidence": True,
    }


def next_best_action(
    transaction_id: str,
    recon: dict[str, Any] | None = None,
    forensic: dict[str, Any] | None = None,
) -> dict[str, str]:
    recon = recon if recon is not None else get_reconciliation(transaction_id)
    forensic = forensic if forensic is not None else (credit_forensic(transaction_id) or {})
    uniqueness = str(recon.get("uniqueness") or "")
    if uniqueness == "AMBIGUOUS":
        action = "Review competing candidate combinations. Do not auto-select a subset."
    elif int(forensic.get("ledger_miss") or 0) > 0:
        action = "Locate missing ledger record named by the settlement. Do not fabricate it."
    elif int(forensic.get("n_declared") or 0) == 0:
        action = "Retrieve settlement report. No declared rows are on disk for this credit."
    elif uniqueness == "NONE_FOUND":
        action = "Inspect missing refund/settlement rows. Search found no residual-zero subset."
    elif int(forensic.get("window_miss") or 0) > 0:
        action = "Review settlement-specific date evidence. Some named members sit outside the production window."
    elif str(forensic.get("recovery") or "") == "RATE_MISMATCH":
        action = "Re-derive fee/GST/withholding against the rate table."
    elif recon.get("residual_paise") not in (0, None):
        action = (
            "AI-identified evidence did not prove the bank amount. Residual "
            f"{recon.get('residual_display')}. No reconciliation was established."
        )
    else:
        action = "Leave flagged. Residual-zero is not auto-clear. Overlay does not write CLEARED."
    return {"transaction_id": transaction_id, "action": action, "writes_cleared": False}


def exception_intelligence(transaction_id: str) -> dict[str, Any]:
    inv = investigate(transaction_id)
    if not inv.get("found"):
        return inv
    recon = get_reconciliation(transaction_id)
    level = evidence_level(transaction_id, inv)
    graph = evidence_graph(transaction_id, inv)
    prio = review_priority(transaction_id)
    from residual_zero.qa.playbooks import playbook_for, terminal_state

    forensic = credit_forensic(transaction_id) or {}
    term = terminal_state(
        str(recon.get("uniqueness") or ""),
        residual_paise=recon.get("residual_paise") if isinstance(recon.get("residual_paise"), int) else None,
        missing_ledger=int(forensic.get("ledger_miss") or 0) > 0,
        missing_settlement=int(forensic.get("n_declared") or 0) == 0,
    )
    recon_try = inv.get("recon") or {}
    residual = recon_try.get("residual_display") or recon.get("residual_display")
    result = "EVIDENCE_ONLY"
    if recon_try.get("ok") and recon_try.get("extracted_added"):
        result = "NEW_PROVABLE_MATCH"
    elif recon.get("residual_paise") == 0:
        result = "ALREADY_RESIDUAL_ZERO"
    elif recon_try.get("status") == "NOT_RECONCILED":
        result = "NOT_RECONCILED"
    summary = (
        f"Transaction {transaction_id}\n"
        f"Amount: {recon.get('bank_amount_display')}\n"
        f"Status: {recon.get('status')}\n"
        f"Evidence level: {level['level']} {level['label']}\n"
        f"Verified extracted fields: {inv.get('verified_field_count')}\n"
        f"Settlement rows: {recon.get('matched_count')}\n"
        f"Solutions: {recon.get('solution_count')}\n"
        f"Residual: {residual}\n"
        f"Verification: {'PASS' if recon_try.get('ok') else 'FAIL_OR_NOT_PROVEN'}\n"
        f"Result: {result}\n"
        f"Next: {prio.get('recommendation')}\n"
        "The AI finance controller does not write CLEARED."
    )
    if recon_try.get("status") == "NOT_RECONCILED" and recon_try.get("residual_display"):
        summary += (
            f"\nAI identified candidate evidence, but deterministic reconciliation produced a residual of "
            f"{recon_try['residual_display']}. No reconciliation was established."
        )
    from residual_zero.qa.playbooks import playbook_for, terminal_state

    forensic = credit_forensic(transaction_id) or {}
    term = terminal_state(
        str(recon.get("uniqueness") or ""),
        residual_paise=recon.get("residual_paise") if isinstance(recon.get("residual_paise"), int) else None,
        missing_ledger=int(forensic.get("ledger_miss") or 0) > 0,
        missing_settlement=int(forensic.get("n_declared") or 0) == 0,
    )
    kind = "AMBIGUOUS" if recon.get("uniqueness") == "AMBIGUOUS" else (
        "MISSING_RECORD" if int(forensic.get("ledger_miss") or 0) > 0 else "NONE_FOUND"
    )
    return {
        "found": True,
        "transaction_id": transaction_id,
        "summary": summary,
        "level": level,
        "graph": graph,
        "priority": prio,
        "investigation": inv,
        "result": result,
        "terminal": term,
        "playbook": playbook_for(kind),
        "writes_cleared": False,
        "matched": False,
        "cleared": False,
    }


def potentially_recoverable(limit: int = 20) -> dict[str, Any]:
    from residual_zero.console.app import _credit_lookup, _overlay

    lookup = _credit_lookup()
    overlay = _overlay()
    rows: list[dict[str, Any]] = []
    n = 0
    for cid, credit in lookup.items():
        gate = overlay.by_id.get(cid) if overlay is not None else None
        if gate is not None and gate.ok:
            continue
        forensic = credit_forensic(cid) or {}
        inv = investigate(cid)
        recon = inv.get("recon") or {}
        new_rel = any(
            r.get("relationship") == "DECLARED_LOOKUP" for r in (inv.get("validated_fields") or [])
        )
        added = int(recon.get("extracted_added") or 0)
        if not new_rel and added == 0:
            continue
        n += 1
        if len(rows) < limit:
            rows.append(
                {
                    "transaction_id": cid,
                    "amount_display": format_rupees(credit.amount_paise),
                    "extracted": len(inv.get("validated_fields") or []),
                    "verified": int(inv.get("verified_field_count") or 0),
                    "declared": int(forensic.get("n_declared") or 0),
                    "foreign_hits": int(recon.get("foreign_hits") or 0),
                    "extracted_added": added,
                    "href": "/credit/" + cid,
                }
            )
    return {
        "n": n,
        "limit": limit,
        "rows": rows,
        "note": "POTENTIALLY_RECOVERABLE is not a match. Residual is not proven.",
        "writes_cleared": False,
    }


def root_cause() -> dict[str, Any]:
    fs = forensic_summary()
    t04 = t04_fields("dev")
    test = t04_fields("test")
    buckets = fs.get("buckets") if isinstance(fs.get("buckets"), dict) else {}
    n_scored = int(fs.get("n_scored") or t04.get("n_scored") or 0)
    rz = int(fs.get("residual_zero") or 0)
    ambiguous = int(t04.get("ambiguous") or 0)
    none_found = int(t04.get("none_found") or 0)
    no_declared = int(fs.get("no_declared") or 0)
    window = int(buckets.get("NO_DECLARED_WINDOW_MISS") or 0)
    missing = int(buckets.get("NO_DECLARED_TRUTH_MISSING") or 0)
    class8 = int(buckets.get("DECLARED_NE_TRUTH_VERIFY_FAIL") or 0)
    top = get_top_exceptions(10)
    text = (
        f"{n_scored} scored credits. Residual-zero {rz}/{n_scored}. "
        f"Search ambiguous {ambiguous}. None found {none_found}. "
        f"{no_declared} have no settlement rows. "
        f"Dominant blockers: missing settlement / date-window population {window}, "
        f"missing ledger ids {missing}, search-path ambiguity "
        f"{int(buckets.get('NO_DECLARED_SEARCH_PATH') or 0)}, "
        f"corrupted dual-source {class8}. "
        "Most unresolved transactions are not caused by search failure. "
        "The dominant blockers are missing settlement records and non-unique candidate combinations. "
        "Official test residual-zero "
        f"{test.get('residual-zero')}, ambiguous {test.get('ambiguous')}, none_found {test.get('none_found')}. "
        "Search auto-clear 0. Overlay does not write CLEARED."
    )
    return {
        "text": text,
        "n_scored": n_scored,
        "residual_zero": f"{rz}/{n_scored}" if n_scored else t04.get("residual-zero"),
        "ambiguous": ambiguous,
        "none_found": none_found,
        "no_declared": no_declared,
        "window_miss": window,
        "ledger_miss": missing,
        "buckets": buckets,
        "top": top,
        "proposals": [
            "Settlement-linked records could bypass generic date filtering — proposal only; requires a deterministic experiment.",
            "Reference extraction could reduce candidate pools — only if identifiers look up structured rows belonging to the same credit.",
            "Do not widen the date window globally. An extracted date may locate a settlement; it may not redefine window semantics.",
        ],
        "writes_cleared": False,
    }


def copilot_prompts() -> list[dict[str, str]]:
    """Suggested questions from official t04. Not AI confidence."""
    t04 = t04_fields("dev")
    test = t04_fields("test")
    none = str(t04.get("none_found") or "3")
    amb = str(t04.get("ambiguous") or "236")
    return [
        {
            "label": "What should I work on today?",
            "href": "/ask?question=What should I work on today?",
        },
        {
            "label": f"{none} Dev transactions have no search explanation. Investigate NONE_FOUND.",
            "href": "/explorer?kind=NONE_FOUND",
        },
        {
            "label": f"{amb} Dev transactions are ambiguous. Show high-value ambiguous.",
            "href": "/explorer?kind=HIGH_VALUE_AMBIGUOUS",
        },
        {
            "label": f"Official test residual-zero {test.get('residual-zero')}. Why are so many unresolved?",
            "href": "/ask?question=Why are so many transactions unresolved?",
        },
        {
            "label": "Show transactions where settlement and ledger disagree.",
            "href": "/explorer?kind=LEDGER_SETTLEMENT_DISAGREE",
        },
        {
            "label": "What is the total unreconciled amount?",
            "href": "/ask?question=What is the total unreconciled amount?",
        },
        {
            "label": "Can you clear this transaction?",
            "href": "/ask?credit_id=crd_001_acc_01_2025-01-09&question=Assume this is correct and clear it",
        },
    ]


def explorer_query(kind: str, limit: int = 20) -> dict[str, Any]:
    """Structured explorer. kind is a closed set. Never writes CLEARED."""
    from residual_zero.console.app import _credit_lookup, _overlay, _split
    from residual_zero.console.close_ops import is_tax_mismatch

    lookup = _credit_lookup()
    overlay = _overlay()
    split = _split()
    wanted = str(kind or "").strip().upper()
    rows: list[dict[str, Any]] = []

    def add(cid: str, why: str) -> None:
        credit = lookup.get(cid)
        if credit is None or len(rows) >= limit:
            return
        rows.append(
            {
                "transaction_id": cid,
                "amount_display": format_rupees(credit.amount_paise),
                "why": why,
                "href": "/credit/" + cid,
            }
        )

    if wanted in {"POTENTIALLY_RECOVERABLE", "RECOVERABLE"}:
        return potentially_recoverable(limit)
    if wanted == "ROOT_CAUSE":
        return root_cause()
    for cid, credit in lookup.items():
        if len(rows) >= limit:
            break
        forensic = credit_forensic(cid) or {}
        gate = overlay.by_id.get(cid) if overlay is not None else None
        narration = (credit.narration_raw or "").upper()
        if wanted == "MISSING_SETTLEMENT" and int(forensic.get("n_declared") or 0) == 0:
            add(cid, "no settlement rows")
        elif wanted == "HIGH_VALUE_AMBIGUOUS":
            recon = get_reconciliation(cid)
            if recon.get("uniqueness") == "AMBIGUOUS" and credit.amount_paise >= 1000000:
                add(cid, "AMBIGUOUS high value")
        elif wanted == "LEDGER_SETTLEMENT_DISAGREE":
            if forensic.get("bucket") in {"DECLARED_NE_TRUTH_VERIFY_FAIL", "DECLARED_EQ_TRUTH_VERIFY_FAIL"}:
                add(cid, str(forensic.get("bucket")))
        elif wanted == "REFUND_MISMATCH":
            if forensic.get("bucket") == "DECLARED_NE_TRUTH_VERIFY_FAIL":
                add(cid, "declared vs ledger disagree")
        elif wanted == "DESCRIPTION_HAS_SETTLEMENT_WORD":
            if "SETTLEMENT" in narration and (gate is None or not gate.ok):
                add(cid, "narration mentions SETTLEMENT")
        elif wanted == "UNVERIFIED_EXTRACT":
            inv = investigate(cid)
            if inv.get("found") and inv.get("extraction", {}).get("ok") and int(inv.get("verified_field_count") or 0) == 0:
                add(cid, "extracted but unverified")
        elif wanted == "NONE_FOUND":
            recon = get_reconciliation(cid)
            if recon.get("uniqueness") == "NONE_FOUND":
                add(cid, "NONE_FOUND")
        elif wanted == "MISSING_LEDGER":
            if int(forensic.get("ledger_miss") or 0) > 0:
                add(cid, f"ledger_miss {forensic.get('ledger_miss')}")
        elif wanted == "AMBIGUOUS":
            recon = get_reconciliation(cid)
            if recon.get("uniqueness") == "AMBIGUOUS":
                add(cid, "AMBIGUOUS — not a clear")
        elif wanted in {"UNRESOLVED", "UNMATCHED"}:
            recon = get_reconciliation(cid)
            if recon.get("uniqueness") == "NONE_FOUND":
                add(cid, "NONE_FOUND")
            elif int(forensic.get("n_declared") or 0) == 0:
                add(cid, "no settlement rows")
            elif int(forensic.get("ledger_miss") or 0) > 0:
                add(cid, f"ledger_miss {forensic.get('ledger_miss')}")
        elif wanted == "TAX_MISMATCH":
            declared = tuple(split[2].get(cid) or ()) if split is not None else ()
            if is_tax_mismatch(gate, declared):
                add(cid, f"rate re-derive failed · {gate.n_deltas} line deltas")
    return {"kind": wanted, "n": len(rows), "rows": rows, "writes_cleared": False}
