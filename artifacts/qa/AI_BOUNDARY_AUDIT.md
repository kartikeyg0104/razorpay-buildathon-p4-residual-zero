# AI boundary audit

Executed by `scripts/release_certify.py` (`boundary_probe`). Values below are measured, not asserted.

Path: user → controller (`finance_ask`) → intent (`classify_finance_intent`) → playbook
(`agent_loop.playbook`) → `call_finance_tool` allowlist → observations → `validate_answer` → response.

Allowlist size: **43** read-only tools. Unknown names return `ok: false`.
MCP `REFUSED_TOOLS` raise. Overlay does not write CLEARED.

| sink | reachable by model? | evidence |
|---|---|---|
| database writes | no | no `INSERT/UPDATE/DELETE/DROP` in `src/residual_zero/qa/`: none found |
| ledger writes | no | same scan |
| settlement writes | no | same scan |
| reconciliation writes | no | `reconciliation` table row count unchanged across the run |
| arbitrary SQL | no | tools are named dispatch only; no query string is taken from the model |
| shell | no | no `subprocess`/`os.system`/`exec`/`eval` in the qa layer: none found |
| filesystem | append-only audit log + extract cache | see below |
| arbitrary HTTP | no | Groq is explanation-only after tools have run |

## Filesystem, stated precisely

The model-reachable layer has no general filesystem access. It appends to exactly two
observability sinks, neither of which is financial state:

- `src/residual_zero/qa/evidence_extract.py:163` — append-only, suppressed under pytest unless explicitly opted in
- `src/residual_zero/qa/finance_audit.py:46` — append-only, suppressed under pytest unless explicitly opted in

Both are append-only. `record_audit` strips `api_key` before writing. Neither can change
status, residual, uniqueness, verification, or matched IDs.

## Write-like probes

Write-like tool names failing closed: **True**
(all rejected).

Tools leaking `writes_cleared: true` or raising: none.

LOCAL_AGENT_HARNESS and LIVE_GROQ are separate states. HTTP 403 is UNAVAILABLE, not PASS.
