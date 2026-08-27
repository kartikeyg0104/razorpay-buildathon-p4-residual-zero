"""F51 degradation ladder. Coverage is allowed to fall; auto-clear error is not allowed to rise."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from residual_zero.features import FeatureFlags

_STRICT = ConfigDict(frozen=True, extra="forbid")


class Rung(str, Enum):
    NORMAL = "NORMAL"
    NO_MODEL = "NO_MODEL"
    NO_SEARCH = "NO_SEARCH"
    READ_ONLY = "READ_ONLY"
    HALTED = "HALTED"


_ORDER = (Rung.NORMAL, Rung.NO_MODEL, Rung.NO_SEARCH, Rung.READ_ONLY, Rung.HALTED)


class RungPolicy(BaseModel):
    model_config = _STRICT

    rung: Rung
    allow_model: bool
    allow_search: bool
    allow_writes: bool
    process_credits: bool


class DegradeConfig(BaseModel):
    model_config = _STRICT

    token_budget_exhausted: str
    provider_unavailable: str
    manual: str
    rolling_error_rate_bps: int = Field(ge=0)
    verifier_failure_rate_bps: int = Field(ge=0)


def load_degrade(path: Path | None = None) -> DegradeConfig:
    if path is None:
        path = Path("config").joinpath("degrade.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return DegradeConfig.model_validate(raw)


def policy_for(rung: Rung) -> RungPolicy:
    if rung is Rung.HALTED:
        return RungPolicy(
            rung=rung, allow_model=False, allow_search=False, allow_writes=False, process_credits=False,
        )
    if rung is Rung.READ_ONLY:
        return RungPolicy(
            rung=rung, allow_model=False, allow_search=True, allow_writes=False, process_credits=True,
        )
    if rung is Rung.NO_SEARCH:
        return RungPolicy(
            rung=rung, allow_model=False, allow_search=False, allow_writes=True, process_credits=True,
        )
    if rung is Rung.NO_MODEL:
        return RungPolicy(
            rung=rung, allow_model=False, allow_search=True, allow_writes=True, process_credits=True,
        )
    return RungPolicy(
        rung=rung, allow_model=True, allow_search=True, allow_writes=True, process_credits=True,
    )


def step(current: Rung, trigger: str, cfg: DegradeConfig) -> Rung:
    """Named triggers only. Unknown names leave the rung unchanged."""
    mapping = {
        "token_budget_exhausted": Rung(cfg.token_budget_exhausted),
        "provider_unavailable": Rung(cfg.provider_unavailable),
        "manual_halt": Rung.HALTED,
        "manual": Rung(cfg.manual),
    }
    target = mapping.get(trigger)
    if target is None:
        return current
    if _ORDER.index(target) < _ORDER.index(current):
        return current
    return target


def active_rung(flags: FeatureFlags, requested: Rung | None = None) -> Rung:
    if not flags.f51_degrade:
        return Rung.NORMAL
    return requested or Rung.NORMAL


def monotonic_coverage(coverages: list[tuple[Rung, int, int]]) -> bool:
    """coverages are (rung, n_cleared, n_credits) in ladder order. Coverage must not rise."""
    prev_cleared: int | None = None
    prev_n: int | None = None
    for _, cleared, n in coverages:
        if prev_cleared is not None and prev_n is not None:
            if cleared * prev_n > prev_cleared * n:
                return False
        prev_cleared, prev_n = cleared, n
    return True
