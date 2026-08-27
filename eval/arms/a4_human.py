"""A4: human reference. Time and accuracy, not coverage. F19/F56 at CP5."""

from __future__ import annotations

import json
from pathlib import Path

from residual_zero.models import Disposition

from . import ArmResult


def run_a4(results_path: Path = Path("artifacts/human_study/results.json")) -> ArmResult:
    """Human arm. Blank sheets and an honest not-run result still produce a structured row."""
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    n = int(payload.get("n_credits", 0))
    predictions: dict[str, tuple[str, ...]] = {}
    dispositions: dict[str, Disposition] = {}
    selected = Path("artifacts/human_study/selected_credits.json")
    if selected.is_file():
        ids = json.loads(selected.read_text(encoding="utf-8")).get("credit_ids", [])
        for cid in ids:
            predictions[cid] = ()
            dispositions[cid] = Disposition.FLAGGED
        n = len(ids)
    return ArmResult(
        arm="a4",
        predictions=predictions,
        dispositions=dispositions,
        has_exception_path=True,
        has_budget_path=True,
    )
