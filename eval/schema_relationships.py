"""Dev-only schema join audit. Does not install production rules. May open truth."""

from __future__ import annotations

import json
from pathlib import Path


def run_schema_audit(split: str = "dev") -> dict[str, object]:
    rows = [
        {
            "field": "settlement.item_id",
            "source": "settlement.csv",
            "other": "ledger.id",
            "join": "explicit",
            "ground_truth_retention": "100%",
            "evidence_strength": "LEVEL 3",
            "safe_to_use": "YES — already used by verify_declared",
        },
        {
            "field": "settlement.credit_id",
            "source": "settlement.csv",
            "other": "bank.id",
            "join": "explicit",
            "ground_truth_retention": "100%",
            "evidence_strength": "LEVEL 3",
            "safe_to_use": "YES — already the declared overlay key",
        },
        {
            "field": "settlement.order_id",
            "source": "settlement.csv",
            "other": "ledger.order_id",
            "join": "explicit",
            "ground_truth_retention": "100%",
            "evidence_strength": "LEVEL 3",
            "safe_to_use": "YES as lookup; NO as a merge across credits",
        },
        {
            "field": "bank.utr",
            "source": "bank.csv",
            "other": "bank.id",
            "join": "one-to-one on this corpus",
            "ground_truth_retention": "corroboration",
            "evidence_strength": "LEVEL 1",
            "safe_to_use": "NO HARD FILTER — same-row corroboration only",
        },
        {
            "field": "bank.narration_raw",
            "source": "bank.csv",
            "other": "settlement (none)",
            "join": "text only",
            "ground_truth_retention": "not a key",
            "evidence_strength": "LEVEL 1",
            "safe_to_use": "NO HARD FILTER — no SET-/INV-/ord_ tokens beyond bank fields",
        },
        {
            "field": "bank.value_date",
            "source": "bank.csv",
            "other": "ledger.occurred_at",
            "join": "date correlation",
            "ground_truth_retention": "window miss if D is included",
            "evidence_strength": "LEVEL 1",
            "safe_to_use": "NO — must not widen [D-5, D-1]",
        },
    ]
    result = {
        "split": split,
        "writes_cleared": False,
        "implemented_new_rules": 0,
        "rows": rows,
        "recommendation": "Do not promote text or date correlations to hard filters.",
    }
    out = Path("artifacts").joinpath(split, "schema_relationships.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps({"n": len(run_schema_audit()["rows"]), "new_rules": 0}, indent=2))
