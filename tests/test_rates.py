"""F38: no alert without min_sample; FP on undrifted points is 0."""

from __future__ import annotations

from residual_zero.config import load_fees
from residual_zero.models import Instrument
from residual_zero.rates import MIN_SAMPLE, regress


def test_below_min_sample_never_alerts():
    fees = load_fees()
    points = [(Instrument.CARD, "2025-W02", 10_000, 200)] * (MIN_SAMPLE - 1)
    reports = regress(points, fees)
    assert reports
    assert all(not r.alert for r in reports)


def test_contracted_rate_inside_band_is_silent():
    fees = load_fees()
    # 2% of 10_000 = 200 paise fee; contracted CARD is 200 bps.
    points = [(Instrument.CARD, "2025-W02", 10_000, 200)] * MIN_SAMPLE
    reports = regress(points, fees)
    assert len(reports) == 1
    assert reports[0].effective_bps == 200
    assert reports[0].alert is False
