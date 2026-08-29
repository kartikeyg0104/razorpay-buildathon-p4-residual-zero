# Before / after — competitive upgrade

All financial metrics below are **executed official cards**, not retuned results.

Official Dev: `artifacts/dev/t04.md`  
Official Test: `artifacts/test/t04.md` (NN-16 gate budget 4 of 4; not rerun in this upgrade)  
QA replays live under `artifacts/qa/` and do not replace official Test.

AI evidence discovery recovered zero additional financial reconciliations on this dataset. The AI nevertheless provides genuine multi-step investigation, source comparison, candidate-equation analysis, root-cause analysis, prioritization, and finance-operations assistance.

| Metric | Previous | Final | Delta | Evidence |
|---|---|---|---|---|
| Dev residual-zero | 159/239 | 159/239 | 0 | artifacts/dev/t04.md |
| Dev member-identified | 148/239 | 148/239 | 0 | artifacts/dev/t04.md |
| Dev verified-linked | 142/239 | 142/239 | 0 | artifacts/dev/t04.md |
| Dev unique | 0 | 0 | 0 | artifacts/dev/t04.md |
| Dev ambiguous | 236 | 236 | 0 | artifacts/dev/t04.md |
| Dev none_found | 3 | 3 | 0 | artifacts/dev/t04.md |
| Dev auto-clear | 0 | 0 | 0 | artifacts/dev/t04.md |
| Dev false clears | 0 | 0 | 0 | artifacts/dev/t04.md |
| Dev search coverage | 239/239 | 239/239 | 0 | artifacts/dev/t04.md |
| Test residual-zero | 521/800 | 521/800 | 0 | artifacts/test/t04.md |
| Test member-identified | 501/800 | 501/800 | 0 | artifacts/test/t04.md |
| Test verified-linked | 464/800 | 464/800 | 0 | artifacts/test/t04.md |
| Test unique | 0 | 0 | 0 | artifacts/test/t04.md |
| Test ambiguous | 779 | 779 | 0 | artifacts/test/t04.md |
| Test none_found | 21 | 21 | 0 | artifacts/test/t04.md |
| Test auto-clear | 0 | 0 | 0 | artifacts/test/t04.md |
| Test false clears | 0 | 0 | 0 | artifacts/test/t04.md |
| Test search coverage | 800/800 | 800/800 | 0 | artifacts/test/t04.md |
| AI-assisted financial matches recovered | 0 | 0 | 0 | artifacts/dev/ai_recovery.json, artifacts/test/ai_recovery.json |
| LLM AUTO-CLEAR | 0 | 0 | 0 | overlay + finance tools writes_cleared |
| LIVE_GROQ | UNAVAILABLE | UNAVAILABLE | 0 | artifacts/qa/groq_live.json |
| Proof Explorer | absent as dedicated UI | `/proof/{id}` + credit panel | product | tests/test_proof_explorer.py |
| Independent solver benchmark | absent | artifacts/competitive/solver_benchmark.json | product | scripts/benchmark_solvers.py |

## Recovery attribution

No newly recovered official transactions.

`AI_USED_FOR_EXPLANATION_ONLY` on every Ask/controller path.

See `artifacts/competitive/recovery_attribution.json`.
