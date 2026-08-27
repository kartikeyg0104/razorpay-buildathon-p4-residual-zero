"""F23: three profiles, one solver config hash."""

from __future__ import annotations

from pathlib import Path

from residual_zero.config import config_digest, load_profile, load_solver_config


def test_solver_hash_identical_across_profile_loads():
    digest = config_digest(load_solver_config())
    for name in ("d2c.yaml", "saas.yaml", "travel.yaml"):
        profile = load_profile(Path("config").joinpath("profiles").joinpath(name))
        assert config_digest(load_solver_config()) == digest
        assert profile.subrupee_member_max == 13
    d2c = load_profile(Path("config").joinpath("profiles").joinpath("d2c.yaml"))
    saas = load_profile(Path("config").joinpath("profiles").joinpath("saas.yaml"))
    travel = load_profile(Path("config").joinpath("profiles").joinpath("travel.yaml"))
    assert d2c.refund_rate_bps > saas.refund_rate_bps
    assert travel.dispute_rate_bps > saas.dispute_rate_bps
    assert travel.representment_lag_days[1] >= travel.representment_lag_days[0]
