"""F30: exhausted token budget becomes UNRESOLVED, it does not fail the run."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.models import ResolutionTier
from residual_zero.semantic.llm import CachedLLMClient, StubLLMClient, TokenBudgetExceeded
from residual_zero.semantic.schema import EntityResolutionRequest, EntityResolutionResponse
from residual_zero.semantic.tiers import EntityRegistry, resolve
from residual_zero.semantic.schema import CandidateEntity


def _registry() -> EntityRegistry:
    return EntityRegistry((CandidateEntity(id="ent_gamma", display_name="Gamma Mills"),))


def test_graceful_budget_returns_unresolved(tmp_path: Path):
    stub = StubLLMClient()
    stub.tokens_per_call = 50
    stub.next_resolve = EntityResolutionResponse(selected_id="ent_gamma", reason="ok")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=10)
    cfg = type("C", (), {"shortlist_k": 3, "rapidfuzz_threshold": 95, "top_two_margin": 5})()
    from residual_zero.config import load_llm_config
    llm = load_llm_config()
    got = resolve("zzzz unknown", "zzzz unknown", None, _registry(), llm, client, graceful_budget=True)
    assert got.tier is ResolutionTier.UNRESOLVED
    assert got.counterparty_id is None


def test_ungraceful_budget_still_raises(tmp_path: Path):
    stub = StubLLMClient()
    stub.tokens_per_call = 50
    stub.next_resolve = EntityResolutionResponse(selected_id="ent_gamma", reason="ok")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=10)
    from residual_zero.config import load_llm_config
    llm = load_llm_config()
    with pytest.raises(TokenBudgetExceeded):
        resolve("zzzz unknown", "zzzz unknown", None, _registry(), llm, client, graceful_budget=False)
