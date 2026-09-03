# Release manifest

Project:
Residual Zero

Release:
Track 04 Hackathon Certified Build

Git commit:
75cef5067474ceb5dff1119f0a445c896c1c7601 (branch main, 213 uncommitted entries)

Python:
3.13.7 on macOS-26.5.1-arm64-arm-64bit-Mach-O
Clean-environment verification: Python 3.14.6

Tests:
`pytest -q` 971 passed, 0 failed, 12 skipped (39.858s)
`RZ_E2E=1 pytest -q` 983 passed, 0 failed
Collected 983 = 971 unit/integration + 12 browser
Invariant suite tests/invariants/: 380 cases, 315 generated property cases

Browser E2E:
12/12 Chromium against live http://127.0.0.1:8765 (not TestClient)

Dev:
Committed `artifacts/dev/t04.md` — residual-zero 159/239, unique 0, auto-clear 0, false clears 0, search 239/239
Row-level regression: 248/248 rows identical on 7 financial fields

Test:
Committed `artifacts/test/t04.md` — residual-zero 521/800, unique 0, auto-clear 0, search 800/800
OFFICIAL TEST EVALUATION NOT RERUN — BUDGET EXHAUSTED

False clears:
0

AI:
Provider nvidia · model openai/gpt-oss-20b · local agent harness PASS
Allowlist 43 read-only tools · MAX_TOOLS 8 · MAX_REPEAT 2
LLM financial decisions 0 · fabricated financial facts 0

Live provider (NVIDIA NIM):
YES (None) · LIVE_PROVIDER_TOOL_CALLING NOT TESTABLE

MCP:
tools/list 13 tools · every write-like operation rejected True · writes_cleared true anywhere False

Security:
Write-path audit PASS — only `verify.py` writes financial tables; AI layer has no SQL write, no shell, no read-write handle
Hallucination PASS · prompt injection PASS · cross-transaction isolation PASS · secrets PASS

Determinism:
12 identical repeats yielded 1 distinct result · permuted candidate order stable True

Source integrity:
changed = [] · official `artifacts/test/` byte-identical

Demo:
PASS · 8 screenshots · CLEARED 0 after the full journey

Known limitations:
- Live provider: YES via nvidia (openai/gpt-oss-20b); tool loop UNAVAILABLE. Groq was removed on 2026-09-03 and is no longer a selectable backend. The provider only rephrases deterministic facts and proposes the next read-only tool; every pick is validated against the allowlist before execution and it can never write financial state.
- NVIDIA NIM latency is 7-20 s per call versus sub-second for the deterministic engine, and the DeepSeek v4 pro/flash models in that catalogue exceeded 120 s on a realistic prompt, so they are unusable against the 30 s controller budget.
- Official Test evaluation NOT RERUN — NN-16 budget exhausted. The committed `artifacts/test/t04.md` is the source of every Test figure.
- Dev UNIQUE = 0 and auto-clear = 0 on this corpus. The threshold is refuse-all by design, so the auto-clear write path is exercised only by unit tests, never by the corpus.
- AI evidence discovery recovered zero additional reconciliations on this dataset.
- Posted console overlay n=248 differs from scored n=239 on Dev; the overlay is not the official card.
- `TABLE_OWNERS` is a convention, not a SQLite-level restriction. Enforcement is by fixed SQL per owner module plus tests/test_least_privilege.py.
- A single unexplained HTTP 500 on `/` was observed in an earlier session and is not reproducible. The server log is now retained by the E2E harness so a recurrence is diagnosable; no exception suppression was added.
- Working tree is large and uncommitted; nothing was committed by this phase.
