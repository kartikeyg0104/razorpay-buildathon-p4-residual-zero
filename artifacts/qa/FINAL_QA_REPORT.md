# FINAL QA REPORT — Residual Zero

> Historical record of the competitive-engineering campaign. Superseded for browser status
> by `artifacts/qa/FINAL_RELEASE_READINESS.md`, where Playwright Chromium is 12/12 PASS.
> The financial figures, "not retuned", "not rerun" and LIVE_GROQ = UNAVAILABLE all still hold.

Competitive engineering upgrade 2026-09-01. Financial cards are **not retuned**. Official Test eval was **not rerun** (NN-16 budget 4 of 4). Browser Playwright: **NOT RUN in this campaign**. LIVE_GROQ = **UNAVAILABLE**.

## 1. Executive Summary

The deterministic engine is still the only financial authority. This upgrade added Proof Explorer, candidate-rejection reasons, a source agreement matrix, evidence-graph v2 edges, an allowlisted multi-step investigation loop with a visible trace, exclusive waterfall labelling, and an independent solver benchmark that does **not** replace production search.

**AI evidence discovery recovered zero additional financial reconciliations on this dataset.** The AI nevertheless provides genuine multi-step investigation, source comparison, candidate-equation analysis, root-cause analysis, prioritization, and finance-operations assistance.

FALSE CLEARS = 0. AUTO-CLEAR = 0. UNIQUE = 0 on official Dev and Test. Overlay does not write CLEARED.

## 2. Existing Architecture

Bank credit → normalisation → candidate pool → signed subset-sum (`solve_search`) → residual → uniqueness → verification → overlay FLAGGED. AI controller is read-only tools + optional Groq rewrite after claim validation. Eval LLM remains stub.

## 3. Competitive Research

See `docs/GITHUB_COMPETITIVE_AUDIT.md` and `docs/COMPETITIVE_FEATURE_MATRIX.md`.

Studied: europeanplaice/subset_sum (dpss), sebastienrousseau/reconcile-mcp, razorpay/razorpay-mcp-server, juspay/hyperswitch, opensyndicate/reconcile, payops-copilot, srikrishna0603/razorpay-buildathon.

## 4. Features Adopted

Proof Explorer; `explain_candidate_rejection`; source agreement matrix; evidence graph v2 (`method`/`verified`/`evidence_level`); LLM edges start unverified; agent investigation trace; investigation playbooks with terminals PROVEN / NOT_PROVEN / MISSING_DATA / AMBIGUOUS / CONFLICTING_SOURCES; exclusive uniqueness waterfall copy; independent brute-force solver benchmark; UI decision-boundary card.

## 5. Features Rejected

Replacing production `solve_search` with dpss; LLM `propose_match`; fuzzy similarity as truth; lowering uniqueness; treating POTENTIALLY_RECOVERABLE as reconciled; payment mutation MCP tools; confidence percentages as evidence; fabricating LIVE_GROQ=YES; overwriting `artifacts/test/`.

## 6. Solver Benchmark

Executed `scripts/benchmark_solvers.py` → `artifacts/competitive/solver_benchmark.json`.

Determinism repeat: True. Production replaced: False. dpss installed: False.

UNIQUE [1,2,3]→6 matches independent set {i00,i01,i02}. AMBIGUOUS [5,5]→5 matches class. NONE_FOUND [1,2,3]→100 matches class. n=20 UNIQUE both sides (production 0.17ms vs brute 541ms on this run). n=400 independent skipped. Zero-amount pools differ by design (production refuses 0 members).

## 7. AI Controller

Intent → allowlisted tools → observation → template → optional Groq explain → claim validation. REFUSE_CLEAR still cannot authorize a financial clear. Fallback templates PASS.

## 8. Agentic Tool Calling

`run_agent`: MAX_TOOLS=8, MAX_REPEAT=2, 30s. Unknown tools rejected. AMBIGUITY playbook now includes `compare_solutions` and `get_proof_explorer`. Live Groq next-tool: UNAVAILABLE (HTTP 403).

## 9. Evidence Graph

Deterministic edges plus `edges_v2`. Unverified extractions are `method=LLM`, `verified=false`, `evidence_level=1`. Only LEVEL 4/5 influence coverage.

## 10. Proof Explorer

`/proof/{credit_id}` and credit-page panel. Mixed twins: 2 solutions, choose_one false, distinguishing evidence NONE. Official `crd_001_acc_01_2025-01-09`: AMBIGUOUS, choose_one false.

## 11. Source Comparison

`compare_sources` returns `matrix` + `agreement`. AI may explain. AI cannot modify.

## 12. Candidate Comparison

`compare_solutions` delegates to Proof Explorer. No winner. `explain_candidate_rejection` always `accepted: false`, `writes_cleared: false`.

## 13. Root Cause

`get_root_cause` still emits structured metrics; Groq (when live) only explains them. This campaign: LIVE_GROQ UNAVAILABLE, deterministic text used.

## 14. Human Review

Human work status cannot be CLEARED (`tests/test_state_transitions.py`). AI event ≠ overlay write. No button writes CLEARED.

## 15. Security

Existing injection / path-traversal / unknown-tool tests remain green. Hostile bank descriptions stay data. `writes_cleared` false on every finance tool in this run.

## 16. API

Existing probes plus `GET /proof/{credit_id}` and `GET /api/finance/proof`. TestClient: mixed and official proof pages 200.

## 17. MCP

Read-only. Recon hits are not clears. `/mcp` and `/api/mcp/tool` still mounted. No payment mutations added.

## 18. Performance

Official Dev wall (committed card): 10066ms (`artifacts/dev/t04.md`). QA replay Dev wall: 87404ms (`artifacts/qa/official_dev/t04.md`). Official Test wall: 68299ms (`artifacts/test/t04.md`). Solver microbench n=20 production 169417ns. AI latency is not mixed into recon runtime. LIVE Groq latency this campaign: 0.169s then HTTP 403 (`artifacts/qa/groq_live.json`).

## 19. Dev Evaluation

Official `artifacts/dev/t04.md`: residual-zero 159/239, identified 148/239, verified 142/239, unique 0, ambiguous 236, none 3, auto-clear 0, false clears 0, search 239/239. Not rerun this upgrade. Delta 0.

## 20. Test Evaluation

Official `artifacts/test/t04.md`: residual-zero 521/800, identified 501/800, verified 464/800, unique 0, ambiguous 779, none 21, auto-clear 0, false clears 0, search 800/800. Not rerun this upgrade. Delta 0.

## 21. Before/After

See `artifacts/competitive/BEFORE_AFTER.md`. All official recon deltas = 0.

## 22. Failures Fixed

AMBIGUITY with a credit id now runs the multi-step agent (including Proof Explorer) instead of only `get_transaction_evidence`. Finance controller synthesizes a pack from `get_transaction` + `get_reconciliation` when the evidence pack tool is not in the 8-call budget. Mixed-desk `mixed_proof` is wired into credit pages.

## 23. Remaining Limitations

Official UNIQUE remains 0. Many residual-zero credits are genuinely AMBIGUOUS. Missing records cannot be invented. Groq 403 → fallback. POTENTIALLY_RECOVERABLE is not a match. Zero-amount members are excluded from search. Browser E2E not run.

## 24. Hackathon Demo

See `docs/DEMO_VERIFICATION.md` and `/demo`.

1. Dashboard: 800 scored, 521 residual-zero, 0 unique, 0 auto-clear, 0 false clears, 800/800 search. Overlapping metrics are not additive.
2. Mixed twins + official ₹59,645.39: residual 0, AMBIGUOUS.
3. INVESTIGATE WITH AI — live tool trace.
4. Proof Explorer — solutions A/B, common vs only-A/only-B, NONE distinguishing evidence.
5. “Why can't you just choose the first combination?” — both equations valid, human review.
6. Biggest blocker — structured root-cause metrics.
7. Highest-value unresolved — explorer / exposure queue.
8. “Clear this transaction.” — cannot authorize a financial clear. SQLite CLEARED count 0.

## Tests this upgrade

`.venv/bin/python -m pytest -q` → **569 passed in 22.79s** (`artifacts/qa/full_pytest.txt`). Previous recorded full suite: 508 passed.
