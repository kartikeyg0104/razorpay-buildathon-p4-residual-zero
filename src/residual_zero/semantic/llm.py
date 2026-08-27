"""LLM client protocol, on-disk cache, offline miss-as-failure, hard token budget."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from residual_zero.canonical import canonical_json
from residual_zero.semantic.redact import RedactionSession, assert_no_pii, redact_entity_request
from residual_zero.semantic.schema import (
    EntityResolutionRequest,
    EntityResolutionResponse,
    NarrationRequest,
    NarrationResponse,
    assert_no_amounts,
    bind_selection,
)


class LLMClient(Protocol):
    def resolve_entity(self, request: EntityResolutionRequest) -> EntityResolutionResponse | None: ...
    def narrate(self, request: NarrationRequest) -> NarrationResponse | None: ...


class TokenBudgetExceeded(RuntimeError):
    """Raised when the hard per-run token budget is exhausted. Fails loudly (§12)."""


class OfflineCacheMiss(RuntimeError):
    """In offline mode a miss raises instead of calling out (NN-9)."""


class StubLLMClient:
    """Q2 option C: no spend. Records calls; returns abstention unless a test injects a reply."""

    def __init__(self) -> None:
        self.resolve_calls: list[EntityResolutionRequest] = []
        self.narrate_calls: list[NarrationRequest] = []
        self.next_resolve: EntityResolutionResponse | None = None
        self.next_narrate: NarrationResponse | None = None
        self.tokens_per_call: int = 1

    def resolve_entity(self, request: EntityResolutionRequest) -> EntityResolutionResponse | None:
        self.resolve_calls.append(request)
        return self.next_resolve

    def narrate(self, request: NarrationRequest) -> NarrationResponse | None:
        self.narrate_calls.append(request)
        return self.next_narrate


class CachedLLMClient:
    """Wraps a provider. Cache key = sha256 of canonical JSON of prompt_version, model_id, request.

    Stored at cache_dir/{key}.json. In offline mode a miss raises rather than calling out.
    """

    def __init__(
        self,
        provider: LLMClient,
        cache_dir: Path,
        offline: bool,
        token_budget: int,
        prompt_version: int = 1,
        model_id: str = "stub",
        enforce_pii: bool = False,
        redaction: RedactionSession | None = None,
    ) -> None:
        self.provider = provider
        self.cache_dir = cache_dir
        self.offline = offline
        self.token_budget = token_budget
        self.prompt_version = prompt_version
        self.model_id = model_id
        self.tokens_used = 0
        self.provider_calls = 0
        self.enforce_pii = enforce_pii
        self.redaction = redaction if redaction is not None else RedactionSession()
        self.egress_log: list[bytes] = []
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _guard(self, payload: bytes) -> None:
        assert_no_amounts(payload)
        if self.enforce_pii:
            assert_no_pii(payload)
        self.egress_log.append(payload)

    def _key(self, kind: str, request_dump: dict) -> str:
        payload = {
            "kind": kind,
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "request": request_dump,
        }
        digest = hashlib.sha256(canonical_json(payload)).hexdigest()
        return digest

    def _path(self, key: str) -> Path:
        return self.cache_dir.joinpath(f"{key}.json")

    def lookup_entity(self, request: EntityResolutionRequest) -> EntityResolutionResponse | None:
        key = self._key("resolve_entity", request.model_dump(mode="json"))
        path = self._path(key)
        if not path.is_file():
            return None
        raw = path.read_bytes()
        assert_no_amounts(raw)
        try:
            return EntityResolutionResponse.model_validate_json(raw)
        except Exception as exc:
            raise OfflineCacheMiss(f"malformed cache entry {path}: {exc}") from exc

    def resolve_entity(self, request: EntityResolutionRequest) -> EntityResolutionResponse | None:
        outbound = request
        if self.enforce_pii:
            outbound = redact_entity_request(request, self.redaction)
        payload = canonical_json({"kind": "resolve_entity", "request": outbound.model_dump(mode="json")})
        self._guard(payload)
        cached = self.lookup_entity(outbound)
        if cached is not None:
            return bind_selection(outbound, cached)
        if self.offline:
            raise OfflineCacheMiss("offline cache miss; refusing to call the provider (NN-9)")
        self._charge(getattr(self.provider, "tokens_per_call", 1))
        self.provider_calls += 1
        response = self.provider.resolve_entity(outbound)
        if response is None:
            return None
        bound = bind_selection(outbound, response)
        if bound is None:
            return None
        key = self._key("resolve_entity", outbound.model_dump(mode="json"))
        self._path(key).write_bytes(bound.model_dump_json().encode("utf-8"))
        return bound

    def narrate(self, request: NarrationRequest) -> NarrationResponse | None:
        dump = request.model_dump(mode="json")
        payload = canonical_json({"kind": "narrate", "request": dump})
        self._guard(payload)
        key = self._key("narrate", dump)
        path = self._path(key)
        if path.is_file():
            raw = path.read_bytes()
            assert_no_amounts(raw)
            if self.enforce_pii:
                assert_no_pii(raw)
            return NarrationResponse.model_validate_json(raw)
        if self.offline:
            raise OfflineCacheMiss("offline cache miss; refusing to call the provider (NN-9)")
        self._charge(getattr(self.provider, "tokens_per_call", 1))
        self.provider_calls += 1
        response = self.provider.narrate(request)
        if response is None:
            return None
        path.write_bytes(response.model_dump_json().encode("utf-8"))
        return response

    def _charge(self, tokens: int) -> None:
        nxt = self.tokens_used + tokens
        if nxt > self.token_budget:
            raise TokenBudgetExceeded(
                f"token budget {self.token_budget} exhausted (used {self.tokens_used}, need {tokens})"
            )
        self.tokens_used = nxt
