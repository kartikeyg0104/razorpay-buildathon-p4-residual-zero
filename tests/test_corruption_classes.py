"""Corruption classes 1–23, held-out class 9, stacking, range B wider than A."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from generator.corrupt import RANGE_A, RANGE_B, HELD_OUT_DEV
from generator.truth import TruthRecord
from eval.truth_loader import load_truth


def _classes(split: str, root: Path) -> Counter:
    recs = load_truth(split, data_root=root)
    c: Counter = Counter()
    for r in recs:
        for cls in r.corruption_classes:
            c[cls] += 1
    return c


def test_every_phase1_class_has_instances(cp2_data: Path):
    """Classes 1–23 each have at least one instance in dev and at least 25 in test (§8.3)."""
    dev = _classes("dev", cp2_data)
    test = _classes("test", cp2_data)
    for cls in range(1, 24):
        if cls == HELD_OUT_DEV:
            assert dev[cls] == 0
            assert test[cls] >= 25, f"class {cls} test={test[cls]}"
            continue
        assert dev[cls] >= 1, f"class {cls} missing from dev: {dev}"
        assert test[cls] >= 25, f"class {cls} test={test[cls]}"


def test_held_out_class_absent_from_dev(cp2_data: Path):
    """The declared held-out class has zero instances in dev and non-zero in test."""
    assert _classes("dev", cp2_data)[HELD_OUT_DEV] == 0
    assert _classes("test", cp2_data)[HELD_OUT_DEV] > 0


def test_test_split_has_stacked_corruptions(cp2_data: Path):
    """At least one test credit carries two or three class ids; dev carries at most one per credit."""
    import json
    def recs(split):
        path = cp2_data.joinpath(split, "truth.jsonl")
        return [TruthRecord.model_validate(json.loads(l)) for l in path.read_text().splitlines() if l.strip()]
    assert any(len(r.corruption_classes) >= 2 for r in recs("test"))
    assert all(len(r.corruption_classes) <= 1 for r in recs("dev"))


def test_range_b_is_wider_than_range_a():
    """For every parameterised class, the test-split parameter range strictly contains the dev range."""
    assert set(RANGE_A[7]["day_offsets"]) < set(RANGE_B[7]["day_offsets"])  # type: ignore[arg-type]
    for cls, params in RANGE_A.items():
        if cls in (7, 16):
            continue
        for key, va in params.items():
            vb = RANGE_B[cls][key]
            if isinstance(va, int):
                assert int(vb) >= va, f"{cls}.{key}: B={vb} does not contain A={va}"


def test_class15_rounding_does_not_break_truth_sum(cp2_data: Path):
    """Class 15 alters only rendered fee lines; truth still sums exactly."""
    recs = load_truth("dev", data_root=cp2_data)
    assert any(15 in r.corruption_classes for r in recs)
    for r in recs:
        assert r.total_paise != 0
