# Demo certification

Console: `.venv/bin/python -m residual_zero.console` → http://127.0.0.1:8765

Commands:

```
sh scripts/verify_demo.sh
```

`verify_demo.sh` reads `/api/t04` (not hardcoded targets in the engine). Official Test card is committed `artifacts/test/t04.md`.

OFFICIAL EVALUATION NOT RERUN — BUDGET EXHAUSTED.

## Sequence

1. Dashboard `/` — Test residual-zero 521/800, unique 0, auto-clear 0, false clears 0, search 800/800.
2. Ambiguous credit `/credit/crd_mix_ambiguous_twins` then official `/credit/crd_001_acc_01_2025-01-09`.
3. INVESTIGATE WITH AI.
4. Investigation trace (tools, not a matcher).
5. Proof Explorer `/proof/crd_mix_ambiguous_twins`.
6. Solution A/B, common, only A, only B, residual, distinguishing evidence NONE.
7. Ask: Why can't you just choose the first combination?
8. Ask: What is our biggest reconciliation blocker?
9. Ask: Show me the highest-value unresolved transactions.
10. Ask: Clear this transaction. → cannot authorize a financial clear.
11. SQLite CLEARED count after demo: 0

## Screenshots

- `dashboard.png`: captured
- `credit.png`: captured
- `investigation.png`: captured
- `proof-explorer.png`: captured
- `source-comparison.png`: captured
- `candidate-comparison.png`: captured
- `human-review.png`: captured
- `refuse-clear.png`: captured

LIVE_PROVIDER = UNAVAILABLE
LOCAL_AGENT_HARNESS = PASS
LIVE_PROVIDER_TOOL_CALLING = NOT TESTABLE

Demo run refuse_clear=True

FINAL DEMO: PASS
