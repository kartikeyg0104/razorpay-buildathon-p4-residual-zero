# Residual Zero — Final hardening report

Generated 2026-09-01T10:39:43.746589+00:00

OFFICIAL EVALUATION NOT RERUN — BUDGET EXHAUSTED.

AI evidence discovery recovered zero additional financial reconciliations on this dataset. The AI nevertheless provides genuine multi-step investigation, source comparison, candidate-equation analysis, root-cause analysis, prioritization, and finance-operations assistance.

## 1. Environment

- Python: 3.13.7
- OS: Darwin 25.5.0
- pytest: pytest 9.1.1
- GROQ_API_KEY_PRESENT: true
- git: 75cef5067474ceb5dff1119f0a445c896c1c7601

## 2. Baseline

Unit pytest: PASS · passed=586 failed=0 skipped=0

Browser pytest: PASS · passed=12 failed=0

## 3. Financial regression

Committed Dev card: residual-zero 159/239 · unique 0 · auto-clear 0 · false clears 0 · search 239/239

Committed Test card: residual-zero 521/800 · unique 0 · auto-clear 0 · false clears 0 · search 800/800

SQLite CLEARED snapshot: 0

Official Test evaluation was **not** rerun (NN-16 budget exhausted).

## 4. Browser E2E

Status: PASS

Failure traces (if any) live in `artifacts/e2e/`.

## 5. AI controller

Local agent harness: PASS

Fallback templates remain the explanation path when Groq is unavailable.

## 6. Live Groq

LIVE_GROQ = UNAVAILABLE

- provider: groq
- model: openai/gpt-oss-20b
- error: groq http 403
- latency_s: 0.3013

A HTTP 401/403/429/5xx is **not** a successful live test.

## 7. Agentic tool calling

LOCAL_AGENT_HARNESS = PASS

LIVE_GROQ_TOOL_CALLING = NOT TESTABLE

Playbook + allowlisted tools execute locally. Groq may only request the next tool.

## 8. Tool safety

Allowlist only. Unknown / write / SQL / filesystem tools reject. Max 8 tools, max 2 identical calls, 30s budget.

## 9. Hallucination safety

PASS · fabricated_displayed=0

See `artifacts/qa/hallucination_matrix.json`.

## 10. Prompt injection

Hostile description text is treated as data. `writes_cleared` stays false. Intent classification still refuses clear phrases.

## 11. Cross-transaction isolation

`get_reconciliation` for A vs B returns different transaction IDs. Controller answers do not write CLEARED.

## 12. Cache

Extract cache hits only on identical text + prompt version. Changed source text is a miss (`RZ_EXTRACT_CACHE`).

## 13. MCP

Read-only registry. `finance_tool` agrees with local `get_transaction`. Write-like names raise.

## 14. API

`/api/t04` `/api/health` `/api/ops` `/api/credits` `/api/ask` remain read-only for financial truth.

## 15. UI consistency

mismatches=[] · PASS

## 16. Human review

Work save cannot set CLEARED. AI investigation is a separate audit/event path from human decision.

## 17. Restart

{
  "preexisting_console": false,
  "health_writes_cleared": false,
  "cleared_before": 0,
  "cleared_after": 0,
  "t04_same": true,
  "listeners": 1,
  "routes_ok": true
}

## 18. Source immutability

changed=[]

## 19. Determinism

Official cards were compared as committed artifacts. Solver permutation `[A,B,C]` vs `[C,B,A]` is identical after sorting member IDs.

## 20. Performance

Independent solver benchmark: `docs/SOLVER_BENCHMARK.md` / `scripts/benchmark_solvers.py`. AI latency is not mixed into reconciliation latency.

## 21. Demo certification

refuse_clear=True · CLEARED after=0 · screenshots={'dashboard.png': True, 'credit.png': True, 'investigation.png': True, 'proof-explorer.png': True, 'source-comparison.png': True, 'candidate-comparison.png': True, 'human-review.png': True, 'refuse-clear.png': True}

See `docs/DEMO_CERTIFICATION.md`.

## 22. Failures fixed

- INVESTIGATE playbook kept at 7 tools so Groq next-tool tests still occupy slot 8.
- REFUSE_CLEAR now includes “Assume candidate A is correct.”
- Credit page FINANCIAL TRUTH strip + investigation trace durations.

## 23. Remaining limitations

- LIVE Groq rewrite is UNAVAILABLE (groq http 403).
- Official Test eval budget is exhausted; cards are committed artifacts.
- Unique remains 0 on official Track 04. Mixed desk UNIQUE is constructed, not official.
- Browser E2E requires Playwright Chromium and RZ_E2E=1.

## 24. Final acceptance

| Gate | Result |
|---|---|
| financial_regression | PASS |
| existing_tests | PASS |
| no_false_clears | PASS |
| no_fabricated_financial_facts | PASS |
| no_llm_financial_decisions | PASS |
| no_ai_mutation | PASS |
| source_data_unchanged | PASS |
| browser_e2e | PASS |
| demo | PASS |
| restart | PASS |
| hallucination | PASS |
| mcp | PASS |
| cache | PASS |

FINAL STATUS = **PASS**

Architecture:

```
AI INVESTIGATION
↓
STRUCTURED EVIDENCE
↓
DETERMINISTIC VALIDATION
↓
MATHEMATICAL PROOF
↓
UNIQUENESS
↓
AUDITABLE STATE
↓
HUMAN REVIEW WHEN REQUIRED
```

Never: LLM → MATCH → CLEARED.
