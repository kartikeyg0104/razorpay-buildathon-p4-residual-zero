# Residual Zero — final submission status

Generated 2026-09-01T17:48:25.021656+00:00
Git HEAD `75cef5067474ceb5dff1119f0a445c896c1c7601` on `main` · 213 uncommitted entries · nothing committed by this phase

**FINAL CODE STATUS: READY FOR COMMIT**

OFFICIAL TEST EVALUATION NOT RERUN — BUDGET EXHAUSTED.

AI evidence discovery recovered zero additional financial reconciliations on this dataset.

## Tests

| Invocation | Result | Runtime |
|---|---|---|
| `pytest -q` (= `make test`) | 971 passed, 0 failed, 12 skipped | 39.858s |
| `RZ_E2E=1 pytest -q` | 983 passed, 0 failed | 77.007s |
| Clean venv `pytest -q` (Python 3.14.6) | 971 passed, 12 skipped | 96.71s |

Collected 983 total. The 12 skipped in the default run are the
browser tests, gated behind `RZ_E2E=1`.

## Playwright

12/12 chromium against http://127.0.0.1:8765 — live HTTP (not TestClient).

## Financial regression

248/248 Dev rows compared on 7 financial fields.
Changed rows: **0**. Verdict: **PRESERVED**. CLEARED rows: 0.

## Dev result — committed `artifacts/dev/t04.md`, not rerun

residual-zero 159/239 · unique 0 · auto-clear 0 · false clears 0 · search 239/239

## Test artifact result — committed `artifacts/test/t04.md`, NOT RERUN

residual-zero 521/800 · unique 0 · auto-clear 0 · false clears 0 · search 800/800

## Headline invariants

| Invariant | Value |
|---|---|
| False clears | 0 |
| Fabricated financial facts | 0 |
| LLM financial decisions | 0 |
| CLEARED across the write-path probe | 0 → 0 |

## AI safety

Write-path audit **PASS**. Only `src/residual_zero/verify.py`
writes financial tables. Allowlist 43 read-only tools; write-like names failing
closed with no exception: all rejected. AI layer SQL writes:
none; shell/eval: none.
Tool limits {'MAX_TOOLS': 8, 'MAX_REPEAT': 2, 'MAX_NS': 30000000000}. Local agent harness PASS.

## MCP · API · security · determinism · source

| Area | Result |
|---|---|
| MCP | PASS — 13 tools, write-like all rejected True, refused exposed none |
| API | PASS — `/api/t04` matches committed cards: True |
| Secrets | PASS — `.env` gitignored True, key literals none, audit sink strips key True |
| Hallucination | PASS |
| Prompt injection | PASS |
| Cache | PASS |
| Determinism | PASS — 12 repeats, 1 distinct result, permutation stable True |
| Source integrity | changed = [] |

`GROQ_API_KEY_PRESENT=true` — value never printed or logged.

## Live Groq

Provider **nvidia** · model `openai/gpt-oss-20b` · endpoint `None`
`LIVE_PROVIDER = YES` ·
`LIVE_TOOL_CALLING = UNAVAILABLE`. Groq on this key is HTTP 403.
The local agent harness is a separate, passing state and is not a live-Groq result.

## Acceptance gates

33 gates · failed none · not run none

## Remaining limitations

- Live provider: YES via nvidia (openai/gpt-oss-20b); tool loop UNAVAILABLE. Groq itself remains HTTP 403 on this key. The provider only rephrases deterministic facts and proposes the next read-only tool; every pick is validated against the allowlist before execution and it can never write financial state.
- NVIDIA NIM latency is 7-20 s per call versus sub-second for the deterministic engine, and the DeepSeek v4 pro/flash models in that catalogue exceeded 120 s on a realistic prompt, so they are unusable against the 30 s controller budget.
- Official Test evaluation NOT RERUN — NN-16 budget exhausted. The committed `artifacts/test/t04.md` is the source of every Test figure.
- Dev UNIQUE = 0 and auto-clear = 0 on this corpus. The threshold is refuse-all by design, so the auto-clear write path is exercised only by unit tests, never by the corpus.
- AI evidence discovery recovered zero additional reconciliations on this dataset.
- Posted console overlay n=248 differs from scored n=239 on Dev; the overlay is not the official card.
- `TABLE_OWNERS` is a convention, not a SQLite-level restriction. Enforcement is by fixed SQL per owner module plus tests/test_least_privilege.py.
- A single unexplained HTTP 500 on `/` was observed in an earlier session and is not reproducible. The server log is now retained by the E2E harness so a recurrence is diagnosable; no exception suppression was added.
- Working tree is large and uncommitted; nothing was committed by this phase.
