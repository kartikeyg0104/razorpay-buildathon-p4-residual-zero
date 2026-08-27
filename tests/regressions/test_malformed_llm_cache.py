"""Malformed cache entry is not parsed into a selected id."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.semantic.llm import CachedLLMClient, OfflineCacheMiss, StubLLMClient
from residual_zero.semantic.schema import CandidateEntity, EntityResolutionRequest


def test_malformed_cache_entry_is_not_a_wrong_id(tmp_path: Path):
    stub = StubLLMClient()
    client = CachedLLMClient(stub, tmp_path, offline=True, token_budget=10)
    request = EntityResolutionRequest(
        narration_norm="x",
        counterparty_text="y",
        candidates=(CandidateEntity(id="a", display_name="A"),),
    )
    key_files = list(tmp_path.glob("*.json"))
    # Plant a bogus file that lookup would only hit on the real key; also plant under the real key.
    from residual_zero.semantic.llm import CachedLLMClient as C
    real = client._path(client._key("resolve_entity", request.model_dump(mode="json")))
    real.write_text("{not-json", encoding="utf-8")
    with pytest.raises(OfflineCacheMiss):
        client.lookup_entity(request)
