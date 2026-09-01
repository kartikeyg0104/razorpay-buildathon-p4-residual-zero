"""Evaluate narration extraction against structured bank fields. Not a recon match.

Does not open the answer-key file. Writes artifacts/dev/extract_eval.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from residual_zero.qa.finance_extract import extract_reference, score_extraction


def run_extract_eval() -> dict[str, object]:
    from residual_zero.console.app import _credit_lookup

    lookup = _credit_lookup()
    predicted_fields = 0
    gold_fields = 0
    correct_fields = 0
    false_fields = 0
    n = 0
    for credit in lookup.values():
        n += 1
        pred = extract_reference(
            credit.narration_raw,
            credit.value_date.isoformat(),
            credit.account_id,
        )
        gold = {
            "source": "RAZORPAY" if "RAZORPAY" in credit.narration_raw.upper() else None,
            "settlement_date": credit.value_date.isoformat(),
            "member_id": credit.account_id if credit.account_id in credit.narration_raw else None,
            "payment_type": "NEFT" if "NEFT" in credit.narration_raw.upper() else None,
            "reference": credit.utr if credit.utr and credit.utr in credit.narration_raw else None,
        }
        scored = score_extraction(pred, gold)
        predicted_fields += scored["predicted_fields"]
        gold_fields += scored["gold_fields"]
        correct_fields += scored["correct_fields"]
        false_fields += scored["false_fields"]
    precision = f"{correct_fields}/{predicted_fields}" if predicted_fields else "0/0"
    recall = f"{correct_fields}/{gold_fields}" if gold_fields else "0/0"
    false_rate = f"{false_fields}/{predicted_fields}" if predicted_fields else "0/0"
    result = {
        "n_credits": n,
        "predicted_fields": predicted_fields,
        "gold_fields": gold_fields,
        "correct_fields": correct_fields,
        "false_fields": false_fields,
        "precision": precision,
        "recall": recall,
        "false_extraction_rate": false_rate,
        "candidate_only": True,
        "writes_cleared": False,
    }
    out = Path("artifacts").joinpath("dev", "extract_eval.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run_extract_eval(), indent=2))
