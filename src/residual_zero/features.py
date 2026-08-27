"""Phase 2 feature flags. Every §6.2 feature is disable-able (P2-EXEC).

``FeatureFlags.all_off()`` is the flags-off test's only input. It does not read
``config/features.yaml``, so a default-on product yaml cannot quietly change Phase 1
dispositions.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(frozen=True, extra="forbid")


class FeatureFlags(BaseModel):
    """One bool per Phase 2 feature, plus the F31 enumerate cap used only when that flag is on."""

    model_config = _STRICT

    f33_conservation: bool = True
    f49_pii: bool = True
    f55_ci: bool = True
    f31_disambiguation: bool = True
    f31_enumerate_cap: int = Field(default=32, ge=2)
    f40_journal: bool = True
    f37_clustering: bool = True
    f38_drift: bool = True
    f52_trace: bool = True
    f50_injection: bool = True
    f54_eval_diff: bool = True
    f24_adversarial: bool = True
    f25_idempotency: bool = True

    @classmethod
    def all_off(cls) -> "FeatureFlags":
        """Every §6.2 runtime switch false. Cap is unused while disambiguation is off."""
        return cls(
            f33_conservation=False,
            f49_pii=False,
            f55_ci=False,
            f31_disambiguation=False,
            f31_enumerate_cap=32,
            f40_journal=False,
            f37_clustering=False,
            f38_drift=False,
            f52_trace=False,
            f50_injection=False,
            f54_eval_diff=False,
            f24_adversarial=False,
            f25_idempotency=False,
        )


def load_features(path: Path | None = None) -> FeatureFlags:
    """Load ``config/features.yaml``. Missing file → all defaults (on)."""
    if path is None:
        path = Path("config").joinpath("features.yaml")
    if not path.is_file():
        return FeatureFlags()
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping")
    return FeatureFlags.model_validate(raw)
