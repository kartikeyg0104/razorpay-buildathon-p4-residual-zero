"""Eval-side truth loader. Unrestricted. NEVER imported by src/residual_zero/."""

from __future__ import annotations

import json
from pathlib import Path

from generator.truth import TruthRecord


def load_truth(split: str, data_root: Path = Path("data")) -> tuple[TruthRecord, ...]:
    """Read data/{split}/truth.jsonl."""
    path = data_root.joinpath(split, "truth.jsonl")
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(TruthRecord.model_validate(json.loads(line)))
    return tuple(records)
