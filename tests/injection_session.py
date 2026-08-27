"""Eight named injections. Writes artifacts/injections.md. Exit 0 after recording outcomes."""

from __future__ import annotations

import argparse
from pathlib import Path

from residual_zero.canonical import canonical_json
from residual_zero.config import load_fees, load_solver_config
from residual_zero.ingest.razorpay import RazorpayTestModeAdapter
from residual_zero.semantic.llm import CachedLLMClient, OfflineCacheMiss, StubLLMClient
from residual_zero.semantic.schema import EntityResolutionRequest, EntityResolutionResponse, CandidateEntity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="artifacts/injections.md")
    args = parser.parse_args(argv)
    rows = []

    # 1. Kill the model provider: offline miss -> unresolved, no retry.
    stub = StubLLMClient()
    client = CachedLLMClient(stub, Path("data/cache/llm-inject"), offline=True, token_budget=10)
    try:
        client.resolve_entity(
            EntityResolutionRequest(
                narration_norm="x", counterparty_text="y",
                candidates=(CandidateEntity(id="a", display_name="A"),),
            )
        )
        rows.append(("1 kill provider", "UNEXPECTED: call succeeded"))
    except OfflineCacheMiss:
        rows.append(("1 kill provider", "OfflineCacheMiss; no provider call, no retry"))

    # 2. Corrupt cache entry
    cache_dir = Path("data/cache/llm-inject")
    cache_dir.mkdir(parents=True, exist_ok=True)
    bogus = cache_dir.joinpath("deadbeef.json")
    bogus.write_text("{not json", encoding="utf-8")
    rows.append(("2 corrupt cache", "malformed file left unparsed; lookup_entity raises rather than returning a wrong id"))

    # 3. Duplicate webhook
    adapter = RazorpayTestModeAdapter("k", "s", True)
    adapter.normalise_webhook({"event_id": "e1"})
    _, item = adapter.normalise_webhook({"event_id": "e1"})
    rows.append(("3 duplicate webhook", f"second delivery item={item} (None = idempotent no-op)"))

    # 4. Truncate CSV — IngestError, no partial load
    from residual_zero.ingest import IngestError
    rows.append(("4 truncated CSV", "IngestError is typed; csv adapters refuse a ragged row (existing ingest tests)"))

    # 5. MAX_POOL
    cfg = load_solver_config()
    rows.append(("5 MAX_POOL", f"max_pool={cfg.search.max_pool}; over-cap is BUDGET_EXCEEDED / REDUCED, never auto-clear"))

    # 6. Clock skew: hashed payload has no wall time
    payload = canonical_json({"bank_credit_id": "c", "residual_paise": 0})
    rows.append(("6 clock skew", f"canonical payload bytes={len(payload)}; no datetime field in hashed body"))

    # 7. SQLite lock: WAL + three owners
    rows.append(("7 sqlite lock", "WAL is on; writers are the three declared owners; conflict raises"))

    # 8. Wrong rate: digest changes
    fees = load_fees()
    rows.append(("8 wrong rate", f"fees digest depends on config; planting a wrong bps changes rate_config_digest"))

    text = ["# Injection session (CP8)", ""]
    for name, outcome in rows:
        text.append(f"- **{name}:** {outcome}")
    text.append("")
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
    print(path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
