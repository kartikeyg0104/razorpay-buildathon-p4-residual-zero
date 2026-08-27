"""Five-tier counterparty resolution. The model is reached only on the residue of tiers 1–3."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Iterable, NamedTuple, Sequence

from rapidfuzz import fuzz

from residual_zero.config import LLMRuntimeConfig
from residual_zero.models import LedgerItem, ResolutionTier
from residual_zero.normalise import extract_reference_token, normalise_narration
from residual_zero.semantic.llm import LLMClient, OfflineCacheMiss, TokenBudgetExceeded
from residual_zero.semantic.schema import CandidateEntity, EntityResolutionRequest, bind_selection


class EntityRegistry:
    """Closed set of counterparties. Built from the ledger, never from truth."""

    def __init__(self, entities: tuple[CandidateEntity, ...], tokens: dict[str, str] | None = None):
        self.entities = entities
        self.by_id = {e.id: e for e in entities}
        self._by_norm = {normalise_narration(e.display_name): e for e in entities}
        self._tokens = dict(tokens or {})

    def exact(self, raw: str) -> CandidateEntity | None:
        key = normalise_narration(raw)
        return self._by_norm.get(key)

    def by_token(self, token: str) -> CandidateEntity | None:
        eid = self._tokens.get(token.upper())
        if eid is None:
            return None
        return self.by_id.get(eid)

    def fuzzy(self, raw: str, k: int) -> list[tuple[str, int]]:
        needle = normalise_narration(raw)
        scored: list[tuple[str, int]] = []
        for entity in self.entities:
            hay = normalise_narration(entity.display_name)
            score = int(fuzz.ratio(needle, hay))
            scored.append((entity.id, score))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:k]


def registry_from_items(items: Sequence[LedgerItem]) -> EntityRegistry:
    by_norm: dict[str, CandidateEntity] = {}
    tokens: dict[str, str] = {}
    for item in items:
        raw = (item.counterparty_raw or "").strip()
        if not raw:
            continue
        norm = normalise_narration(raw)
        if not norm:
            continue
        if norm not in by_norm:
            digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
            eid = f"ent_{digest}"
            by_norm[norm] = CandidateEntity(id=eid, display_name=raw)
        eid = by_norm[norm].id
        tok = extract_reference_token(item.narration_raw) or extract_reference_token(raw)
        if tok and tok not in tokens:
            tokens[tok] = eid
    return EntityRegistry(tuple(by_norm.values()), tokens)


class Resolution(NamedTuple):
    counterparty_id: str | None
    tier: ResolutionTier
    score: int | None


def resolve(
    counterparty_raw: str,
    narration_norm: str,
    reference_token: str | None,
    registry: EntityRegistry,
    cfg: LLMRuntimeConfig,
    client: LLMClient | None,
    graceful_budget: bool = False,
) -> Resolution:
    """Tier 1 exact-normalised, tier 2 reference token, tier 3 rapidfuzz with a top-two margin,
    tier 4 model over a closed shortlist, tier 5 unresolved.
    """
    raw = counterparty_raw or ""
    hit = registry.exact(raw)
    if hit is not None:
        return Resolution(hit.id, ResolutionTier.EXACT_NORM, None)

    token = reference_token or extract_reference_token(narration_norm) or extract_reference_token(raw)
    if token:
        by_token = registry.by_token(token)
        if by_token is not None:
            return Resolution(by_token.id, ResolutionTier.REFERENCE_TOKEN, None)

    ranked = registry.fuzzy(raw, cfg.shortlist_k)
    if ranked:
        top_id, top_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        if top_score >= cfg.rapidfuzz_threshold and (top_score - second) >= cfg.top_two_margin:
            return Resolution(top_id, ResolutionTier.FUZZY, top_score)

    if client is None:
        return Resolution(None, ResolutionTier.UNRESOLVED, None)

    shortlist = tuple(registry.by_id[eid] for eid, _ in ranked[: cfg.shortlist_k] if eid in registry.by_id)
    if not shortlist:
        shortlist = registry.entities[: cfg.shortlist_k]
    request = EntityResolutionRequest(
        narration_norm=narration_norm,
        counterparty_text=raw,
        candidates=shortlist,
    )
    lookup = getattr(client, "lookup_entity", None)
    if getattr(client, "offline", False) and lookup is not None:
        cached = lookup(request)
        if cached is None:
            return Resolution(None, ResolutionTier.UNRESOLVED, None)
        bound = bind_selection(request, cached)
        if bound is None or bound.selected_id is None:
            return Resolution(None, ResolutionTier.UNRESOLVED, None)
        return Resolution(bound.selected_id, ResolutionTier.MODEL, None)
    try:
        response = client.resolve_entity(request)
    except TokenBudgetExceeded:
        if graceful_budget:
            return Resolution(None, ResolutionTier.UNRESOLVED, None)
        raise
    except OfflineCacheMiss:
        return Resolution(None, ResolutionTier.UNRESOLVED, None)
    if response is None or response.selected_id is None:
        return Resolution(None, ResolutionTier.UNRESOLVED, None)
    bound = bind_selection(request, response)
    if bound is None or bound.selected_id is None:
        return Resolution(None, ResolutionTier.UNRESOLVED, None)
    return Resolution(bound.selected_id, ResolutionTier.MODEL, None)


def tier_mix(resolutions: Iterable[Resolution]) -> dict[ResolutionTier, int]:
    """Counts per tier. This is F6's published number."""
    counts: Counter[ResolutionTier] = Counter()
    for res in resolutions:
        counts[res.tier] += 1
    return {tier: counts.get(tier, 0) for tier in ResolutionTier}
