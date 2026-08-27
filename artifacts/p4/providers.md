# F53 provider swap

- tuning_effort: none (identical on every backend)
- live_models: none (Q2=C; all three backends are StubLLMClient)
- n_credits: 248
- n_items: 5991

| backend | model_id | MODEL | EXACT_NORM | other | tokens | cost_paise | cost_per_credit | e2e_coverage | e2e_error |
|---|---|---:|---:|---:|---:|---:|---|---|---|
| stub-frontier | stub-frontier | 0 | 5991 | 0 | 0 | 0 | 0 | 0/239 | — |
| stub-small | stub-small | 0 | 5991 | 0 | 0 | 0 | 0 | 0/239 | — |
| stub-local-7b | stub-local-7b | 0 | 5991 | 0 | 0 | 0 | 0 | 0/239 | — |

Tier-4 accuracy is not applicable: zero MODEL resolutions on this corpus, on every backend.
End-to-end auto-clear coverage is the published A3 figure (0 at threshold 1.000000 on 239 truth credits);
the table's 0/n_credits column is 'did this stub produce a CLEARED?' and the answer is no.
