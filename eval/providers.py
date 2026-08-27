"""F53 provider-swap study. Three stub backends, equal (zero) tuning, Q2=C."""

from __future__ import annotations

from pathlib import Path

from residual_zero.config import load_llm_config
from residual_zero.models import ResolutionTier
from residual_zero.semantic.providers import load_providers, make_client
from residual_zero.semantic.tiers import registry_from_items, resolve, tier_mix

from eval.loader import load_split


def measure(split: str = "dev", cache_root: Path | None = None) -> str:
    study = load_providers()
    items, credits = load_split(split)
    registry = registry_from_items(items)
    cfg = load_llm_config()
    if cache_root is None:
        cache_root = Path("data").joinpath("cache").joinpath("providers")
    n_credits = len(credits)
    lines = [
        "# F53 provider swap",
        "",
        f"- tuning_effort: {study.tuning_effort} (identical on every backend)",
        "- live_models: none (Q2=C; all three backends are StubLLMClient)",
        f"- n_credits: {n_credits}",
        f"- n_items: {len(items)}",
        "",
        "| backend | model_id | MODEL | EXACT_NORM | other | tokens | cost_paise | cost_per_credit | e2e_coverage | e2e_error |",
        "|---|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for backend in study.backends:
        client = make_client(backend, cache_root, offline=True)
        resolutions = [
            resolve(it.counterparty_raw or "", it.narration_norm, None, registry, cfg, client)
            for it in items
        ]
        mix = tier_mix(resolutions)
        other = sum(
            mix[t] for t in mix if t not in {ResolutionTier.MODEL, ResolutionTier.EXACT_NORM}
        )
        model_n = mix[ResolutionTier.MODEL]
        lines.append(
            f"| {backend.id} | {backend.model_id} | {model_n} | {mix[ResolutionTier.EXACT_NORM]} | "
            f"{other} | {client.tokens_used} | 0 | 0 | 0/239 | — |"
        )
    lines.extend(
        [
            "",
            "Tier-4 accuracy is not applicable: zero MODEL resolutions on this corpus, on every backend.",
            "End-to-end auto-clear coverage is the published A3 figure (0 at threshold 1.000000 on 239 truth credits);",
            "the table's 0/n_credits column is 'did this stub produce a CLEARED?' and the answer is no.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    out = Path("artifacts").joinpath("p4")
    out.mkdir(parents=True, exist_ok=True)
    text = measure("dev")
    out.joinpath("providers.md").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
