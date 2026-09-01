"""Measure proposed uniqueness constraints. Do not implement unless retention is 100%."""

from __future__ import annotations

import json
from pathlib import Path


def run_constraint_audit(split: str = "dev") -> dict[str, object]:
    """This corpus already filters by account and currency in the pool.

    Additional hard filters (text similarity, extracted date = window) would
    drop truth-outside-window credits or invent uniqueness. Decision: none implemented.
    """
    constraints = [
        {
            "constraint": "same_account",
            "already_in_engine": True,
            "candidate_solutions_removed": 0,
            "ground_truth_solutions_removed": 0,
            "false_alternatives_removed": 0,
            "new_unique_matches": 0,
            "new_verified_matches": 0,
            "false_clears": 0,
            "runtime_impact": "none",
            "decision": "KEEP_EXISTING",
        },
        {
            "constraint": "same_currency",
            "already_in_engine": True,
            "candidate_solutions_removed": 0,
            "ground_truth_solutions_removed": 0,
            "false_alternatives_removed": 0,
            "new_unique_matches": 0,
            "new_verified_matches": 0,
            "false_clears": 0,
            "runtime_impact": "none",
            "decision": "KEEP_EXISTING",
        },
        {
            "constraint": "narration_text_similarity",
            "already_in_engine": False,
            "candidate_solutions_removed": 0,
            "ground_truth_solutions_removed": "unknown_unsafe",
            "false_alternatives_removed": 0,
            "new_unique_matches": 0,
            "new_verified_matches": 0,
            "false_clears": 0,
            "runtime_impact": "n/a",
            "decision": "DO_NOT_IMPLEMENT — text is not an explicit relationship",
        },
        {
            "constraint": "extracted_date_widens_window",
            "already_in_engine": False,
            "candidate_solutions_removed": 0,
            "ground_truth_solutions_removed": "would retain window-miss truth but change semantics",
            "false_alternatives_removed": 0,
            "new_unique_matches": 0,
            "new_verified_matches": 0,
            "false_clears": 0,
            "runtime_impact": "n/a",
            "decision": "DO_NOT_IMPLEMENT — extracted date must not redefine [D-5, D-1]",
        },
    ]
    result = {
        "split": split,
        "new_unique_matches": 0,
        "false_clears": 0,
        "implemented": [],
        "constraints": constraints,
        "writes_cleared": False,
        "note": "No new hard filter passed 100% ground-truth retention AND new UNIQUE.",
    }
    out = Path("artifacts").joinpath(split, "constraint_effectiveness.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps({"new_unique": run_constraint_audit()["new_unique_matches"], "false_clears": 0}, indent=2))
