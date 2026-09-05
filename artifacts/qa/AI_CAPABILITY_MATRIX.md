# AI capability matrix

> **HISTORICAL SNAPSHOT — not current production state.**
> Captured during the QA campaign dated below, when Groq was still the configured
> provider and was returning HTTP 403. **Groq was removed on 2026-09-03.** The current
> provider is **NVIDIA NIM** (`openai/gpt-oss-20b`), and `AI_PROVIDER=groq` now resolves
> to no endpoint and makes no call. The financial figures in this document are unchanged
> and remain valid; only the provider state is out of date. Current provider
> configuration: `README.md` and `.env.example`.

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
