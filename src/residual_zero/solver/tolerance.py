"""F32 derived search tolerance. The verifier is not an input of this module (NN-12)."""

from __future__ import annotations

from math import isqrt

from residual_zero.config import SolverConfig
from residual_zero.features import FeatureFlags


def ceil_k_sqrt_n(k: int, n: int) -> int:
    """Integer ``ceil(k · √n)`` paise. No true division."""
    if k < 1 or n < 0:
        raise ValueError("k must be >= 1 and n >= 0")
    if n == 0:
        return 0
    prod = k * k * n
    p = isqrt(prod)
    if p * p < prod:
        return p + 1
    return p


def paise_window_to_rupees(eps_paise: int) -> int:
    """Search axis is rupee-granular: ``ceil(ε_paise / 100)``."""
    if eps_paise < 0:
        raise ValueError("eps_paise must be >= 0")
    return (eps_paise + 99) // 100


def apply_derived_epsilon(cfg: SolverConfig, flags: FeatureFlags) -> SolverConfig:
    """When F32 is on, replace the D6 flat window with the fitted rupee window.

    Verifier acceptance is untouched: this copies only ``search.epsilon_*`` and the
    diagnosis ceiling that is required to track it.
    """
    if not flags.f32_derived_epsilon:
        return cfg
    rupees = cfg.search.derived_epsilon_rupees
    if rupees is None:
        return cfg
    paise = rupees * 100
    search = cfg.search.model_copy(
        update={"epsilon_rupees": rupees, "epsilon_paise_equivalent": paise}
    )
    diagnosis = cfg.diagnosis.model_copy(update={"rounding_delta_ceiling_paise": paise})
    return cfg.model_copy(update={"search": search, "diagnosis": diagnosis})
