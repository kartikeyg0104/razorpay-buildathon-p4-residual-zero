# F34 deterministic parallelism

- n_credits: 16
- workers: threads (CPython GIL; DP is Python). Byte-identity is the load-bearing claim.

| workers | wall_ns | credits_per_1000s | payload_sha256 |
|---:|---:|---:|---|
| 1 | 183159792 | 87355 | 3b8d8b9cd1af78111dcf3e9b5517003e14fa03044f4f74e6bdf11a796d2984b8 |
| 4 | 182920000 | 87469 | 3b8d8b9cd1af78111dcf3e9b5517003e14fa03044f4f74e6bdf11a796d2984b8 |
| 8 | 286994125 | 55750 | 3b8d8b9cd1af78111dcf3e9b5517003e14fa03044f4f74e6bdf11a796d2984b8 |

- byte_identical_1_4_8: true
