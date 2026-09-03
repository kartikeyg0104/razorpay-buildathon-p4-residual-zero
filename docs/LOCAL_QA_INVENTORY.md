# Residual Zero — Local QA inventory

Frozen from filesystem and executed commands on 2026-08-29. Production logic was not changed to produce this file.

Repository root: `/Users/kartikey0104/Desktop/outputs/residual-zero`

| Component | Location | Purpose | How tested | Current test coverage | Known risks |
|---|---|---|---|---|---|
| Reconciliation orchestrator | `src/residual_zero/orchestrator.py` | Declared overlay + search; dispositions; no auto-clear at threshold 1.000000 | `pytest` + official A3 | `tests/test_named_declared.py`, `tests/test_settlement_ops.py`, `eval/arms/a3_full.py` | Residual-zero ≠ UNIQUE. Overlay must not write CLEARED. |
| Search solver | `src/residual_zero/solver/{fastpath,enumerate,bitset_dp,prune}.py` | Signed subset-sum, uniqueness, budget | `pytest -q` subset + `scripts/qa_campaign.py` | `tests/test_uniqueness.py`, `tests/test_solution_sets.py`, `tests/test_scale_search.py`, `tests/test_solver_properties.py` | Permutation of the same ids must be one solution. BUDGET_EXCEEDED must not become a guess. |
| Candidate window | `src/residual_zero/candidates.py` | `[D-5, D-1]` plus widened kinds | existing window tests + official eval | `tests/test_candidates.py`, `eval/window_strategies.py` | Must not globally widen to raise match rate. |
| Money / fees / tax | `src/residual_zero/money.py`, `config/fees.yaml`, `config/tax_rates.yaml` | Integer paise only | `tests/test_money.py`, `tests/test_rates.py`, `tests/test_arithmetic_invariant.py` | Strong unit coverage | No float literals in `src/` except `ordering.py`. |
| Settlement ingest | `src/residual_zero/ingest/settlement_report.py` | Declared lines keyed by `credit_id` + `item_id` | ingest tests + dataset integrity | `tests/test_ingest.py` | No `member_id` column exists. Join is `item_id → ledger.id`. |
| Bank / ledger ingest | `src/residual_zero/ingest/csv_bank.py`, `csv_ledger.py` | Load rendered CSVs | ingest + integrity script | `tests/test_ingest.py`, `tests/test_normalise.py` | Source CSVs must stay immutable during eval. |
| Official eval CLI | `eval/cli.py`, `eval/arms/a3_full.py` | Official Dev 239 / Test 800 | `--full` to `artifacts/qa/official_*` | `tests/test_arms_*.py` | Test-split NN-16 official budget is 4/4. QA replay must not clobber `artifacts/test/t04.md`. |
| Ground truth | `data/{dev,test}/truth.jsonl` | Eval-only member sets | `eval/truth_loader.py` | `tests/test_no_leakage.py` | `src/` must not open truth. |
| Finance tools | `src/residual_zero/qa/finance_tools.py`, `investigate_tools.py` | Read-only structured JSON | `tests/test_finance_controller.py` + `scripts/qa_campaign.py` | 38 named tools | Tools must never write CLEARED / MATCHED / VERIFIED. |
| AI controller | `src/residual_zero/qa/finance_controller.py`, `agent_loop.py` | Intent → tools → evidence → template → optional NVIDIA NIM | fallback + live provider probe | `tests/test_finance_controller.py`, `tests/test_agent_loop.py` | LLM cannot select a financial match. |
| Provider client (NVIDIA NIM) | `src/residual_zero/semantic/provider.py` | Optional rewrite / next-tool | live request if key present | `tests/test_provider.py` (`live_enabled` false in pytest) | Never log API keys. Pytest stays offline unless `RZ_LLM_TEST=1`. |
| Evidence extract / graph | `src/residual_zero/qa/evidence_extract.py`, `evidence_validate.py`, `evidence_ops.py` | Candidate evidence only | `tests/test_evidence_discovery.py` | Extract eval in `artifacts/dev/extract_eval.json` | Bank narrations contain no SET-/INV-/ord_ tokens. Recovered matches = 0. |
| AI audit | `src/residual_zero/qa/finance_audit.py` | Append-only JSONL | campaign + restart | `artifacts/console/ai_audit.jsonl` | Keys stripped. Pytest skips write unless `RZ_AI_AUDIT`. |
| Console / API | `src/residual_zero/console/app.py`, `extra.py`, `ext_api.py` | FastAPI + Jinja desk | curl via `scripts/qa_api_probe.py` | `tests/test_console.py` | Stale process can 404 `/explorer`. Restart after logic changes. |
| Frontend templates | `src/residual_zero/console/templates/*.html`, `static/` | Dashboard, credit, ask, explorer | HTTP 200 + substring checks | Not browser-tested in this campaign unless noted | HTTP success ≠ visual correctness. |
| SQLite | `artifacts/dev/ledger.sqlite` | Audit / books / overlay reads | `make verify-audit` style checks | `tests/test_audit_chain.py` | Overlay must not mutate reconciliation to CLEARED. |
| Dev datasets | `data/dev/rendered/{bank,ledger,settlement}.csv` | 239 bank credits | integrity + hashes | Official A3 | Do not modify. |
| Test datasets | `data/test/rendered/{bank,ledger,settlement}.csv` | 800 bank credits | integrity + hashes | Official A3 | Do not modify. |
| Config | `config/*.yaml`, `config/profiles/` | Solver, fees, tax, LLM stub, flags | `tests/test_config.py` | Eval LLM is stub (`config/llm.yaml`) | NVIDIA NIM is Ask-only. Flags-off floor 129/239. |
| Environment | `.env` (gitignored), `.env.example` | NVIDIA key / model | presence-only report | — | Never print key values. |
| Tests | `tests/` (103 test files, incl. `tests/invariants/`) | Unit + integration | `pytest -q` | Baseline captured in `artifacts/qa/baseline_pytest.txt` | `filterwarnings = error`. |
| Package | `pyproject.toml`, `.venv` | setuptools, pytest 9.1.1, CPython 3.13.7 | `pip list` | — | `ortools` / `lxml` listed in pyproject but absent from this venv `pip list`. Suite still ran. |
| Docs | `docs/*`, `PLAN-P*.md`, `README.md` | Spec, decisions, evaluation log | read-only | — | Official t04 numbers live in `artifacts/{dev,test}/t04.md`. |
| QA artifacts | `artifacts/qa/` | This campaign | generated from execution | — | Do not hardcode metrics. |

## Executed environment snapshot (this campaign)

- Python: CPython 3.13.7 (`.venv/bin/python`)
- System `python3`: `/opt/homebrew/bin/python3` (do not use for pytest)
- pytest: 9.1.1
- Package manager: pip 26.2.1 inside `.venv`
- AI_PROVIDER: `nvidia` (function default `nvidia`; NVIDIA NIM is the only backend)
- AI_MODEL: unset
- AI_MODEL: `openai/gpt-oss-20b`
- NVIDIA_API_KEY: present
- AI_API_KEY: missing
- live_enabled() outside pytest: True
- Database default: `artifacts/dev/ledger.sqlite` if present
- Entry points: `.venv/bin/python -m residual_zero.console` (port 8765); `python -m eval.cli`

## Official committed baselines (not assumed as this run)

These are the last committed official cards. This campaign re-measures into `artifacts/qa/official_*`.

- Dev `artifacts/dev/t04.md`: residual-zero 159/239, unique 0, ambiguous 236, none 3, budget 0, search 239/239, auto-clear 0, false clears 0
- Test `artifacts/test/t04.md`: residual-zero 521/800, unique 0, ambiguous 779, none 21, budget 0, search 800/800, auto-clear 0, false clears 0
- pytest last known green before this file: 507 passed in 75.38s (`artifacts/qa/baseline_pytest.txt`)
