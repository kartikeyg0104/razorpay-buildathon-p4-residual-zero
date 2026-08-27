"""F37 deterministic clustering. No cause_labels in src/residual_zero/cluster.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from residual_zero.cluster import ExceptionRow, cluster_rows, compression_ratio
from residual_zero.models import ExceptionClass


def test_same_signature_collapses():
    rows = (
        ExceptionRow(
            bank_credit_id="c1", exception_class=ExceptionClass.MISSING_RECORD,
            value_date=date(2025, 1, 9), nearest_delta_paise=1_000,
            pool_gross_paise=100_000, instrument="UPI", missing_kind="TAX_GST",
        ),
        ExceptionRow(
            bank_credit_id="c2", exception_class=ExceptionClass.MISSING_RECORD,
            value_date=date(2025, 1, 10), nearest_delta_paise=1_000,
            pool_gross_paise=100_000, instrument="UPI", missing_kind="TAX_GST",
        ),
    )
    clusters = cluster_rows(rows)
    assert len(clusters) == 1
    assert compression_ratio(2, 1) == (2, 1)


def test_class_split_is_not_merged():
    rows = (
        ExceptionRow(
            bank_credit_id="c1", exception_class=ExceptionClass.MISSING_RECORD,
            value_date=date(2025, 1, 9), nearest_delta_paise=1_000,
            pool_gross_paise=100_000, instrument="UPI", missing_kind="none",
        ),
        ExceptionRow(
            bank_credit_id="c2", exception_class=ExceptionClass.AMBIGUOUS_DECOMPOSITION,
            value_date=date(2025, 1, 9), nearest_delta_paise=1_000,
            pool_gross_paise=100_000, instrument="UPI", missing_kind="none",
        ),
    )
    assert len(cluster_rows(rows)) == 2


def test_cluster_module_does_not_name_truth():
    text = Path("src/residual_zero/cluster.py").read_text(encoding="utf-8")
    assert "truth.jsonl" not in text
    assert "cause_labels" not in text
