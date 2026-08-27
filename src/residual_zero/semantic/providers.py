"""F53: three named backends, cache partitioned by model_id, equal tuning effort."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.semantic.llm import CachedLLMClient, LLMClient, StubLLMClient

_STRICT = ConfigDict(frozen=True, extra="forbid")


class ProviderBackend(BaseModel):
    model_config = _STRICT

    id: str
    model_id: str
    token_budget: int = Field(ge=0)


class ProviderStudy(BaseModel):
    model_config = _STRICT

    tuning_effort: str
    backends: tuple[ProviderBackend, ...]


def load_providers(path: Path | None = None) -> ProviderStudy:
    """Load ``config/providers.yaml``. Missing file is a configuration error."""
    if path is None:
        path = Path("config").joinpath("providers.yaml")
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping")
    return ProviderStudy.model_validate(raw)


def make_client(
    backend: ProviderBackend,
    cache_root: Path,
    *,
    offline: bool,
    provider: LLMClient | None = None,
) -> CachedLLMClient:
    """Same stub protocol for every backend. Tuning effort is identical (none)."""
    inner = provider if provider is not None else StubLLMClient()
    return CachedLLMClient(
        inner,
        cache_root.joinpath(backend.model_id),
        offline=offline,
        token_budget=backend.token_budget,
        model_id=backend.model_id,
    )
