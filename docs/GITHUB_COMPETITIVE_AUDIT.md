# GitHub competitive audit

Residual Zero / Razorpay Track 04 AI Finance Controller. Audit date: 2026-09-01.

This document records what was inspected in-repo and what was studied in public GitHub projects. It is **not** a claim that Residual Zero is universally superior. Competitive ideas were adopted only when they preserve:

- FALSE CLEARS = 0
- FABRICATED MATCHES = 0
- LLM FINANCIAL DECISIONS = 0
- LLM AUTO-CLEAR = 0
- uniqueness threshold 1.000000
- overlay never writes `CLEARED`

## 1. Repository inventory (inspected)

| Area | Location |
|---|---|
| Reconciliation engine / signed subset-sum | `src/residual_zero/solver/` (`bitset_dp.py`, `enumerate.py`, `solve_search`) |
| Candidate generation | `src/residual_zero/candidates.py` |
| Uniqueness / verification | `src/residual_zero/solver/disambiguate.py`, `verify_declared` |
| Settlement recon | ingest + overlay `src/residual_zero/console/ops.py` |
| Overlay | never writes `CLEARED` |
| AI controller | `src/residual_zero/qa/finance_controller.py`, `agent_loop.py` |
| NVIDIA NIM | `src/residual_zero/semantic/provider.py` (Ask only; eval LLM stays stub) |
| Finance tools | `src/residual_zero/qa/finance_tools.py` (allowlisted, read-only) |
| Evidence graph | `src/residual_zero/qa/evidence_ops.py` + `proof_explorer.graph_edges_v2` |
| Extraction | `src/residual_zero/qa/evidence_extract.py` |
| MCP | `src/residual_zero/mcp/`, console `/mcp` |
| HTTP / console | `src/residual_zero/console/app.py`, `extra.py`, `ext_api.py` |
| Explorer / close pack | `/explorer`, `/close` |
| Audit trail | SQLite `audit_entry` + `src/residual_zero/qa/finance_audit.py` |
| Caching | `artifacts/console/extract_cache.jsonl` keyed by dataset/question hashes |
| Official Dev / Test eval | `python -m eval.cli`; cards `artifacts/dev/t04.md`, `artifacts/test/t04.md` |
| Ground truth | eval harness; `src/` must not open `truth.jsonl` |
| Feature flags | `config/` YAML; eval LLM stub |
| Performance | `artifacts/dev/latency.md`, QA reports |

## 2. Projects studied

### europeanplaice/subset_sum (`dpss`)

Sparse hash-set DP, many-to-many matching, tolerance, Python/Rust, MCP tools `find_subset` / `reconcile_transactions`. Useful idea: keep solving **inside** a deterministic library and expose thin MCP. **Rejected as a production replacement** — Residual Zero already has a signed, uniqueness-gated, budgeted solver on integer paise. An independent brute-force check is used only in `scripts/benchmark_solvers.py`.

### sebastienrousseau/reconcile-mcp

ISO 20022 pain.001 vs camt.053. Tools: `reconcile`, `explain_match`, 1:N / N:1 with scores. Useful idea: **explain_match** as a structured contract. Residual Zero analogue is Proof Explorer + `explain_candidate_rejection` without using match scores as financial truth.

### razorpay/razorpay-mcp-server

Settlement identifiers and read-only vs write tools. Residual Zero already refuses payment mutations. MCP recon hits remain **not clears**.

### juspay/hyperswitch

PSP → bank N:1 settlement, exception handling. Residual Zero already models declared settlement stacks vs bank credits. No architecture replacement.

### opensyndicate/reconcile

Deterministic ID/amount/date matcher plus optional LLM `propose_match` for leftovers. **Rejected:** fuzzy / LLM-proposed matches as financial truth. **Adopted pattern:** agent tool loop that cannot mutate matcher output.

### himanisharrma/payops-copilot

Exception queues, missing records, duplicate UTRs, late files. Residual Zero already has explorer chips, duplicate UTR radar, next-best-action. Strengthened labels; did not add an “Approve/Clear” action.

### srikrishna0603/razorpay-buildathon

Typed AI outputs and policy boundaries. Residual Zero already has typed intents, claim validation, and refuse-clear. Strengthened the visible AI / engine / human boundary in UI.

## 3. What this upgrade added vs replaced

Added: Proof Explorer, candidate rejection reasons, source agreement matrix, evidence graph v2 edges, agent investigation trace, exclusive waterfall labelling, solver benchmark, competitive matrix.

Did **not** replace: production `solve_search`, uniqueness, windows, epsilon, overlay write policy, official Test artifacts.

## 4. Safety remainder

AI evidence discovery recovered **zero** additional financial reconciliations on the official Track 04 datasets. That is the intended ceiling when uniqueness is 0 and records are missing or genuinely ambiguous.
