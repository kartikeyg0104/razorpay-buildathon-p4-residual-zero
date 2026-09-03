# Demo verification

Console: `.venv/bin/python -m residual_zero.console` → `http://127.0.0.1:8765`

Golden path is `/demo` (5–7 minutes). Official Track 04 cards are `artifacts/dev/t04.md` and `artifacts/test/t04.md`. Anything under `artifacts/qa/` is a **QA replay**, not an official overwrite.

Official demo credit: `crd_001_acc_01_2025-01-09` (₹59,645.39, residual 0.00, uniqueness AMBIGUOUS, eval REFUSE, console write REFUSE). Official unique remains **0/239**.

Constructed mixed desk: `/mixed`. Same solver, tiny FULL pools, epsilon 0. UNIQUE credits show **Eval ELIGIBLE**. AMBIGUOUS / NONE_FOUND show **REFUSE**. Overlay still does not write CLEARED. This is not official Track 04.

Proof Explorer: `/proof/crd_mix_ambiguous_twins` and `/proof/crd_001_acc_01_2025-01-09`. Two residual-zero explanations are displayed. The UI does not pick a winner.

| Step | Where | What to say |
|---|---|---|
| 0:00 | `/` | Residual-zero ≠ UNIQUE ≠ CLEARED. Overlapping metrics are not additive. Exclusive uniqueness sums to 800. Official unique is 0. |
| 0:30 | `/mixed` then UNIQUE + twins | Constructed UNIQUE: eval ELIGIBLE, console REFUSE. Twins: two explanations, residual 0. |
| 1:00 | `/proof/crd_mix_ambiguous_twins` then official proof | Common vs only-A/only-B. Distinguishing evidence NONE. Decision AMBIGUOUS. |
| 0:45 | `/credit/crd_001_acc_01_2025-01-09#auto-clear-decision` | Official ₹59,645.39 residual PASS, uniqueness FAIL, eval REFUSE. |
| 2:00 | INVESTIGATE WITH AI, then “Why can't you just choose the first combination?” | Tools, then fallback if LIVE_PROVIDER UNAVAILABLE. Both equations valid. Human review. Then refuse “Clear this transaction”. |
| 3:15 | `#human-decision` then `/exceptions` | AI is not the decision maker. Work status cannot be CLEARED. |
| 4:15 | `/explorer?kind=AMBIGUOUS` `/close` | Implemented explorer chips. Cash bridge unplugged. |
| 5:15 | `/challenge` `/books` `/recon` | Honest refusal. Books hold. MCP hit ≠ clear. |
| 6:15 | `/evidence` | Stop. Do not add an AI matcher. Do not move official unique off 0. |

LIVE_PROVIDER = YES only after a successful rewrite. Key present + HTTP 403 = UNAVAILABLE. DETERMINISTIC_CONTROLLER = PASS. LIVE_LLM_TOOL_LOOP = UNAVAILABLE until a live next-tool pick succeeds.

Browser Playwright: **12 passed** (`RZ_E2E=1 pytest tests/e2e`, Chromium, live `http://127.0.0.1:8765`). Screenshots in `artifacts/demo/`. Certification: `docs/DEMO_CERTIFICATION.md`.
