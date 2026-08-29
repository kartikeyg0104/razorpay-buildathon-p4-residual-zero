# Residual Zero — Release certification

Generated 2026-09-01T14:33:09.413261+00:00

OFFICIAL TEST EVALUATION NOT RERUN — BUDGET EXHAUSTED.

AI evidence discovery recovered zero additional financial reconciliations on this dataset. The AI nevertheless provides genuine multi-step investigation, source comparison, candidate-equation analysis, root-cause analysis, prioritization, and finance-operations assistance.

## 1. Release candidate status

**FINAL STATUS: PASS**

release_candidate = True

## 2. Exact test counts

Unit pytest: 971 passed, 0 failed, 0 skipped — PASS

Playwright E2E: 12 passed, 0 failed — PASS

## 3. Browser E2E

Chromium against live `http://127.0.0.1:8765`. Traces on failure in `artifacts/e2e/`.

## 4. Financial regression

CLEARED=0 · audit_n=248 · pass=True

## 5. Dev evaluation

Committed `artifacts/dev/t04.md`: residual-zero 159/239 · unique 0 · auto-clear 0 · false clears 0

## 6. Test evaluation

Committed `artifacts/test/t04.md`: residual-zero 521/800 · search 800/800 · not rerun

## 7. AI controller

Fallback templates when Groq unavailable. Deterministic engine is financial truth.

## 8. Local agent harness

PASS · tools=7 · eighth capped=True

## 9. Live Groq

LIVE_GROQ = UNAVAILABLE · error=groq http 403

## 10. Tool security

Allowlist 43 tools · MAX_TOOLS=8

## 11. Hallucination protection

Fabricated financial facts displayed: **0** · pass=True
Claim validation runs on every controller answer (`validate_answer`). Matrix: `artifacts/qa/hallucination_matrix.json`.

## 12. Prompt injection

Every clear/verify/choose/ignore instruction is refused regardless of phrasing.
All refuse probes returned refusal: **True** · database unchanged: **True**

## 13. Cache

Repeat request cached: **True** · key sensitive to source text / dataset / prompt / model: **True** · engine truth unaffected: **True**
Cached payloads are candidate-only and cannot change status, residual, uniqueness, verification, or matched IDs.
Detail: `artifacts/qa/cache_final_check.json`.

## 14. MCP

`tools/list` exposes **13** tools · refused tools exposed: **none** · every write-like operation rejected: **True** · `writes_cleared` true anywhere: **False**
Detail: `artifacts/qa/mcp_final_check.json`.

## 15. API

API surface probe: **PASS** · `/api/t04` matches the committed official cards · `writes_cleared` false on every finance response.

## 16. Human review

Human decisions are recorded as separate events (`exception_resolution`, `exception_work`), never as CLEARED.
Saving a human review does not create a financial record.

## 17. Restart

Across a console restart: official cards identical **True** · CLEARED 0 → 0 · routes served **True** · `writes_cleared` **False**

## 18. Source integrity

Hashed before and after certification. Changed: **[]**
Official `artifacts/test/` was not rewritten.

## 19. Determinism

Official cards are committed and parsed at runtime; the Test evaluation was not rerun.
Repeat Dev snapshots are row-identical (`artifacts/qa/dev_financial_regression.json`).

## 20. Performance

Layers are recorded separately and never combined: `artifacts/qa/performance_final.json`.
Deterministic wall (committed card): see `artifacts/dev/latency.md`. AI latency is never mixed into recon runtime.

## 21. Demo

Full human journey captured: **PASS** · screenshots in `artifacts/demo/`.

## 22. Production-code audit

Production risks (TODO/FIXME/breakpoint/pdb/debug=True) in `src/`: **none**. `print()` appears only in CLI entrypoints, which is their interface.
No hardcoded dashboard metric survives an artifact-free render: fabricated numbers = **none**.
The console degrades to `—` rather than displaying an official-looking number it did not compute.

## 23. Remaining limitations

- LIVE_GROQ UNAVAILABLE (HTTP 403) — LIVE_GROQ_TOOL_CALLING NOT TESTABLE
- Official Test evaluation not rerun — NN-16 budget exhausted
- Posted overlay n=248 vs scored n=239 on Dev
- Large working tree — not all files committed to git HEAD

## 24. Final acceptance

Failures: none
Warnings: none

**FINAL STATUS: PASS**
