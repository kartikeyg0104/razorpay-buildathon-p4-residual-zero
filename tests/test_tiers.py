"""Five-tier cascade: order, residue-only model, cache, offline, budget."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.config import load_llm_config
from residual_zero.models import ResolutionTier
from residual_zero.semantic.llm import CachedLLMClient, OfflineCacheMiss, StubLLMClient, TokenBudgetExceeded
from residual_zero.semantic.schema import CandidateEntity, EntityResolutionRequest, EntityResolutionResponse
from residual_zero.semantic.tiers import EntityRegistry, resolve, tier_mix


def _cfg():
    return load_llm_config()


def _registry() -> EntityRegistry:
    return EntityRegistry(
        (
            CandidateEntity(id="ent_alpha", display_name="Aarav Textiles Private Limited"),
            CandidateEntity(id="ent_beta", display_name="Beta Mills Limited"),
            CandidateEntity(id="ent_gamma", display_name="Gamma Exports"),
        ),
        tokens={"UTRABC12345678": "ent_alpha"},
    )


def test_tier_order_is_respected(tmp_path: Path):
    stub = StubLLMClient()
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=1000)
    res = resolve(
        "Aarav Textiles Pvt Ltd",
        "payment aarav",
        None,
        _registry(),
        _cfg(),
        client,
    )
    assert res.tier == ResolutionTier.EXACT_NORM
    assert stub.resolve_calls == []


def test_model_only_sees_the_residue(tmp_path: Path):
    stub = StubLLMClient()
    stub.next_resolve = EntityResolutionResponse(selected_id="ent_gamma", reason="closest")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=1000)
    registry = _registry()
    cfg = _cfg()
    known = [
        ("Aarav Textiles Pvt Ltd", "pay"),
        ("Beta Mills Ltd", "pay"),
    ]
    unknown = [
        ("zzzz not a real merchant xyz", "pay zzzz"),
        ("qqqq also unknown merchant", "pay qqqq"),
    ]
    for raw, nar in known:
        resolve(raw, nar, None, registry, cfg, client)
    for raw, nar in unknown:
        resolve(raw, nar, None, registry, cfg, client)
    assert len(stub.resolve_calls) == len(unknown)


def test_out_of_shortlist_response_becomes_an_exception(tmp_path: Path):
    stub = StubLLMClient()
    stub.next_resolve = EntityResolutionResponse(selected_id="not_in_set", reason="free text")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=1000)
    res = resolve("zzzz not a real merchant xyz", "pay", None, _registry(), _cfg(), client)
    assert res.tier == ResolutionTier.UNRESOLVED
    assert res.counterparty_id is None


def test_abstention_is_not_a_failure(tmp_path: Path):
    stub = StubLLMClient()
    stub.next_resolve = EntityResolutionResponse(selected_id=None, reason="abstain")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=1000)
    res = resolve("zzzz not a real merchant xyz", "pay", None, _registry(), _cfg(), client)
    assert res.tier == ResolutionTier.UNRESOLVED
    assert res.counterparty_id is None


def test_cache_hit_avoids_a_call(tmp_path: Path):
    stub = StubLLMClient()
    stub.next_resolve = EntityResolutionResponse(selected_id="ent_gamma", reason="ok")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=1000)
    request = EntityResolutionRequest(
        narration_norm="pay",
        counterparty_text="zzzz not a real merchant xyz",
        candidates=_registry().entities,
    )
    first = client.resolve_entity(request)
    assert first is not None
    assert client.provider_calls == 1
    second = client.resolve_entity(request)
    assert second == first
    assert client.provider_calls == 1


def test_offline_miss_raises(tmp_path: Path):
    stub = StubLLMClient()
    client = CachedLLMClient(stub, tmp_path, offline=True, token_budget=1000)
    request = EntityResolutionRequest(
        narration_norm="pay",
        counterparty_text="zzzz",
        candidates=_registry().entities,
    )
    with pytest.raises(OfflineCacheMiss):
        client.resolve_entity(request)
    assert stub.resolve_calls == []


def test_token_budget_fails_loudly(tmp_path: Path):
    stub = StubLLMClient()
    stub.tokens_per_call = 50
    stub.next_resolve = EntityResolutionResponse(selected_id="ent_gamma", reason="ok")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=10)
    request = EntityResolutionRequest(
        narration_norm="pay",
        counterparty_text="zzzz",
        candidates=_registry().entities,
    )
    with pytest.raises(TokenBudgetExceeded):
        client.resolve_entity(request)


def test_tier_mix_counts():
    from residual_zero.semantic.tiers import Resolution
    mix = tier_mix(
        [
            Resolution("a", ResolutionTier.EXACT_NORM, None),
            Resolution("b", ResolutionTier.FUZZY, 90),
            Resolution(None, ResolutionTier.UNRESOLVED, None),
        ]
    )
    assert mix[ResolutionTier.EXACT_NORM] == 1
    assert mix[ResolutionTier.FUZZY] == 1
    assert mix[ResolutionTier.UNRESOLVED] == 1
    assert mix[ResolutionTier.MODEL] == 0
