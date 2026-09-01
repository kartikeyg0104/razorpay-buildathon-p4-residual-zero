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
    dumped = flags.model_dump()
    for name, value in dumped.items():
        if name == "f31_enumerate_cap":
            continue
        assert value is False, name
    assert dumped["f31_enumerate_cap"] == 32


def test_product_yaml_defaults_on():
    loaded = load_features()
    dumped = loaded.model_dump()
    for name, value in dumped.items():
        if name == "f31_enumerate_cap":
            continue
        assert value is True, name


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


def _a3_exact(flags: FeatureFlags) -> tuple[int, int]:
    """A3 member-set exact on dev, through the real eval arm."""
    from residual_zero.config import (
        load_fees, load_llm_config, load_profile, load_solver_config, load_tax_rates,
    )
    from residual_zero.ingest.settlement_report import load_settlement_report
    from residual_zero.ingest.source_root import SourceRoot

    from eval.arms.a3_full import run_a3
    from eval.loader import load_split
    from eval.metrics import exact_decomposition_counted
    from eval.truth_loader import load_truth

    root = Path("data")
    items, credits = load_split("dev", data_root=root)
    truth = {r.bank_credit_id: r.member_ids for r in load_truth("dev", data_root=root)}
    by_credit: dict[str, list] = {}
    for row in load_settlement_report(SourceRoot(DEV_RENDERED)):
        by_credit.setdefault(row.credit_id, []).append(row)
    result = run_a3(
        items, credits, by_credit, truth,
        load_tax_rates(), load_fees(), load_solver_config(), load_llm_config(),
        load_profile(Path("config").joinpath("profiles", "phase1.yaml")).reserve_bps,
        flags=flags,
    )
    counted = exact_decomposition_counted(result.predictions, truth)
    return counted.numerator, counted.denominator


def test_flags_off_exact_floor_is_enforced():
    """F55's exact floor. config/ci.yaml says a drop OR a rise fails — the core moved.

    The CI workflow step named "Flags-off exact floor" loaded this number and printed it
    without ever comparing anything, so the guard could not fail (found 2026-09). The
    comparison lives here, where `make test` actually runs it.
    """
    import yaml

    if not DEV_RENDERED.is_dir():
        pytest.skip("data/dev not present")
    ci = yaml.safe_load(Path("config").joinpath("ci.yaml").read_text(encoding="utf-8"))
    numerator, denominator = _a3_exact(FeatureFlags.all_off())
    assert f"{numerator}/{denominator}" == ci["dev_exact_floor"]
    assert denominator == ci["dev_split_n"]


def test_features_on_does_not_lower_exact():
    """Turning the product's features on may raise exact; it must never lower it."""
    if not DEV_RENDERED.is_dir():
        pytest.skip("data/dev not present")
    off, n_off = _a3_exact(FeatureFlags.all_off())
    on, n_on = _a3_exact(load_features())
    assert n_off == n_on
    assert on >= off, f"features on dropped exact from {off} to {on}"
