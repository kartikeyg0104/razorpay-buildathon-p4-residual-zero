# AI capability matrix

Financially authoritative = the deterministic engine only.

| Capability | Local harness | Live Groq | Browser | Financially authoritative |
|---|---|---|---|---|
| Intent detection | actual (pytest) | unavailable unless LIVE_GROQ=AVAILABLE | actual when E2E runs | No |
| Tool selection | actual playbook + allowlist | next-tool only if live | actual investigate button | No |
| Multi-step investigation | actual | unavailable unless live tool loop | actual trace | No |
| Evidence aggregation | actual | same tools | actual | No |
| Source comparison | actual | same tools | actual | No |
| Candidate comparison | actual | same tools | Proof Explorer | No |
| Explanation | fallback templates / live rewrite | UNAVAILABLE | Ask UI | No |
| Human prioritization | actual next_best_action | same | actual | No |
| Financial reconciliation | deterministic | deterministic | deterministic | Yes |
| UNIQUE | deterministic | deterministic | deterministic | Yes |
| CLEARED | deterministic/human policy · never LLM | never LLM | UI policy | Never LLM |
