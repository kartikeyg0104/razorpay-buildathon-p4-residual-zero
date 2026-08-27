"""Normalisation is a pure function. The baselines depend on that (§5.4)."""

from __future__ import annotations

from residual_zero.normalise import extract_reference_token, normalise_narration


def test_normalisation_is_idempotent():
    """normalise_narration(normalise_narration(s)) == normalise_narration(s)."""
    samples = [
        "NEFT-AARAV TEXTILES PVT LTD",
        "IMPS/Meera  Krishnan",
        "UPI/Eastern Spices Co",
        "  Lotus   Pharma PVT. LTD.  ",
        "already normalised text",
        "",
    ]
    for sample in samples:
        once = normalise_narration(sample)
        assert normalise_narration(once) == once


def test_truncation_survives_normalisation():
    """A 35-char truncated name normalises without raising and stays distinct from the full name."""
    full = "Aarav Textiles Private Limited Mumbai"
    truncated = full[:35]
    assert len(truncated) == 35
    norm_full = normalise_narration(full)
    norm_trunc = normalise_narration(truncated)
    assert norm_trunc
    assert norm_trunc != norm_full


def test_abbreviations_expand_and_rails_strip():
    assert "private" in normalise_narration("NEFT-ACME PVT LTD")
    assert "limited" in normalise_narration("ACME PVT LTD")
    assert extract_reference_token("NEFT UTRABC123456789 SETTLEMENT") == "UTRABC123456789"
