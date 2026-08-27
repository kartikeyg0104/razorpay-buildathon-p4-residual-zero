"""F32 overlay and the integer ceil(k·√n) helper."""

from __future__ import annotations

from residual_zero.config import load_solver_config
from residual_zero.features import FeatureFlags
from residual_zero.solver.tolerance import apply_derived_epsilon, ceil_k_sqrt_n, paise_window_to_rupees


def test_derived_window_is_two_and_flat_is_seven():
    cfg = load_solver_config()
    assert cfg.search.epsilon_rupees == 7
    assert cfg.search.derived_k == 21
    assert cfg.search.derived_epsilon_rupees == 2
    on = apply_derived_epsilon(cfg, FeatureFlags())
    off = apply_derived_epsilon(cfg, FeatureFlags.all_off())
    assert on.search.epsilon_rupees == 2
    assert off.search.epsilon_rupees == 7
    assert on.diagnosis.rounding_delta_ceiling_paise == 200


def test_ceil_k_sqrt_n_matches_the_fit_anchor():
    assert ceil_k_sqrt_n(21, 32) == 119
    assert paise_window_to_rupees(119) == 2
