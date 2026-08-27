"""Configuration loading. This module is the NN-8 mechanism.

Every rate lives in ``config/`` as an integer count of basis points with a ``source_url`` and an
``as_of`` date, and :func:`load_tax_rates` / :func:`load_fees` **raise** on any unverified value.
Nothing in this system can run against a rate nobody checked — that is enforcement, not
documentation (ADR-6).

The autonomy threshold is handled the same way in reverse: it is unset until CP6 reads it off the
risk-coverage curve, and asking for it before then raises rather than defaulting to a number
somebody picked.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import canonical_json as _canonical_json
from .models import Instrument

_STRICT = ConfigDict(frozen=True, extra="forbid")

UNVERIFIED_PREFIX = "TBD-VERIFY"
DEFERRED_PREFIX = "TBD-CP"


class UnverifiedRateError(RuntimeError):
    """Raised when a config value is still ``TBD-VERIFY``.

    This is what makes NN-8 a mechanism rather than a promise: a plausible number cannot be
    substituted for a sourced one, because the system refuses to start without the source.
    """


class ThresholdNotDerivedError(RuntimeError):
    """Raised when the autonomy threshold is read before CP6 derives it from the §9.5 curve.

    A hand-picked threshold is a guess wearing a suit (spec §9.5), so the absence of a derived
    one is an error rather than a default.
    """


def _walk(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield ``(dotted_path, value)`` for every leaf in a nested mapping/sequence."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")
    else:
        yield path, node


def _reject_unverified(raw: Any, source: Path) -> None:
    """Raise :class:`UnverifiedRateError` if any leaf is still ``TBD-VERIFY``."""
    unverified = [p for p, v in _walk(raw) if isinstance(v, str) and v.startswith(UNVERIFIED_PREFIX)]
    if unverified:
        raise UnverifiedRateError(
            f"{source}: {len(unverified)} value(s) still unverified, so nothing may run against "
            f"this config (NN-8). Source each from a primary document and record its source_url "
            f"and as_of, or record why it cannot be sourced in PLAN-QUESTIONS.md. "
            f"Unverified keys: {', '.join(unverified)}"
        )


class ProvenanceEntry(BaseModel):
    """Where a non-rate configured value came from. Additive to PLAN-P1 D2's schema so that a
    synthetic contract term still has to say it is synthetic (NN-8's spirit)."""

    model_config = _STRICT

    source_url: str = Field(min_length=1)
    as_of: date
    synthetic: bool = False
    note: str | None = None


class RateEntry(BaseModel):
    """One rate: integer basis points, a primary source, and the date it was read."""

    model_config = _STRICT

    bps: int = Field(ge=0)
    source_url: str = Field(min_length=1)
    as_of: date
    synthetic: bool = False
    note: str | None = None
    base: str | None = None
    """For withholding: which base the rate applies to. See PLAN-QUESTIONS.md Q1."""

    @field_validator("bps", mode="before")
    @classmethod
    def _bps_must_be_integer(cls, v: Any) -> Any:
        if isinstance(v, bool) or isinstance(v, float):
            raise ValueError(
                f"rate must be an integer count of basis points, got {v!r}. A rate needing finer "
                f"resolution than one basis point gets a '_micro_bps' key, never a float (ADR-6)."
            )
        return v

    @model_validator(mode="after")
    def _synthetic_must_say_so(self) -> "RateEntry":
        if self.source_url == "synthetic" and not self.synthetic:
            raise ValueError(
                "source_url 'synthetic' requires synthetic: true — a private contract term must "
                "be labelled, not disguised as a sourced rate"
            )
        return self


class TaxRates(BaseModel):
    model_config = _STRICT

    gst_on_fee: RateEntry
    withholding: RateEntry


class FeeSchedule(BaseModel):
    model_config = _STRICT

    per_instrument_bps: dict[Instrument, RateEntry]
    bank_charge_paise: int = Field(ge=0)
    bank_charge: ProvenanceEntry
    reserve_bps: RateEntry

    @model_validator(mode="after")
    def _every_instrument_priced(self) -> "FeeSchedule":
        missing = sorted(i.value for i in Instrument if i not in self.per_instrument_bps)
        if missing:
            raise ValueError(
                f"no fee rate for instrument(s): {', '.join(missing)}. Fee is computed per "
                f"transaction from the instrument (spec §3.2), so every instrument needs an entry."
            )
        return self


class SearchConfig(BaseModel):
    model_config = _STRICT

    epsilon_rupees: int = Field(ge=0)
    epsilon_paise_equivalent: int = Field(ge=0)
    max_pool: int = Field(gt=0)
    max_axis_width_rupees: int = Field(gt=0)
    max_enum_nodes: int = Field(gt=0)
    enumerate_cap: int = Field(ge=2)
    require_nonempty: bool
    wallclock_backstop_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def _epsilon_units_agree(self) -> "SearchConfig":
        if self.epsilon_paise_equivalent != self.epsilon_rupees * 100:
            raise ValueError(
                f"epsilon_paise_equivalent ({self.epsilon_paise_equivalent}) must be 100x "
                f"epsilon_rupees ({self.epsilon_rupees}). Mixed units in a tolerance config is an "
                f"afternoon of phantom residuals."
            )
        return self


class WindowConfig(BaseModel):
    model_config = _STRICT

    base_days_before: int = Field(gt=0)
    widened_days_before: int = Field(gt=0)
    widened_kinds: tuple[str, ...]

    @model_validator(mode="after")
    def _widened_is_wider(self) -> "WindowConfig":
        if self.widened_days_before <= self.base_days_before:
            raise ValueError(
                "widened_days_before must exceed base_days_before; the asymmetry is what lets "
                "cross-window cases resolve at all (spec §5.5)"
            )
        return self


class SubWindowSplitConfig(BaseModel):
    model_config = _STRICT

    enabled: bool
    strategy: str
    max_attempts: int = Field(gt=0)


class DiagnosisConfig(BaseModel):
    model_config = _STRICT

    rate_match_tolerance_bps: int = Field(ge=0)
    min_rate_delta_paise: int = Field(ge=0)
    rounding_delta_ceiling_paise: int = Field(ge=0)


class OrderingScoreConfig(BaseModel):
    model_config = _STRICT

    expected_max_members: int = Field(gt=0)
    terms: tuple[str, ...]
    weights: str

    @field_validator("weights")
    @classmethod
    def _weights_uniform_in_phase1(cls, v: str) -> str:
        if v != "uniform":
            raise ValueError(
                "Phase 1 uses uniform weights deliberately: fitting six weights on a few hundred "
                "dev credits would overfit, and §9.5 uses the curve's shape rather than the "
                "score's calibration (PLAN-P1 D14)"
            )
        return v


class AutonomyConfig(BaseModel):
    """The autonomy threshold, which is *derived* at CP6 and unset before then."""

    model_config = _STRICT

    error_budget: str | None = None
    threshold: str | None = None
    threshold_source: str | None = None

    @model_validator(mode="after")
    def _threshold_needs_a_curve(self) -> "AutonomyConfig":
        if self.threshold is not None and self.threshold_source is None:
            raise ValueError(
                "autonomy.threshold requires a threshold_source naming the curve artifact it was "
                "read from. A threshold set by hand is a guess wearing a suit (spec §9.5)."
            )
        return self

    @property
    def derived_threshold(self) -> str:
        """The threshold, or raise. Never returns a default."""
        if self.threshold is None or self.threshold_source is None:
            raise ThresholdNotDerivedError(
                "the autonomy threshold has not been derived yet. CP6 reads it off the "
                "risk-coverage curve at the declared error budget; until then there is no "
                "threshold, and auto-clear must not proceed."
            )
        return self.threshold


class SolverConfig(BaseModel):
    model_config = _STRICT

    search: SearchConfig
    windows: WindowConfig
    sub_window_split: SubWindowSplitConfig
    diagnosis: DiagnosisConfig
    ordering_score: OrderingScoreConfig
    autonomy: AutonomyConfig

    @model_validator(mode="after")
    def _rounding_ceiling_tracks_epsilon(self) -> "SolverConfig":
        if self.diagnosis.rounding_delta_ceiling_paise != self.search.epsilon_paise_equivalent:
            raise ValueError(
                "diagnosis.rounding_delta_ceiling_paise must equal search.epsilon_paise_equivalent "
                "so it moves with the D6 bound rather than being an independent magic number"
            )
        return self


class MerchantProfile(BaseModel):
    """Generator stage 1 parameters. Parameterised now; F23's three profiles are Phase 3."""

    model_config = _STRICT

    name: str
    split: str
    accounts: int = Field(gt=0)
    settlement_dates_per_horizon: int = Field(gt=0)
    horizon_days: int = Field(gt=0)
    settlement_cycle_days: int = Field(ge=0)
    business_days_only: bool
    orders_per_day_per_account: int = Field(gt=0)
    order_amount_min_paise: int = Field(gt=0)
    order_amount_max_paise: int = Field(gt=0)
    instrument_mix_weights: dict[Instrument, int]
    refund_rate_bps: int = Field(ge=0)
    cross_window_refund_fraction_bps: int = Field(ge=0, le=10_000)
    dispute_rate_bps: int = Field(ge=0)
    representment_rate_bps: int = Field(ge=0, le=10_000)
    representment_lag_days: tuple[int, int]
    adjustment_rate_bps: int = Field(ge=0)
    reserve_bps: int = Field(ge=0)
    reserve_release_lag_days: int = Field(ge=0)
    fee_itemisation: str
    subrupee_member_max: int = Field(ge=0)
    counterparty_pool: str
    corruption_range: str
    stacked_corruptions: bool
    held_out_class: int | None = None

    @model_validator(mode="after")
    def _order_amounts_are_whole_rupees(self) -> "MerchantProfile":
        for field in ("order_amount_min_paise", "order_amount_max_paise"):
            value = getattr(self, field)
            if value % 100 != 0:
                raise ValueError(
                    f"{field}={value} is not a whole rupee. The Phase 1 profile keeps payments "
                    f"whole-rupee so they contribute zero rounding error, which is what bounds "
                    f"the search tolerance (PLAN-P1 D6)."
                )
        if self.order_amount_min_paise > self.order_amount_max_paise:
            raise ValueError("order_amount_min_paise exceeds order_amount_max_paise")
        return self

    @model_validator(mode="after")
    def _instrument_mix_sums_to_100(self) -> "MerchantProfile":
        total = sum(self.instrument_mix_weights.values())
        if total != 100:
            raise ValueError(f"instrument_mix_weights must sum to 100, got {total}")
        return self

    @model_validator(mode="after")
    def _itemisation_bounds_subrupee_members(self) -> "MerchantProfile":
        if self.fee_itemisation not in ("PER_SETTLEMENT_INSTRUMENT", "PER_PAYMENT"):
            raise ValueError(f"unknown fee_itemisation {self.fee_itemisation!r}")
        if self.fee_itemisation == "PER_SETTLEMENT_INSTRUMENT":
            # 2 lines per instrument (fee, GST) + withholding + reserve + bank charge.
            implied = 2 * len(Instrument) + 3
            if self.subrupee_member_max != implied:
                raise ValueError(
                    f"subrupee_member_max={self.subrupee_member_max} contradicts "
                    f"fee_itemisation=PER_SETTLEMENT_INSTRUMENT, which implies {implied}. The "
                    f"search tolerance is derived from this number (PLAN-P1 D6), so a mismatch "
                    f"silently invalidates the reachability argument."
                )
        return self


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the top level, got {type(raw).__name__}")
    return raw


def load_tax_rates(path: Path = Path("config/tax_rates.yaml")) -> TaxRates:
    """Load and validate statutory rates. Raises :class:`UnverifiedRateError` on any TBD-VERIFY."""
    raw = _load_yaml(path)
    _reject_unverified(raw, path)
    return TaxRates.model_validate(raw)


def load_fees(path: Path = Path("config/fees.yaml")) -> FeeSchedule:
    """Load and validate commercial terms. Raises :class:`UnverifiedRateError` on any TBD-VERIFY."""
    raw = _load_yaml(path)
    _reject_unverified(raw, path)
    return FeeSchedule.model_validate(raw)


def load_solver_config(path: Path = Path("config/solver.yaml")) -> SolverConfig:
    """Load solver tunables.

    Unlike the rate loaders this tolerates ``TBD-CP*`` markers in the ``autonomy`` block only,
    mapping them to ``None`` — the threshold is legitimately unset until CP6 derives it, and
    reading it before then raises :class:`ThresholdNotDerivedError` rather than defaulting.
    """
    raw = _load_yaml(path)
    _reject_unverified(raw, path)
    autonomy = raw.get("autonomy", {})
    if isinstance(autonomy, dict):
        raw["autonomy"] = {
            k: (None if isinstance(v, str) and v.startswith(DEFERRED_PREFIX) else v)
            for k, v in autonomy.items()
        }
    return SolverConfig.model_validate(raw)


def load_profile(path: Path) -> MerchantProfile:
    """Load a merchant profile for the generator."""
    raw = _load_yaml(path)
    _reject_unverified(raw, path)
    return MerchantProfile.model_validate(raw)


def _canonical_bytes(payload: Any) -> bytes:
    """Canonical JSON for digesting config. Delegates to canonical.py (D11)."""
    if not isinstance(payload, dict):
        raise TypeError(f"canonical payload must be a mapping, got {type(payload).__name__}")
    return _canonical_json(payload)


def config_digest(*models: BaseModel) -> str:
    """sha256 over the canonical JSON of the configs actually used, for the proof record."""
    digest = hashlib.sha256()
    for model in models:
        digest.update(_canonical_bytes(model.model_dump(mode="json")))
        digest.update(b"\x00")
    return digest.hexdigest()
