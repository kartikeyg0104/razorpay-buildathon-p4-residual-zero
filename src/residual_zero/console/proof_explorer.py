"""Proof Explorer: two residual-zero explanations, never a winner.

Display-only. Overlay does not write CLEARED. Selecting A or B is unsupported.
"""

from __future__ import annotations

from typing import Any

from residual_zero.money import format_rupees
from residual_zero.solver.alt_diff import diff_sets, render_diff

THESIS_AMBIGUOUS = (
    "Both explanations satisfy the financial equation. "
    "No authoritative evidence distinguishes them. Human review is required."
)


def _brute_index_subsets(rupees: tuple[int, ...], target: int, cap: int = 3) -> list[tuple[int, ...]]:
    n = len(rupees)
    found: list[tuple[int, ...]] = []
    limit = 1
    for _ in range(n):
        limit *= 2
    for mask in range(1, limit):
        total = 0
        idxs: list[int] = []
        bit = 1
        for i in range(n):
            if mask & bit:
                total += rupees[i]
                idxs.append(i)
            bit *= 2
        if total == target:
            found.append(tuple(idxs))
            if len(found) >= cap:
                break
    return found


def _edge(
    src: str,
    src_field: str,
    dst: str,
    dst_field: str,
    rel: str,
    *,
    verified: bool,
    level: int,
    method: str = "DETERMINISTIC",
) -> dict[str, Any]:
    return {
        "source_record_id": src,
        "source_field": src_field,
        "target_record_id": dst,
        "target_field": dst_field,
        "relationship_type": rel,
        "rel": rel,
        "method": method,
        "verified": verified,
        "evidence_level": level,
    }


def mixed_proof(credit_id: str) -> dict[str, Any] | None:
    from residual_zero.console.mixed_desk import SPECS, is_mixed_credit, mixed_by_id

    if not is_mixed_credit(credit_id):
        return None
    spec = next((s for s in SPECS if s.credit_id == credit_id), None)
    row = mixed_by_id().get(credit_id)
    if spec is None or row is None:
        return None
    subsets = _brute_index_subsets(spec.rupees, spec.target_rupees, cap=3)
    ids = tuple(f"{spec.credit_id}_i{i:02d}" for i in range(len(spec.rupees)))
    sols = []
    for n, idxs in enumerate(subsets[:2], start=1):
        members = tuple(ids[i] for i in idxs)
        total = sum(spec.rupees[i] for i in idxs) * 100
        sols.append(
            {
                "name": "A" if n == 1 else "B",
                "matched_ids": members,
                "n": len(members),
                "total_display": format_rupees(total),
                "residual_display": "0.00",
                "residual_paise": 0,
                "settlement": "constructed mixed desk",
                "member": ",".join(members),
                "date": "2025-01-15",
                "reference": f"UTR_MIX_{credit_id[-8:].upper()}",
            }
        )
    a_ids = tuple(sols[0]["matched_ids"]) if sols else ()
    b_ids = tuple(sols[1]["matched_ids"]) if len(sols) > 1 else ()
    diff = diff_sets(a_ids, b_ids) if b_ids else diff_sets(a_ids, a_ids)
    n_sol = len(subsets)
    decision = "UNIQUE" if n_sol == 1 else ("AMBIGUOUS" if n_sol >= 2 else "NONE_FOUND")
    distinguishing = "NONE" if n_sol >= 2 else "SINGLE_EXPLANATION"
    names = ("BANK", "SETTLEMENT", "LEDGER", "TAX", "REFUND")
    has_refund = any(a < 0 for a in spec.rupees)
    flags = {
        "BANK": True,
        "SETTLEMENT": True,
        "LEDGER": True,
        "TAX": False,
        "REFUND": has_refund,
    }

    def cell(a: str, b: str) -> str:
        if a == b:
            return "—"
        if flags[a] and flags[b]:
            return "✓"
        return "?"

    return {
        "found": True,
        "corpus": "CONSTRUCTED_MIXED",
        "transaction_id": credit_id,
        "bank_display": row.amount,
        "bank_amount_paise": row.amount_paise,
        "solution_count": n_sol,
        "uniqueness": row.uniqueness,
        "solutions": sols,
        "difference": {
            "only_a": diff.only_a,
            "only_b": diff.only_b,
            "common": len(diff.shared),
            "shared": diff.shared,
            "symmetric_difference_size": diff.symmetric_difference_size,
            "text": render_diff(diff),
        },
        "distinguishing_authoritative_evidence": distinguishing,
        "decision": decision,
        "thesis": THESIS_AMBIGUOUS if n_sol >= 2 else "One explanation on this constructed pool.",
        "choose_one": False,
        "writes_cleared": False,
        "matrix": {a: {b: cell(a, b) for b in names} for a in names},
        "note": "Constructed mixed desk. Not official Track 04. Overlay does not write CLEARED.",
    }


def official_proof(credit_id: str) -> dict[str, Any]:
    from residual_zero.config import load_solver_config
    from residual_zero.console.app import _credit_lookup, _overlay, _split
    from residual_zero.console.ops import greedy_versus_declared
    from residual_zero.qa.finance_tools import get_reconciliation

    cid = str(credit_id or "").strip()
    split = _split()
    overlay = _overlay()
    lookup = _credit_lookup()
    credit = lookup.get(cid)
    recon = get_reconciliation(cid)
    if credit is None:
        return {"found": False, "transaction_id": cid, "writes_cleared": False, "error": "not_found"}
    declared = tuple(r.item_id for r in (split[2].get(cid) or ())) if split is not None else ()
    gate = overlay.by_id.get(cid) if overlay is not None else None
    greedy_ids: tuple[str, ...] = ()
    greedy_would = False
    if split is not None:
        hit = greedy_versus_declared(credit, split[0], load_solver_config(), declared)
        greedy_ids = hit.member_ids
        greedy_would = hit.would_clear
    residual_a = gate.residual_paise if gate is not None else None
    sols = [
        {
            "name": "A",
            "label": "DECLARED",
            "matched_ids": declared[:40],
            "n": len(declared),
            "total_display": format_rupees(credit.amount_paise - residual_a) if residual_a is not None else None,
            "residual_display": format_rupees(residual_a) if residual_a is not None else None,
            "residual_paise": residual_a,
            "settlement": "present" if declared else "missing",
            "member": str(len(declared)),
            "date": credit.value_date.isoformat(),
            "reference": credit.utr or "",
        }
    ]
    sols.append(
        {
            "name": "B",
            "label": "A2_GREEDY",
            "matched_ids": greedy_ids[:40],
            "n": len(greedy_ids),
            "total_display": None,
            "residual_display": "within ε" if greedy_would else "not a unique search set",
            "residual_paise": None,
            "settlement": "greedy largest-first, not uniqueness",
            "member": str(len(greedy_ids)),
            "date": credit.value_date.isoformat(),
            "reference": credit.utr or "",
            "enumerated": bool(greedy_ids),
            "note": (
                "A2 greedy is a rival explanation, not search UNIQUE. "
                "Live AMBIGUOUS pools are not auto-enumerated into a winner."
            ),
        }
    )
    diff = diff_sets(declared, greedy_ids)
    uniqueness = str(recon.get("uniqueness") or "AMBIGUOUS")
    distinguishing = "NONE"
    if diff.symmetric_difference_size:
        distinguishing = "DECLARED_VS_GREEDY"
    return {
        "found": True,
        "corpus": "OFFICIAL",
        "transaction_id": cid,
        "bank_display": format_rupees(credit.amount_paise),
        "bank_amount_paise": credit.amount_paise,
        "solution_count": recon.get("solution_count"),
        "uniqueness": uniqueness,
        "solutions": sols,
        "difference": {
            "only_a": diff.only_a[:20],
            "only_b": diff.only_b[:20],
            "common": len(diff.shared),
            "shared": diff.shared[:20],
            "symmetric_difference_size": diff.symmetric_difference_size,
            "text": render_diff(diff),
        },
        "distinguishing_authoritative_evidence": distinguishing if uniqueness != "AMBIGUOUS" else "NONE",
        "decision": uniqueness,
        "thesis": THESIS_AMBIGUOUS if uniqueness == "AMBIGUOUS" else "Uniqueness is not AMBIGUOUS on this credit.",
        "choose_one": False,
        "writes_cleared": False,
        "greedy_would_clear": greedy_would,
        "matrix": source_agreement_matrix(cid).get("matrix"),
        "note": "Selecting one residual-zero subset without uniqueness UNIQUE would be an unsupported assumption.",
    }


def proof_explorer(credit_id: str) -> dict[str, Any]:
    mixed = mixed_proof(credit_id)
    if mixed is not None:
        return mixed
    return official_proof(credit_id)


def explain_candidate_rejection(transaction_id: str, candidate_id: str) -> dict[str, Any]:
    """Observable deterministic reasons only. Never an LLM decision."""
    from residual_zero.console.app import _credit_lookup, _overlay, _split
    from residual_zero.console.mixed_desk import is_mixed_credit, mixed_by_id
    from residual_zero.qa.finance_tools import get_reconciliation

    cid = str(transaction_id or "").strip()
    cand = str(candidate_id or "").strip()
    reasons: list[str] = []
    evidence: list[str] = []
    accepted = False
    if is_mixed_credit(cid):
        row = mixed_by_id().get(cid)
        blob = mixed_proof(cid) or {}
        members = {m for s in blob.get("solutions") or [] for m in s.get("matched_ids") or ()}
        if row is None:
            reasons.append("missing ledger record")
        elif cand not in members and cand:
            reasons.append("uniqueness conflict")
            evidence.append(cand)
        if row is not None and row.uniqueness == "AMBIGUOUS":
            reasons.append("uniqueness conflict")
        if row is not None and row.uniqueness == "NONE_FOUND":
            reasons.append("residual non-zero")
        return {
            "candidate_id": cand,
            "transaction_id": cid,
            "accepted": False,
            "reasons": reasons or ["uniqueness conflict"],
            "evidence_ids": evidence,
            "writes_cleared": False,
        }
    lookup = _credit_lookup()
    credit = lookup.get(cid)
    recon = get_reconciliation(cid)
    if credit is None:
        return {
            "candidate_id": cand,
            "transaction_id": cid,
            "accepted": False,
            "reasons": ["missing ledger record"],
            "evidence_ids": [],
            "writes_cleared": False,
            "error": "not_found",
        }
    split = _split()
    overlay = _overlay()
    declared = {r.item_id for r in (split[2].get(cid) or ())} if split is not None else set()
    ledger = split[3] if split is not None else {}
    gate = overlay.by_id.get(cid) if overlay is not None else None
    if cand and cand not in ledger and cand not in declared:
        reasons.append("missing ledger record")
        evidence.append(cand)
    if cand and cand in declared and gate is not None and gate.residual_paise != 0:
        reasons.append("residual non-zero")
        reasons.append("verification failure")
    if recon.get("uniqueness") == "AMBIGUOUS":
        reasons.append("uniqueness conflict")
    if recon.get("uniqueness") == "BUDGET_EXCEEDED":
        reasons.append("search budget")
    if recon.get("uniqueness") == "NONE_FOUND":
        reasons.append("residual non-zero")
    item = ledger.get(cand) if cand else None
    if item is not None and credit is not None:
        if item.account_id != credit.account_id:
            reasons.append("wrong account")
        if item.currency != credit.currency:
            reasons.append("wrong currency")
    if not reasons:
        reasons.append("uniqueness conflict")
    return {
        "candidate_id": cand,
        "transaction_id": cid,
        "accepted": accepted,
        "reasons": list(dict.fromkeys(reasons)),
        "evidence_ids": evidence,
        "writes_cleared": False,
        "note": "Rejection is deterministic. The LLM may explain these reasons. It may not accept the candidate.",
    }


def source_agreement_matrix(transaction_id: str) -> dict[str, Any]:
    """BANK × SETTLEMENT × LEDGER × TAX × REFUND. LLM cannot modify."""
    from residual_zero.console.app import _credit_lookup, _overlay, _split

    cid = str(transaction_id or "").strip()
    lookup = _credit_lookup()
    credit = lookup.get(cid)
    split = _split()
    overlay = _overlay()
    if credit is None:
        return {"found": False, "transaction_id": cid, "writes_cleared": False}
    declared = tuple(split[2].get(cid) or ()) if split is not None else ()
    ledger = split[3] if split is not None else {}
    gate = overlay.by_id.get(cid) if overlay is not None else None
    has_bank = True
    has_set = bool(declared)
    has_led = bool(declared) and all(r.item_id in ledger for r in declared)
    has_tax = any(r.kind.value in {"TAX_GST", "TAX_WITHHOLDING", "FEE"} for r in declared)
    has_ref = any(r.kind.value == "REFUND" for r in declared)
    flags = {
        "BANK": has_bank,
        "SETTLEMENT": has_set,
        "LEDGER": has_led,
        "TAX": has_tax,
        "REFUND": has_ref,
    }

    def cell(a: str, b: str) -> str:
        if a == b:
            return "—"
        if flags[a] and flags[b]:
            return "✓"
        if flags[a] or flags[b]:
            return "?"
        return "?"

    names = ("BANK", "SETTLEMENT", "LEDGER", "TAX", "REFUND")
    matrix = {a: {b: cell(a, b) for b in names} for a in names}
    relations = [
        {
            "source": "BANK",
            "record_id": cid,
            "field": "amount_paise",
            "value": credit.amount_paise,
            "relationship": "credit",
            "verified": True,
            "evidence_level": 4 if gate is not None and gate.residual_paise == 0 else 3,
        },
        {
            "source": "SETTLEMENT",
            "record_id": cid,
            "field": "n_rows",
            "value": len(declared),
            "relationship": "declared",
            "verified": has_set,
            "evidence_level": 3 if has_set else 0,
        },
        {
            "source": "LEDGER",
            "record_id": cid,
            "field": "named_ids_present",
            "value": has_led,
            "relationship": "named_ledger",
            "verified": has_led,
            "evidence_level": 3 if has_led else 0,
        },
    ]
    return {
        "found": True,
        "transaction_id": cid,
        "matrix": matrix,
        "flags": flags,
        "relations": relations,
        "overlay_residual_paise": None if gate is None else gate.residual_paise,
        "writes_cleared": False,
        "note": "The AI can explain this matrix. The AI cannot modify it.",
    }


def graph_edges_v2(transaction_id: str) -> list[dict[str, Any]]:
    from residual_zero.console.app import _credit_lookup, _split

    cid = str(transaction_id or "").strip()
    lookup = _credit_lookup()
    credit = lookup.get(cid)
    split = _split()
    edges: list[dict[str, Any]] = []
    if credit is None:
        return edges
    edges.append(_edge(cid, "account_id", credit.account_id, "id", "account", verified=True, level=3))
    edges.append(_edge(cid, "value_date", credit.value_date.isoformat(), "date", "date", verified=True, level=3))
    edges.append(_edge(cid, "amount_paise", cid, "amount_paise", "amount", verified=True, level=3))
    if credit.utr:
        edges.append(_edge(cid, "utr", credit.utr, "utr", "reference", verified=True, level=3))
    declared = tuple(split[2].get(cid) or ()) if split is not None else ()
    if declared:
        set_id = "set:" + cid
        edges.append(_edge(cid, "id", set_id, "credit_id", "settlement", verified=True, level=3))
        ledger = split[3]
        for row in declared[:40]:
            edges.append(_edge(set_id, "item_id", row.item_id, "id", "ledger_item", verified=row.item_id in ledger, level=3))
            edges.append(_edge(row.item_id, "kind", row.kind.value, "kind", "kind", verified=True, level=3))
    return edges
