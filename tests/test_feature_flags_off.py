"""All §6.2 features off → dispositions identical to the tagged Phase 1 baseline.

Designed at CP2.1 and extended by every later checkpoint. When this goes red, the
core moved while a feature was being added — stop and find out how.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.features import FeatureFlags, load_features
from residual_zero.models import Disposition

from eval.dispositions import collect_a3_dispositions, read_dispositions

BASELINE = Path("artifacts").joinpath("v1", "dispositions.json")
DEV_RENDERED = Path("data").joinpath("dev", "rendered")


def test_all_off_is_all_false():
    flags = FeatureFlags.all_off()
    assert flags.f33_conservation is False
    assert flags.f49_pii is False
    assert flags.f31_disambiguation is False
    assert flags.f40_journal is False
    assert flags.f37_clustering is False
    assert flags.f38_drift is False
    assert flags.f52_trace is False
    assert flags.f25_idempotency is False


def test_product_yaml_defaults_on():
    loaded = load_features()
    assert loaded.f33_conservation is True
    assert loaded.f31_disambiguation is True


def test_flags_off_matches_v1_baseline():
    if not BASELINE.is_file():
        pytest.fail(f"missing {BASELINE}; capture it at CP2.1 before adding features")
    if not DEV_RENDERED.is_dir():
        pytest.skip("data/dev not present")
    baseline = read_dispositions(BASELINE)
    got = collect_a3_dispositions("dev", Path("data"), FeatureFlags.all_off())
    assert set(got) == set(baseline), (
        f"credit-id set drifted: extra={sorted(set(got) - set(baseline))[:8]} "
        f"missing={sorted(set(baseline) - set(got))[:8]}"
    )
    changed = {cid: (baseline[cid], got[cid]) for cid in baseline if baseline[cid] != got[cid]}
    assert not changed, f"flags-off dispositions moved vs v1: {list(changed.items())[:8]}"
    allowed = {d.value for d in Disposition}
    assert set(got.values()) <= allowed
