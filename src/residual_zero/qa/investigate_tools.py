"""Read-only investigation tools. LLM never queries SQLite. Never writes CLEARED."""

from __future__ import annotations

from typing import Any

from residual_zero.console.facts import credit_forensic
from residual_zero.money import format_rupees
from residual_zero.qa.finance_tools import _cite, _limit_n, get_reconciliation, get_settlement_details, get_tax_breakdown

INVESTIGATE_TOOLS = (
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
)


def _desk():
    from residual_zero.console.app import _credit_lookup, _overlay, _split

    return _split(), _overlay(), _credit_lookup()


def find_by_reference(reference: str) -> dict[str, Any]:
    token = str(reference or "").strip()
    split, _overlay, lookup = _desk()
    hits: list[dict[str, str]] = []
    if not token:
        return {"found": False, "reference": token, "n": 0, "rows": [], "writes_cleared": False}
    for credit in lookup.values():
        if credit.utr and credit.utr == token:
            hits.append({"transaction_id": credit.id, "via": "bank.utr"})
    if split is not None:
        for cid, rows in split[2].items():
            for row in rows:
                if row.order_id == token:
                    hits.append({"transaction_id": cid, "via": "settlement.order_id"})
                    break
    return {
        "found": bool(hits),
        "reference": token,
        "n": len(hits),
        "rows": hits[:20],
        "writes_cleared": False,
        "note": "Lookup only. Not a reconciliation.",
    }


def find_by_settlement(settlement_id: str) -> dict[str, Any]:
    return get_settlement_details(settlement_id)


def find_by_invoice(invoice_id: str) -> dict[str, Any]:
    return find_by_reference(invoice_id)


def find_by_member(member_id: str) -> dict[str, Any]:
    token = str(member_id or "").strip()
    split, _overlay, lookup = _desk()
    hits: list[dict[str, str]] = []
    if split is not None:
        ledger = split[3]
        item = ledger.get(token)
        if item is not None:
            hits.append({"member_id": token, "account_id": item.account_id, "via": "ledger.id"})
        for cid, rows in split[2].items():
            if any(r.item_id == token for r in rows):
                hits.append({"transaction_id": cid, "via": "settlement.item_id"})
    for credit in lookup.values():
        if credit.account_id == token:
            hits.append({"transaction_id": credit.id, "via": "bank.account_id"})
            if len(hits) >= 20:
                break
    return {"found": bool(hits), "member_id": token, "n": len(hits), "rows": hits[:20], "writes_cleared": False}


def find_by_account(account_id: str, limit: int | None = None) -> dict[str, Any]:
    token = str(account_id or "").strip()
    n = _limit_n(limit)
    _split, _overlay, lookup = _desk()
    rows = [
        {"transaction_id": c.id, "amount_display": format_rupees(c.amount_paise), "date": c.value_date.isoformat()}
        for c in lookup.values()
        if c.account_id == token
    ][:n]
    return {"found": bool(rows), "account_id": token, "n": len(rows), "rows": rows, "writes_cleared": False}


def find_by_date(value_date: str, limit: int | None = None) -> dict[str, Any]:
    token = str(value_date or "").strip()
    n = _limit_n(limit)
    _split, _overlay, lookup = _desk()
    rows = [
        {"transaction_id": c.id, "account_id": c.account_id, "amount_display": format_rupees(c.amount_paise)}
        for c in lookup.values()
        if c.value_date.isoformat() == token
    ][:n]
    return {"found": bool(rows), "value_date": token, "n": len(rows), "rows": rows, "writes_cleared": False}


def compare_sources(transaction_id: str) -> dict[str, Any]:
    """Bank vs settlement vs ledger vs tax. Discrepancy is computed here, not by the LLM."""
    cid = str(transaction_id or "").strip()
    split, overlay, lookup = _desk()
    credit = lookup.get(cid)
    if credit is None:
        return {"found": False, "transaction_id": cid, "writes_cleared": False, "error": "not_found"}
    declared = tuple(split[2].get(cid) or ()) if split is not None else ()
    ledger = split[3] if split is not None else {}
    by_kind: dict[str, int] = {}
    ledger_sum = 0
    missing: list[str] = []
    for row in declared:
        by_kind[row.kind.value] = by_kind.get(row.kind.value, 0) + row.amount_paise
        item = ledger.get(row.item_id)
        if item is None:
            missing.append(row.item_id)
        else:
            ledger_sum += item.amount_paise
    settlement_sum = sum(by_kind.values())
    gate = overlay.by_id.get(cid) if overlay is not None else None
    bank = credit.amount_paise
    bank_minus_settlement = bank - settlement_sum
    sources = [
        {"source": "BANK", "record_id": cid, "amount_paise": bank, "amount_display": format_rupees(bank), "sign": "credit", "date": credit.value_date.isoformat(), "status": "present"},
        {"source": "SETTLEMENT", "record_id": cid, "amount_paise": settlement_sum, "amount_display": format_rupees(settlement_sum), "sign": "ops", "date": credit.value_date.isoformat(), "status": "present" if declared else "missing"},
        {"source": "LEDGER", "record_id": cid, "amount_paise": ledger_sum, "amount_display": format_rupees(ledger_sum), "sign": "ops", "date": "", "status": "missing_items" if missing else "present"},
    ]
    for kind in ("PAYMENT", "FEE", "TAX_GST", "TAX_WITHHOLDING", "REFUND", "RESERVE_HOLD", "BANK_CHARGE"):
        paise = by_kind.get(kind, 0)
        sources.append(
            {
                "source": kind,
                "record_id": cid,
                "amount_paise": paise,
                "amount_display": format_rupees(paise),
                "sign": "in" if paise > 0 else ("out" if paise < 0 else "zero"),
                "date": "",
                "status": "present" if kind in by_kind else "absent",
            }
        )
    from residual_zero.console.proof_explorer import source_agreement_matrix

    agreement = source_agreement_matrix(cid)
    return {
        "found": True,
        "transaction_id": cid,
        "sources": sources,
        "bank_minus_settlement_paise": bank_minus_settlement,
        "bank_minus_settlement_display": format_rupees(bank_minus_settlement),
        "overlay_residual_paise": None if gate is None else gate.residual_paise,
        "overlay_residual_display": None if gate is None else format_rupees(gate.residual_paise),
        "missing_ledger_ids": tuple(missing[:20]),
        "matrix": agreement.get("matrix"),
        "agreement": agreement,
        "writes_cleared": False,
        "note": "Discrepancy is computed by this tool. The LLM must not recalculate it.",
        "evidence": [_cite("cmp.bank", "bank.csv", cid, "amount_paise", bank)],
    }


def explain_verification_failure(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    recon = get_reconciliation(cid)
    forensic = credit_forensic(cid) or {}
    tax = get_tax_breakdown(cid)
    if not recon.get("found"):
        return recon
    residual = recon.get("residual_paise")
    why = "residual is zero; search uniqueness still blocks auto-clear"
    if residual not in (0, None):
        why = "verify_declared residual is not zero"
    if int(forensic.get("ledger_miss") or 0) > 0:
        why = "settlement names a ledger id that is not on disk"
    if int(forensic.get("n_declared") or 0) == 0:
        why = "no settlement rows on disk for this credit"
    return {
        "found": True,
        "transaction_id": cid,
        "uniqueness": recon.get("uniqueness"),
        "residual_display": recon.get("residual_display"),
        "gate_a_ok": recon.get("gate_a_ok"),
        "bucket": forensic.get("bucket"),
        "why": why,
        "missing_tax_lines": tax.get("missing_tax_lines"),
        "writes_cleared": False,
        "matched": False,
        "cleared": False,
    }


def get_candidate_equations(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    split, overlay, lookup = _desk()
    credit = lookup.get(cid)
    if credit is None:
        return {"found": False, "transaction_id": cid, "writes_cleared": False}
    declared = tuple(split[2].get(cid) or ()) if split is not None else ()
    kinds: dict[str, int] = {}
    for row in declared:
        kinds[row.kind.value] = kinds.get(row.kind.value, 0) + row.amount_paise
    gate = overlay.by_id.get(cid) if overlay is not None else None
    recon = get_reconciliation(cid)
    declared_eq = {
        "name": "DECLARED",
        "lines": [{"kind": k, "amount_display": format_rupees(v)} for k, v in kinds.items()],
        "bank_display": format_rupees(credit.amount_paise),
        "residual_display": format_rupees(gate.residual_paise) if gate is not None else None,
        "ok": bool(gate is not None and gate.ok),
    }
    search_eq = {
        "name": "SEARCH",
        "lines": [],
        "solution_count": recon.get("solution_count"),
        "uniqueness": recon.get("uniqueness"),
        "note": (
            "Search member sets are not auto-selected. "
            "When uniqueness is AMBIGUOUS the engine refuses to pick Equation SEARCH."
        ),
        "ok": False,
    }
    return {
        "found": True,
        "transaction_id": cid,
        "equations": [declared_eq, search_eq],
        "choose_one": False,
        "writes_cleared": False,
        "note": "The AI may explain that two paths exist. It may not pick one.",
    }


def get_missing_records(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    forensic = credit_forensic(cid) or {}
    cmp = compare_sources(cid)
    return {
        "found": cmp.get("found"),
        "transaction_id": cid,
        "ledger_miss": int(forensic.get("ledger_miss") or 0),
        "n_declared": int(forensic.get("n_declared") or 0),
        "missing_ledger_ids": cmp.get("missing_ledger_ids") or (),
        "bucket": forensic.get("bucket"),
        "writes_cleared": False,
        "note": "Do not fabricate missing ledger amounts.",
    }


def get_transaction_timeline(transaction_id: str) -> dict[str, Any]:
    cid = str(transaction_id or "").strip()
    split, _overlay, lookup = _desk()
    credit = lookup.get(cid)
    if credit is None:
        return {"found": False, "transaction_id": cid, "writes_cleared": False}
    events = [
        {"at": credit.value_date.isoformat(), "kind": "BANK_VALUE_DATE", "record_id": cid},
    ]
    if split is not None:
        for item_id in (r.item_id for r in (split[2].get(cid) or ())):
            item = split[3].get(item_id)
            if item is None:
                continue
            day = item.occurred_at.date().isoformat() if item.occurred_at else ""
            if day:
                events.append({"at": day, "kind": item.kind.value, "record_id": item_id})
    return {"found": True, "transaction_id": cid, "events": events[:40], "writes_cleared": False}


def compare_solutions(transaction_id: str) -> dict[str, Any]:
    from residual_zero.console.proof_explorer import proof_explorer

    blob = proof_explorer(transaction_id)
    blob["choose_one"] = False
    blob["writes_cleared"] = False
    if blob.get("found"):
        blob.setdefault(
            "note",
            "Selecting one residual-zero subset without uniqueness UNIQUE would be an unsupported assumption.",
        )
    return blob


def call_investigate_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any] | None:
    args = dict(arguments or {})
    cid = str(args.get("transaction_id") or args.get("credit_id") or args.get("settlement_id") or "")
    if name == "find_by_reference":
        return find_by_reference(str(args.get("reference") or args.get("value") or cid))
    if name == "find_by_settlement":
        return find_by_settlement(str(args.get("settlement_id") or cid))
    if name == "find_by_invoice":
        return find_by_invoice(str(args.get("invoice_id") or args.get("reference") or cid))
    if name == "find_by_member":
        return find_by_member(str(args.get("member_id") or args.get("value") or cid))
    if name == "find_by_account":
        return find_by_account(str(args.get("account_id") or args.get("value") or ""), args.get("limit") if isinstance(args.get("limit"), int) else None)
    if name == "find_by_date":
        return find_by_date(str(args.get("value_date") or args.get("date") or args.get("value") or ""), args.get("limit") if isinstance(args.get("limit"), int) else None)
    if name == "compare_sources":
        return compare_sources(cid)
    if name == "explain_verification_failure":
        return explain_verification_failure(cid)
    if name == "get_candidate_equations":
        return get_candidate_equations(cid)
    if name == "get_missing_records":
        return get_missing_records(cid)
    if name == "get_transaction_timeline":
        return get_transaction_timeline(cid)
    if name == "compare_solutions":
        return compare_solutions(cid)
    if name == "get_proof_explorer":
        from residual_zero.console.proof_explorer import proof_explorer

        return proof_explorer(cid)
    if name == "explain_candidate_rejection":
        from residual_zero.console.proof_explorer import explain_candidate_rejection

        return explain_candidate_rejection(cid, str(args.get("candidate_id") or args.get("member_id") or ""))
    return None
