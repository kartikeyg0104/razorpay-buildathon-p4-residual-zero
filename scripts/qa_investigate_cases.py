"""Investigate representative credits. Does not mutate reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

from residual_zero.qa.finance_tools import call_finance_tool

CASES = {
    "residual_zero": "crd_001_acc_01_2025-01-09",
    "ambiguous": "crd_001_acc_01_2025-01-09",
    "none_found_dev": "crd_001_acc_00_2025-01-08",
    "none_found_test_open": "crd_101_acc_00_2025-01-08",
    "missing_record": "crd_003_acc_01_2025-01-30",
    "settlement_linked": "crd_001_acc_01_2025-01-09",
}

EXPLORER = (
    "UNRESOLVED",
    "AMBIGUOUS",
    "HIGH_VALUE_AMBIGUOUS",
    "MISSING_SETTLEMENT",
    "MISSING_LEDGER",
    "TAX_MISMATCH",
    "REFUND_MISMATCH",
    "LEDGER_SETTLEMENT_DISAGREE",
    "POTENTIALLY_RECOVERABLE",
    "HIGH_VALUE_UNRESOLVED",
)


def _pack(cid: str) -> dict:
    recon = call_finance_tool("get_reconciliation", {"transaction_id": cid})
    inv = call_finance_tool("investigate_transaction", {"transaction_id": cid})
    cmp = call_finance_tool("compare_sources", {"transaction_id": cid})
    miss = call_finance_tool("get_missing_records", {"transaction_id": cid})
    eq = call_finance_tool("get_candidate_equations", {"transaction_id": cid})
    tax = call_finance_tool("get_tax_breakdown", {"transaction_id": cid})
    return {
        "transaction_id": cid,
        "found": recon.get("found"),
        "status": recon.get("status"),
        "uniqueness": recon.get("uniqueness"),
        "residual_paise": recon.get("residual_paise"),
        "residual_display": recon.get("residual_display"),
        "solution_count": recon.get("solution_count"),
        "matched_count": recon.get("matched_count"),
        "auto_cleared": recon.get("auto_cleared"),
        "writes_cleared": recon.get("writes_cleared"),
        "investigation_found": inv.get("found"),
        "bank_minus_settlement": cmp.get("bank_minus_settlement_display"),
        "missing": miss.get("missing") if isinstance(miss.get("missing"), list) else miss.get("rows") or miss.get("items"),
        "equations": eq.get("n") or eq.get("count") or len(eq.get("equations") or eq.get("rows") or []),
        "tax_found": tax.get("found"),
    }


def main() -> dict:
    cases = {name: _pack(cid) for name, cid in CASES.items()}
    explorer = {}
    for kind in EXPLORER:
        got = call_finance_tool("explorer_query", {"kind": kind, "limit": 5})
        explorer[kind] = {
            "n": got.get("n"),
            "writes_cleared": got.get("writes_cleared"),
            "sample": [r.get("transaction_id") for r in (got.get("rows") or [])[:3]],
        }
    root = call_finance_tool("get_root_cause", {})
    payload = {
        "cases": cases,
        "explorer": explorer,
        "root_cause_prefix": str(root.get("text") or "")[:300],
        "writes_cleared": False,
        "ai_selected_winner": False,
    }
    out = Path("artifacts").joinpath("qa", "investigations.json")
    out.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: {"status": v.get("status"), "uniqueness": v.get("uniqueness"), "residual_paise": v.get("residual_paise")} for k, v in cases.items()}, indent=2))
    return payload


if __name__ == "__main__":
    main()
