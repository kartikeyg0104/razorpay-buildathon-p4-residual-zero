# Latency (F57)

- machine: Darwin 25.5.0 (arm64)
- n_credits: 248
- wall_ns: 62598650209
- bottleneck: dp

| stage | n | p50_ns | p95_ns | p99_ns |
|---|---:|---:|---:|---:|
| dp | 248 | 8424041 | 15399291 | 19112042 |
| ingest | 1 | 115488167 | 115488167 | 115488167 |
| verify | 248 | 103625 | 201792 | 3215709 |

- throughput_credits_per_1000s: 3961
- projected_5000_credit_wall_ns_if_linear: 1262069560665
- 5000-credit point is a linear projection from this n, not a separate corpus.
