# Competitive feature matrix

Projects compared (public GitHub, as of 2026-09-01):

1. Residual Zero (this repo)
2. europeanplaice/subset_sum (`dpss`)
3. sebastienrousseau/reconcile-mcp
4. opensyndicate/reconcile
5. razorpay/razorpay-mcp-server
6. juspay/hyperswitch (architecture notes; not a Track 04 solver)

`safe_to_adopt` means “safe to copy as an idea without weakening Residual Zero financial controls.” It is not a license to paste code.

Machine-readable copy: `artifacts/competitive/feature_matrix.json`.

Do not read this table as a leaderboard. Several cells for other projects are **documented capability**, not a side-by-side run on the official 239/800 Track 04 splits.

| feature | Residual Zero | dpss | reconcile-mcp | opensyndicate | razorpay-mcp | hyperswitch | engineering_value | safe_to_adopt | priority |
|---|---|---|---|---|---|---|---|---|---|
| N:M reconciliation | signed subset-sum + declared N:M stacks | yes, many-to-many DP | 1:N and N:1 ISO matches | mostly 1:1 then leftovers | settlement fetch, not N:M proof | N:1 PSP→bank | high | already present | — |
| signed subset-sum | yes, integer paise | amounts; signed via DP | not subset-sum | no | no | no | high | keep ours | — |
| uniqueness | threshold 1.000000, UNIQUE or refuse | not Track 04 uniqueness | scores, not uniqueness | optional LLM propose | n/a | n/a | critical | do not weaken | — |
| residual verification | residual paise == 0 | tolerance matching | short/over deltas | amount_diff | n/a | recon identifiers | critical | keep ours | — |
| evidence graph | v2 edges, LEVEL 0–5 | n/a | explain_match signals | classified gaps | API objects | recon IDs | high | adopted v2 shape | P0 |
| source comparison | BANK×SETTLEMENT×LEDGER matrix | n/a | expected vs observed | settlement vs ledger | settlement payloads | multi-leg | high | adopted matrix | P0 |
| candidate equations | Proof Explorer A/B | multiple subsets | scored pairs | leftover propose | n/a | n/a | high | adopted display | P0 |
| MCP | read-only finance + Razorpay recon tools | find_subset MCP | first-class MCP recon | no MCP | first-class payments MCP | internal | high | keep read-only | — |
| agentic investigation | allowlisted loop, 8 calls / 30s | MCP skill wraps solver | tool recipes | litellm propose_match | agent over live APIs | ops | high | adopted trace | P0 |
| human review | required for AMBIGUOUS | optional | explain_match for humans | leftover list | n/a | exceptions | critical | keep | — |
| auditability | hash chain + AI audit jsonl | n/a | sandbox scenarios | CLI report | API logs | ledger | high | keep | — |
| exception management | explorer + playbooks + NBA | n/a | unmatched residuals | gap kinds | n/a | exception flows | high | labels adopted | P1 |
| settlement APIs | MCP read-only | n/a | ISO files | file loaders | live Razorpay | PSP | medium | no writes | — |
| AI extraction | LEVEL 1, never coverage | n/a | n/a | optional | n/a | n/a | medium | keep LEVEL 1 | — |
| AI explanation | NVIDIA NIM rewrite after tools; claim validation | n/a | explain_match | rewrite explanations | n/a | n/a | high | keep validation | — |
| caching | dataset/question/model hash | n/a | n/a | n/a | n/a | n/a | medium | keep invalidation | — |
| performance | budgeted DP, measured eval wall | sparse DP + Rayon | file-scale | file-scale | network | production | medium | benchmark only | P1 |
| close operations | month-end pack, cash bridge unplugged | n/a | month_end sandbox | n/a | n/a | recon jobs | high | keep | — |
| proof generation | proof block + Proof Explorer | subset lists | scored report | matched pairs | n/a | n/a | high | adopted explorer | P0 |

## Adopted

- Proof Explorer (competing residual-zero explanations, no winner)
- `explain_candidate_rejection` (deterministic reasons only)
- Source agreement matrix (AI may explain, not edit)
- Evidence graph v2 edge contract; LLM edges `verified=false`
- Visible AI / engine / human boundary
- Independent solver benchmark that cannot replace production
- Investigation playbooks with terminals PROVEN / NOT_PROVEN / MISSING_DATA / AMBIGUOUS / CONFLICTING_SOURCES

## Rejected

- Replacing `solve_search` with `dpss`
- Fuzzy or scored matching as financial truth
- LLM `propose_match` / auto-pick of leftovers
- Tolerance widening to raise residual-zero %
- Treating POTENTIALLY_RECOVERABLE as reconciled
- Payment mutation tools from razorpay-mcp-server
- Confidence percentages as evidence
