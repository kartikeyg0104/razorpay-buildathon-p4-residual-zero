"""F53: three backends, partitioned cache, equal (zero) tuning, no live spend."""

from __future__ import annotations

from pathlib import Path

from residual_zero.config import load_llm_config
from residual_zero.models import ResolutionTier
from residual_zero.semantic.llm import StubLLMClient
from residual_zero.semantic.providers import load_providers, make_client
from residual_zero.semantic.schema import CandidateEntity, EntityResolutionRequest, EntityResolutionResponse
from residual_zero.semantic.tiers import EntityRegistry, resolve, tier_mix


def test_three_backends_share_the_stub_protocol(tmp_path: Path):
    study = load_providers()
    assert study.tuning_effort == "none"
    assert len(study.backends) == 3
    ids = [b.model_id for b in study.backends]
    assert ids == ["stub-frontier", "stub-small", "stub-local-7b"]
    cache_root = tmp_path.joinpath("cache")
    for backend in study.backends:
        client = make_client(backend, cache_root, offline=False)
        assert client.model_id == backend.model_id
        assert client.cache_dir == cache_root.joinpath(backend.model_id)
        assert client.token_budget == 0


def test_cache_key_includes_model_id(tmp_path: Path):
    study = load_providers()
    cache_root = tmp_path.joinpath("cache")
    a = make_client(study.backends[0], cache_root, offline=False)
    b = make_client(study.backends[1], cache_root, offline=False)
    request = EntityResolutionRequest(
        narration_norm="pay",
        counterparty_text="zzzz unknown merchant",
        candidates=(CandidateEntity(id="ent_x", display_name="X"),),
    )
    stub_a = StubLLMClient()
    stub_a.next_resolve = EntityResolutionResponse(selected_id="ent_x", reason="ok")
    a.provider = stub_a
    a.token_budget = 10
    a.resolve_entity(request)
    assert a.lookup_entity(request) is not None
    assert b.lookup_entity(request) is None


def test_equal_tuning_no_tier4_on_a_known_registry():
    """Tiers 1–3 resolve the known names; no backend is given extra prompt engineering."""
    study = load_providers()
    cfg = load_llm_config()
    registry = EntityRegistry((CandidateEntity(id="ent_alpha", display_name="Aarav Textiles Private Limited"),))
    mixes = []
    for backend in study.backends:
        client = make_client(backend, Path("data").joinpath("cache").joinpath("llm"), offline=True)
        res = resolve("Aarav Textiles Pvt Ltd", "payment aarav", None, registry, cfg, client)
        mixes.append(tier_mix([res]))
    assert all(m[ResolutionTier.EXACT_NORM] == 1 for m in mixes)
    assert all(m[ResolutionTier.MODEL] == 0 for m in mixes)
