"""Eval-only leakage precision. Never imported from src/."""

from __future__ import annotations

from residual_zero.controller.leakage import LeakageReport
from generator.truth import TruthRecord


def precision_against_truth(report: LeakageReport, recs: tuple[TruthRecord, ...]) -> tuple[int, int]:
    """(hits, n_evidence). A hit is evidence whose subject appears in a corrupted truth record."""
    corrupted_ids: set[str] = set()
    for rec in recs:
        if rec.corruption_classes:
            corrupted_ids.add(rec.bank_credit_id)
            corrupted_ids.update(rec.member_ids)
    hits = sum(1 for row in report.evidence if row.subject_id in corrupted_ids)
    return hits, len(report.evidence)
