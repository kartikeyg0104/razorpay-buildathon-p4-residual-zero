"""Config is the NN-8 mechanism: no rate runs without a primary source and a date."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from residual_zero.config import (
    ThresholdNotDerivedError,
    UnverifiedRateError,
    load_fees,
    load_profile,
    load_solver_config,
    load_tax_rates,
)

RATE_FILES = [Path("config/tax_rates.yaml"), Path("config/fees.yaml")]


def _rate_entries(node, path=""):
    """Yield (dotted_path, mapping) for every mapping that looks like a rate entry."""
    if isinstance(node, dict):
        if "bps" in node:
            yield path, node
        for key, value in node.items():
            yield from _rate_entries(value, f"{path}.{key}" if path else str(key))


@pytest.mark.parametrize("path", RATE_FILES, ids=lambda p: p.name)
def test_every_rate_has_source_and_as_of(path: Path):
    """No rate entry lacks source_url or as_of, whether or not its value is verified yet (NN-8)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = list(_rate_entries(raw))
    assert entries, f"{path} contains no rate entries; the scan is not testing anything"
    for dotted, entry in entries:
        assert "source_url" in entry, f"{path}:{dotted} has no source_url"
        assert "as_of" in entry, f"{path}:{dotted} has no as_of"
        assert entry["source_url"], f"{path}:{dotted} has an empty source_url"


def test_synthetic_terms_are_labelled():
    """A private contract term must say it is synthetic, not pose as a sourced rate."""
    raw = yaml.safe_load(Path("config/fees.yaml").read_text(encoding="utf-8"))
    for dotted, entry in _rate_entries(raw):
        if entry.get("source_url") == "synthetic":
            assert entry.get("synthetic") is True, f"fees.yaml:{dotted} is unsourced but unlabelled"


def test_tbd_verify_raises(tmp_path: Path):
    """The loader refuses to run against an unverified rate. This is NN-8 as a mechanism."""
    bad = tmp_path / "tax_rates.yaml"
    bad.write_text(
        "gst_on_fee:\n"
        "  bps: TBD-VERIFY\n"
        "  source_url: TBD-VERIFY\n"
        "  as_of: TBD-VERIFY\n"
        "withholding:\n"
        "  bps: 10\n"
        "  source_url: http://example.invalid\n"
        "  as_of: 2026-01-01\n",
        encoding="utf-8",
    )
    with pytest.raises(UnverifiedRateError) as excinfo:
        load_tax_rates(bad)
    assert "gst_on_fee.bps" in str(excinfo.value), "the error must name the offending key"


def test_the_real_tax_rates_file_loads_now_that_q1_is_sourced():
    """Q1 is answered: 194-O at 10 bps on GROSS_PAYMENTS, from Finance (No. 2) Bill 2024.

    The previous form of this test asserted the loader *refused* because withholding was
    TBD-VERIFY. That was the NN-8 mechanism working. The rate is now sourced from a primary
    document, so the loader must succeed — and the withholding entry must name the provision
    and the base, so a reviewer can check the number against the right statute.
    """
    rates = load_tax_rates()
    assert rates.withholding.bps == 10
    assert rates.withholding.base == "GROSS_PAYMENTS"
    assert "194-O" in (rates.withholding.note or "")
    assert "incometaxindia.gov.in" in rates.withholding.source_url


def test_rates_are_integer_bps(tmp_path: Path):
    """A fractional-bp rate fails validation rather than silently truncating (ADR-6)."""
    bad = tmp_path / "tax_rates.yaml"
    bad.write_text(
        "gst_on_fee:\n"
        "  bps: 1800.5\n"
        "  source_url: http://example.invalid\n"
        "  as_of: 2026-01-01\n"
        "withholding:\n"
        "  bps: 10\n"
        "  source_url: http://example.invalid\n"
        "  as_of: 2026-01-01\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception) as excinfo:
        load_tax_rates(bad)
    assert "basis point" in str(excinfo.value).lower() or "integer" in str(excinfo.value).lower()


def test_fees_load_and_price_every_instrument():
    """Fee is computed per transaction from the instrument, so every instrument needs a rate."""
    from residual_zero.models import Instrument

    fees = load_fees()
    for instrument in Instrument:
        assert instrument in fees.per_instrument_bps


def test_solver_config_loads_with_the_threshold_still_undecided():
    """After CP6 the threshold is derived and named by its curve artifact, never hand-picked."""
    cfg = load_solver_config()
    assert cfg.search.epsilon_rupees > 0
    assert cfg.autonomy.threshold == "1.000000"
    assert cfg.autonomy.threshold_source == "artifacts/dev/curve_a3.json"


def test_reading_the_threshold_before_it_is_derived_raises():
    """A hand-picked threshold without a source is rejected; a derived one is readable."""
    cfg = load_solver_config()
    assert cfg.autonomy.derived_threshold == "1.000000"


def test_epsilon_matches_the_derived_rounding_bound():
    """epsilon_rupees must equal floor((subrupee_member_max + 1) / 2) from PLAN-P1 D6.

    This is the assertion that keeps the search tolerance *derived* rather than chosen: change
    the profile's itemisation model and this test tells you the tolerance no longer follows from
    it.
    """
    from residual_zero.money import rounding_bound_rupees

    cfg = load_solver_config()
    profile = load_profile(Path("config/profiles/phase1.yaml"))
    assert cfg.search.epsilon_rupees == rounding_bound_rupees(profile.subrupee_member_max)


def test_profile_rejects_a_mismatched_subrupee_bound(tmp_path: Path):
    """A profile whose subrupee bound contradicts its itemisation invalidates D6 silently."""
    raw = yaml.safe_load(Path("config/profiles/phase1.yaml").read_text(encoding="utf-8"))
    raw["subrupee_member_max"] = 5
    bad = tmp_path / "profile.yaml"
    bad.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        load_profile(bad)
    assert "subrupee_member_max" in str(excinfo.value)


def test_profile_rejects_fractional_rupee_order_amounts(tmp_path: Path):
    """Whole-rupee payments are what bound the rounding accumulation (D6)."""
    raw = yaml.safe_load(Path("config/profiles/phase1.yaml").read_text(encoding="utf-8"))
    raw["order_amount_min_paise"] = 20_001
    bad = tmp_path / "profile.yaml"
    bad.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        load_profile(bad)
    assert "whole rupee" in str(excinfo.value)
