# Residual Zero — final release readiness

Generated 2026-09-01T17:48:24.822539+00:00 · commit `75cef5067474`

OFFICIAL TEST EVALUATION NOT RERUN — BUDGET EXHAUSTED.

**FINAL RELEASE STATUS: PASS** · 33/33 gates PASS, 0 FAIL, 0 NOT RUN

## Tests

| Invocation | Result | Runtime |
|---|---|---|
| `pytest -q` | 971 passed, 0 failed, 12 skipped | 39.858s |
| `RZ_E2E=1 pytest -q` | 983 passed, 0 failed | 77.007s |
| Clean venv `pytest -q` (Python 3.14.6) | 971 passed, 12 skipped | 96.71s |

Collected: 983 total = 971 unit/integration + 12 browser.
New invariant suite: `tests/invariants/` with 380 cases, including 315 generated property cases.

## Acceptance gates

| Gate | Status | Evidence |
|---|---|---|
| existing financial semantics preserved | PASS | 248 dev rows identical on 7 financial fields, changed=0 |
| deterministic engine remains authority | PASS | financial-table writers: ['src/residual_zero/verify.py'] |
| ai cannot modify financial state | PASS | 43 tools + 8 mutation prompts + 6 POST probes; delta=[] |
| ai cannot clear | PASS | CLEARED 0 -> 0 |
| ai cannot choose ambiguous solution | PASS | solver returns member_ids=() for AMBIGUOUS; no LLM selection path |
| financial state machine invariants | PASS | tests/invariants/test_financial_state_machine.py (121 cases) |
| money invariants | PASS | tests/invariants/test_money_invariants.py (54 cases): no float, no true division, no Decimal |
| solver invariants | PASS | tests/invariants/test_solver_invariants.py (43 cases incl. 315 generated) |
| uniqueness invariants | PASS | AMBIGUOUS never yields members; UNIQUE required for auto-clear |
| search budget invariants | PASS | BUDGET_EXCEEDED / REDUCED short-circuit away from CLEARED |
| date semantics preserved | PASS | no window or epsilon change; dev results byte-identical |
| source data unchanged | PASS | changed=[] |
| no hardcoded production financial metrics | PASS | artifact-free render fabricated=[]; production literals=0 |
| no secret leakage | PASS | .env gitignored=True, key literals=[] |
| dependencies valid | PASS | No broken requirements found. |
| clean environment tested | PASS | Python 3.14.6, pytest 971 passed |
| ai allowlist | PASS | 43 read-only tools; write-like not failing closed=[] |
| tool loop limits | PASS | MAX_TOOLS=8, MAX_REPEAT=2, time gate enforced |
| hallucination tests | PASS | fabricated displayed=0 |
| prompt injection tests | PASS | clear/verify/choose/ignore refused across phrasings; db unchanged |
| cross transaction isolation | PASS | per-transaction evidence; no fixture markers in metric APIs |
| cache isolation | PASS | repeat hit=True, keys sensitive=True, engine unaffected=True |
| api contract | PASS | /api/t04 matches committed cards; no traceback or writes_cleared leak on 6 POST probes |
| mcp | PASS | tools/list=13, refused exposed=[], write-like all rejected=True |
| human review boundary | PASS | human endpoints touched=['exception_work'] |
| audit integrity | PASS | hash chain verified; no key material in the AI audit log |
| browser e2e | PASS | 12/12 chromium against live HTTP |
| restart | PASS | listeners=1, cards identical=True, CLEARED 0->0 |
| determinism | PASS | 12 repeats distinct=1; permutation stable=True |
| performance regression acceptable | PASS | deterministic p50=1.711ms, ai p50=8.626ms (layers separate) |
| documentation accurate | PASS | live provider measured as YES; tool loop UNAVAILABLE; 14 judge questions answerable |
| demo | PASS | 8 screenshots, refusal captured |
| official evaluation artifacts preserved | PASS | artifacts/test/ byte-identical (13 files); official Test evaluation NOT RERUN — budget exhausted |

## Defects fixed in this phase

1. CI ran zero tests: the e2e conftest collection hook skipped the entire suite, so bare `pytest -q` and therefore `make test` reported success while executing nothing. Hook now scoped by marker and path.
2. Official match rates were hardcoded in the AI answer path: qa/corpus.py interpolated `residual-zero 159/239` into a corpus document and fell back to `129/239`/`239`/`3339/5973`; qa/desk_tools.py fell back to `521/800`. All now sourced from the committed card or `—`.
3. Refused tool requests left no audit trace: agent_loop returned early for unknown and repeat-limited names, so the intended `llm_rejected` record was never emitted. Rejections are now reported in `rejected_tools` without consuming a MAX_TOOLS slot.
4. Playwright was required by tests/e2e but declared in no dependency group. Added a separate `e2e` extra so browser deps stay out of runtime and dev installs.

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

## Performance, per layer

Layers are measured separately and never summed. AI latency is not part of reconciliation runtime.

| Layer | Operation | p50 | p99 |
|---|---|---|---|
| deterministic | `get_reconciliation` | 1.711 ms | 3.623 ms |
| deterministic | `get_reconciliation_statistics` | 0.231 ms | 0.305 ms |
| ai | `finance_ask` investigate | 8.626 ms | 19.646 ms |
| mcp | `finance_tool` | 90.195 ms | 118.026 ms |
| browser | `GET /` | 15.23 ms | 32.759 ms |

Committed deterministic batch card: `artifacts/dev/latency.md`.

## Architecture, unchanged

```
BANK CREDIT -> NORMALISATION -> CANDIDATE GENERATION -> SIGNED SUBSET-SUM
            -> RESIDUAL -> UNIQUENESS -> {UNIQUE -> VERIFICATION -> AUTO-CLEAR}
                                       {AMBIGUOUS -> HUMAN REVIEW}

USER -> AI -> READ-ONLY TOOLS -> STRUCTURED EVIDENCE -> EXPLANATION -> PRIORITISATION -> HUMAN
```

Never `LLM -> MATCH -> CLEARED`. The only writer of `reconciliation` is
`verify.write_cleared`, called from one flag-gated site in the orchestrator.
