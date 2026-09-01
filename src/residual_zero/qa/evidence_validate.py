"""Deterministic validation of AI-extracted identifiers. Never treats extraction as MATCH."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from residual_zero.money import format_rupees
from residual_zero.qa.evidence_extract import extract_for_credit, normalize_identifier
from residual_zero.solver.fastpath import DeclaredLine, verify_declared


@lru_cache(maxsize=1)
def _indexes() -> dict[str, Any]:
    from residual_zero.console.app import _credit_lookup, _overlay, _split
    from residual_zero.config import load_fees, load_tax_rates

    split = _split()
    overlay = _overlay()
    lookup = _credit_lookup()
    by_order: dict[str, list] = {}
    by_item: dict[str, list] = {}
    by_credit_decl: dict[str, list] = {}
    ledger = {}
    ledger_by_order: dict[str, list] = {}
    if split is not None:
        _items, _credits, by_credit, ledger, _ids = split
        by_credit_decl = dict(by_credit)
        for cid, rows in by_credit.items():
            for row in rows:
                if row.order_id:
                    by_order.setdefault(row.order_id, []).append((cid, row))
                by_item.setdefault(row.item_id, []).append((cid, row))
        for item in ledger.values():
            if item.order_id:
                ledger_by_order.setdefault(item.order_id, []).append(item)
    utr_map = {c.utr: c.id for c in lookup.values() if c.utr}
    return {
        "split": split,
        "overlay": overlay,
        "lookup": lookup,
        "by_order": by_order,
        "by_item": by_item,
        "by_credit": by_credit_decl,
        "ledger": ledger,
        "ledger_by_order": ledger_by_order,
        "utr_map": utr_map,
        "rates": load_tax_rates(),
        "fees": load_fees(),
    }


def reset_indexes() -> None:
    _indexes.cache_clear()


def _belongs(credit_id: str, found_credit_id: str) -> bool:
    return credit_id == found_credit_id


def validate_fields(transaction_id: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark each extracted field verified iff a structured record exists and belongs to this credit."""
    idx = _indexes()
    lookup = idx["lookup"]
    credit = lookup.get(transaction_id)
    out: list[dict[str, Any]] = []
    for row in fields:
        item = dict(row)
        name = str(item.get("field") or "")
        value = str(item.get("value") or "")
        exists = False
        belongs = False
        source = ""
        record_id = ""
        if name == "settlement_id":
            rows = idx["by_credit"].get(value) or []
            if rows:
                exists = True
                belongs = _belongs(transaction_id, value)
                source = "settlement.csv"
                record_id = value
            elif value in lookup:
                exists = True
                belongs = _belongs(transaction_id, value)
                source = "bank_credit"
                record_id = value
        elif name == "reference":
            cid = idx["utr_map"].get(value)
            if cid:
                exists = True
                belongs = _belongs(transaction_id, cid)
                source = "bank.utr"
                record_id = cid
            elif value in idx["by_order"]:
                hits = idx["by_order"][value]
                exists = True
                belongs = any(_belongs(transaction_id, cid) for cid, _row in hits)
                source = "settlement.order_id"
                record_id = value
            elif value in idx["ledger_by_order"]:
                exists = True
                belongs = any(it.account_id == (credit.account_id if credit else "") for it in idx["ledger_by_order"][value])
                source = "ledger.order_id"
                record_id = value
            else:
                norm = normalize_identifier(value)["normalized_value"]
                for order_id in idx["by_order"]:
                    if normalize_identifier(order_id)["normalized_value"] == norm:
                        exists = True
                        belongs = any(_belongs(transaction_id, cid) for cid, _r in idx["by_order"][order_id])
                        source = "settlement.order_id_normalized"
                        record_id = order_id
                        break
        elif name == "invoice_id":
            if value in idx["by_order"]:
                exists = True
                belongs = any(_belongs(transaction_id, cid) for cid, _row in idx["by_order"][value])
                source = "settlement.order_id"
                record_id = value
            elif value in idx["ledger_by_order"]:
                exists = True
                source = "ledger.order_id"
                record_id = value
                belongs = any(it.account_id == (credit.account_id if credit else "") for it in idx["ledger_by_order"][value])
        elif name == "member_id":
            if value in idx["ledger"]:
                exists = True
                item_row = idx["ledger"][value]
                belongs = credit is not None and item_row.account_id == credit.account_id
                source = "ledger"
                record_id = value
            elif credit is not None and value == credit.account_id:
                exists = True
                belongs = True
                source = "bank.account_id"
                record_id = transaction_id
        elif name == "date":
            if credit is not None and value == credit.value_date.isoformat():
                exists = True
                belongs = True
                source = "bank.value_date"
                record_id = transaction_id
        elif name == "source":
            exists = True
            belongs = credit is not None and value.upper() in (credit.narration_raw or "").upper()
            source = "bank.narration_raw"
            record_id = transaction_id
        elif name == "payment_type":
            exists = True
            belongs = credit is not None and value.upper() in (credit.narration_raw or "").upper()
            source = "bank.narration_raw"
            record_id = transaction_id
        item["exists"] = exists
        item["belongs_to_credit"] = belongs
        item["verified"] = bool(exists and belongs)
        item["lookup_source"] = source
        item["lookup_record_id"] = record_id
        self_sources = {
            "bank.utr",
            "bank.account_id",
            "bank.value_date",
            "bank.narration_raw",
            "bank_credit",
        }
        item["relationship"] = (
            "CORROBORATION"
            if source in self_sources and belongs
            else ("DECLARED_LOOKUP" if belongs and exists else ("FOREIGN" if exists else "NONE"))
        )
        item["status"] = "VERIFIED" if item["verified"] else ("EXISTS_FOREIGN" if exists else "UNVERIFIED")
        out.append(item)
    return out


def try_declared_from_extraction(
    transaction_id: str,
    validated: list[dict[str, Any]],
) -> dict[str, Any]:
    """If extraction names this credit's settlement rows, run verify_declared. Never writes CLEARED.

    Foreign settlement hits are recorded as EXISTS_FOREIGN and are not used.
    """
    idx = _indexes()
    lookup = idx["lookup"]
    credit = lookup.get(transaction_id)
    declared = list(idx["by_credit"].get(transaction_id) or [])
    new_from_extract: list = []
    foreign = 0
    for row in validated:
        if not row.get("exists"):
            continue
        name = row.get("field")
        value = str(row.get("value") or "")
        if name == "settlement_id" and value in idx["by_credit"] and value != transaction_id:
            foreign += 1
        if name in {"reference", "invoice_id"} and value in idx["by_order"]:
            for cid, srow in idx["by_order"][value]:
                if cid == transaction_id:
                    if srow not in declared and srow not in new_from_extract:
                        new_from_extract.append(srow)
                else:
                    foreign += 1
    added = len(new_from_extract)
    lines = tuple(
        DeclaredLine(r.item_id, r.kind, r.amount_paise, r.instrument)
        for r in (*declared, *new_from_extract)
    )
    result = {
        "transaction_id": transaction_id,
        "declared_count": len(declared),
        "extracted_added": added,
        "foreign_hits": foreign,
        "recon_attempted": False,
        "residual_paise": None,
        "residual_display": None,
        "ok": False,
        "missing_item_ids": (),
        "writes_cleared": False,
        "status": "EVIDENCE_ONLY",
    }
    if credit is None:
        result["status"] = "NOT_FOUND"
        return result
    if not lines:
        result["status"] = "NO_DECLARED"
        return result
    overlay = idx["overlay"]
    gate = overlay.by_id.get(transaction_id) if overlay is not None else None
    if added == 0 and gate is not None:
        result["recon_attempted"] = True
        result["ok"] = gate.ok
        result["residual_paise"] = gate.residual_paise
        result["residual_display"] = format_rupees(gate.residual_paise)
        result["status"] = "RESIDUAL_ZERO" if gate.ok else "NOT_RECONCILED"
        return result
    if added == 0:
        result["status"] = "NO_NEW_DECLARED"
        return result
    from residual_zero.console.app import _profile

    fast = verify_declared(
        credit,
        lines,
        idx["ledger"],
        idx["rates"],
        idx["fees"],
        reserve_bps=_profile().reserve_bps,
    )
    result["recon_attempted"] = True
    result["ok"] = fast.ok
    result["residual_paise"] = fast.residual_paise
    result["residual_display"] = format_rupees(fast.residual_paise)
    result["missing_item_ids"] = fast.missing_item_ids
    if fast.ok:
        result["status"] = "RESIDUAL_ZERO"
    else:
        result["status"] = "NOT_RECONCILED"
    return result


def investigate(transaction_id: str) -> dict[str, Any]:
    """Extract → validate → optional verify_declared. AI never returns MATCHED/CLEARED."""
    idx = _indexes()
    credit = idx["lookup"].get(transaction_id)
    if credit is None:
        return {
            "found": False,
            "transaction_id": transaction_id,
            "error": "not_found",
            "writes_cleared": False,
        }
    extracted = extract_for_credit(
        transaction_id,
        credit.narration_raw,
        credit.value_date.isoformat(),
        credit.account_id,
        credit.utr or "",
    )
    validated = validate_fields(transaction_id, list(extracted.get("fields") or []))
    recon = try_declared_from_extraction(transaction_id, validated)
    verified_n = sum(1 for r in validated if r.get("verified"))
    return {
        "found": True,
        "transaction_id": transaction_id,
        "extraction": extracted,
        "validated_fields": validated,
        "verified_field_count": verified_n,
        "recon": recon,
        "writes_cleared": False,
        "matched": False,
        "cleared": False,
        "unique": False,
    }
