"""Semantic cascade surface."""

from __future__ import annotations

from residual_zero.semantic.llm import CachedLLMClient, OfflineCacheMiss, StubLLMClient, TokenBudgetExceeded
from residual_zero.semantic.schema import (
    AmountLeakError,
    CandidateEntity,
    EntityResolutionRequest,
    EntityResolutionResponse,
    MONEY_PATTERN,
    NarrationRequest,
    NarrationResponse,
    assert_no_amounts,
)
from residual_zero.semantic.tiers import EntityRegistry, Resolution, registry_from_items, resolve, tier_mix

__all__ = [
    "AmountLeakError",
    "CachedLLMClient",
    "CandidateEntity",
    "EntityRegistry",
    "EntityResolutionRequest",
    "EntityResolutionResponse",
    "MONEY_PATTERN",
    "NarrationRequest",
    "NarrationResponse",
    "OfflineCacheMiss",
    "Resolution",
    "StubLLMClient",
    "TokenBudgetExceeded",
    "assert_no_amounts",
    "registry_from_items",
    "resolve",
    "tier_mix",
]
