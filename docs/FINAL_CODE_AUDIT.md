# Final code audit

Component map produced during the final hardening phase. Every row was read, not inferred.

"Financial authority" means the component may decide a reconciliation outcome. Exactly one
subsystem has it.

## Deterministic engine — the only financial authority

| Component | Location | Responsibility | Write access | Financial authority | Tests |
|---|---|---|---|---|---|
| Normalisation / ingest | `src/residual_zero/ingest/` | Parse bank, ledger, settlement into integer paise | none (reads CSV) | No | `tests/test_razorpay_adapter.py`, `tests/test_ingest*.py` |
| Candidate generation | `src/residual_zero/candidates.py` | Build the candidate pool and sub-windows | none | No | `tests/test_candidates.py` |
| Safe prune | `src/residual_zero/solver/prune.py` | Drop candidates that cannot appear in any in-window subset | none | No | `tests/test_solver_properties.py` |
| Signed subset-sum | `src/residual_zero/solver/bitset_dp.py` | Bitset DP over the shifted rupee axis | none | No | `tests/test_solver_properties.py`, `tests/invariants/test_solver_invariants.py` |
| Enumeration / uniqueness | `src/residual_zero/solver/enumerate.py` | `solve_search`; decides UNIQUE / AMBIGUOUS / NONE_FOUND / BUDGET_EXCEEDED | none | **Yes** | `tests/invariants/test_solver_invariants.py` |
| Declared fast path | `src/residual_zero/solver/fastpath.py` | `verify_declared` on posted lines | none | **Yes** | `tests/test_solver_properties.py` |
| Verification | `src/residual_zero/verify.py` | Residual + derived-line check; **only writer of `reconciliation`** | `reconciliation`, `decomposition_member` | **Yes** | `tests/test_conservation.py`, `tests/test_least_privilege.py` |
| Disposition | `src/residual_zero/orchestrator.py` | Six-conjunct `can_clear` gate → CLEARED / FLAGGED / BUDGET_EXCEEDED | via `write_cleared`, gated on `pol.allow_writes` | **Yes** | `tests/invariants/test_financial_state_machine.py` |
| Money | `src/residual_zero/money.py` | Integer paise, half-up rounding, bps, Indian formatting | none | **Yes** | `tests/test_money.py`, `tests/invariants/test_money_invariants.py` |
| Exceptions | `src/residual_zero/exceptions/` | Closed 11-class assignment, by rule | `exception` | No | `tests/test_exceptions.py` |
| Audit chain | `src/residual_zero/audit.py` | Hash-chained `audit_entry` | `audit_entry` | No | `tests/test_audit*.py` |

### Risks noted

- `TABLE_OWNERS` is a convention, not a SQLite-enforced restriction: an owner connection is
  a plain read-write handle and could in principle touch another owner's table. In practice
  each owner module issues only fixed SQL for its own tables, and
  `tests/test_least_privilege.py` pins the three importers of `_open_readwrite`.
- A sub-rupee ledger item rounds to 0 on the rupee search axis. `enumerate.py` deliberately
  refuses the whole pool in that case rather than searching with an invisible member. There
  are 8 such rows in the dev corpus. Documented and pinned by
  `test_a_zero_rupee_record_makes_the_search_refuse_rather_than_search`.

## AI layer — investigation only, no authority

| Component | Location | Responsibility | Write access | Financial authority | Tests |
|---|---|---|---|---|---|
| Intent | `src/residual_zero/qa/finance_intents.py` | Classify the question, including REFUSE_CLEAR | none | No | `tests/invariants/test_ai_authority.py` |
| Planner / loop | `src/residual_zero/qa/agent_loop.py` | Playbook then optional model next-tool; MAX_TOOLS 8, MAX_REPEAT 2, 30s | none | No | `tests/test_agent_loop.py`, `tests/invariants/test_ai_authority.py` |
| Tool dispatch | `src/residual_zero/qa/finance_tools.py` | 43 read-only tools, fail-closed on unknown names | none | No | `tests/invariants/test_ai_authority.py` |
| Controller | `src/residual_zero/qa/finance_controller.py` | Aggregate evidence, template the answer, validate claims | none | No | `tests/test_finance_controller.py` |
| Claim validation | `src/residual_zero/qa/finance_validate.py`, `evidence_validate.py` | Reject unsupported financial claims | none | No | `tests/test_hardening_safety.py` |
| Extraction | `src/residual_zero/qa/evidence_extract.py` | Candidate-only reference extraction; append-only cache | appends `extract_cache.jsonl` | No | `tests/test_evidence_discovery.py` |
| AI audit | `src/residual_zero/qa/finance_audit.py` | Append-only run log; strips `api_key` | appends `ai_audit.jsonl` | No | `tests/test_hardening_safety.py` |
| Provider client (NVIDIA NIM) | `src/residual_zero/semantic/provider.py` | Optional explanation rewrite / next-tool pick | none | No | `tests/test_provider.py` |
| Corpus / desk prose | `src/residual_zero/qa/corpus.py`, `desk_tools.py` | Narrate committed official cards | none | No | `tests/invariants/test_release_regressions.py` |

The model-reachable layer contains no SQL writes, no `subprocess`/`eval`/`exec`, and no
reference to `write_cleared`, `open_verify` or `_open_readwrite`. Verified by
`scripts/qa_write_path_audit.py` and pinned by `tests/invariants/test_ai_authority.py`.

## Console, API, MCP

| Component | Location | Responsibility | Write access | Financial authority | Tests |
|---|---|---|---|---|---|
| Console app | `src/residual_zero/console/app.py` | Pages; DB handle is `open_readonly` (`mode=ro` + `query_only`) | `exception_resolution`, `exception_work` via `open_exceptions` | No | `tests/test_console.py` |
| Clear gate (display) | `src/residual_zero/console/clear_gate.py` | Explains refusal; `overlay_writes_cleared` is hard-false | none | No | `tests/invariants/test_financial_state_machine.py` |
| Official cards | `src/residual_zero/console/facts.py` | Parse committed `artifacts/{split}/t04.md`; degrade to `—` | none | No | `tests/test_facts.py`, `tests/invariants/test_release_regressions.py` |
| Extended API | `src/residual_zero/console/ext_api.py` | `/api/ask`, `/api/finance/tool`, `/api/mcp/tool`, `/mcp` | none | No | `tests/test_api_contracts.py` |
| Proof explorer | `src/residual_zero/console/proof_explorer.py` | Solution A/B comparison | none | No | `tests/test_proof_explorer.py` |
| MCP registry | `src/residual_zero/mcp/registry.py` | 13 tools; 8 declared refused names raise | none | No | `tests/test_mcp_protocol.py` |
| Human review | `POST /exceptions/{id}/resolve`, `/work` | Records a human decision as its own event | `exception_resolution`, `exception_work` | No | `tests/test_ops.py`, `tests/test_state_transitions.py` |

Eight non-GET routes exist. Two write, and only to human-decision tables. Neither can reach
`reconciliation`.

## Evaluation and tooling

| Component | Location | Responsibility | Notes |
|---|---|---|---|
| Eval harness | `eval/` | Arms A0–A3, metrics, dispositions | Official Test budget exhausted; not rerun |
| Generator | `generator/` | Synthetic corpora from profiles | Session-scoped fixture in `tests/conftest.py` |
| QA scripts | `scripts/qa_*.py`, `scripts/release_certify.py` | Audits and certification, all writing to `artifacts/qa/` | Every value measured |
| CI | `.github/workflows/ci.yml` → `make test` | Runs `pytest -q` | See defect below |

### Defect found and fixed in this phase

`tests/e2e/conftest.py::pytest_collection_modifyitems` is handed **every** item in the
session, not just the ones under its own directory. It applied the browser skip marker to
all of them, so bare `pytest -q` reported `598 skipped` and exit 0. `make test` — the CI
entrypoint — therefore passed while executing nothing. The hook is now scoped by marker and
path. Bare `pytest -q` runs 971 tests; `RZ_E2E=1 pytest -q` runs 983.

## Feature flags and configuration

| File | Purpose |
|---|---|
| `config/solver.yaml` | Epsilon, pool caps, axis width, thresholds |
| `config/features.yaml` | Feature flags, including `FeatureFlags.all_off()` for the CI floor |
| `config/llm.yaml` | Model id; `stub` for evaluation so scoring never depends on a provider |
| `config/tax_rates.yaml`, `config/fees.yaml` | GST, withholding, fee schedules |
| `config/profiles/*.yaml` | Corpus generation profiles |
| `.env` | Local credentials only; gitignored. `.env.example` ships empty placeholders |
