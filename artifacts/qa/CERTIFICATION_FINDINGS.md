# Release-certification findings

What the certification pass actually found, what was changed, and what was deliberately left
alone. Financial semantics, thresholds, uniqueness, and AI authority were not touched.

## Finding 1 — Playwright suite was not green at the start (RESOLVED)

The state handed to certification claimed "12 Chromium Playwright E2E tests passed". The last
recorded run in `artifacts/qa/release_e2e.txt` was **10 passed, 2 failed**. Both failures were
the two tests that navigate to `/`, which was returning `Internal Server Error`:

- `tests/e2e/test_dashboard.py::test_dashboard_matches_api_t04`
- `tests/e2e/test_smoke.py::test_smoke_pages`

Root cause could not be reconstructed from the run: the E2E conftest sent the console server's
stdout and stderr to `DEVNULL`, so the traceback behind the 500 was discarded, and the server
log had already been deleted. `/` was reproducibly healthy afterwards across a cold start, a
post-unit-suite start, and a post-demo-journey start.

A second, separate problem was masking it: the Playwright Chromium build was missing from the
local cache (`chromium_headless_shell-1234`), so the suite could only error at setup until
`playwright install chromium` was run.

Actions:

- Installed the Chromium build.
- `tests/e2e/conftest.py` now writes the harness-owned console log to
  `artifacts/e2e/console_server.log` instead of discarding it, so a 500 is diagnosable.
- `scripts/release_certify.py` deletes stale browser artifacts before the E2E step, so whatever
  remains in `artifacts/e2e/` belongs to the current run.

Current state: **12/12 pass**. A harness-owned run logged 51 requests, all HTTP 200, zero
tracebacks (`artifacts/qa/e2e_console_server_harness_owned.log`).

The unexplained 500 is recorded as a residual risk: it was real, it is not currently
reproducible, and the diagnostics to catch a recurrence are now in place. No broad
`try/except` was added around `/`, because that would hide the failure rather than surface it.

## Finding 2 — Hardcoded official metrics in the site-wide honesty strip (FIXED)

`src/residual_zero/console/facts.py` embedded official match rates as literals:

- `honesty_line()` printed `residual-zero 159/239` and `residual-zero 521/800`
  **unconditionally**, not as fallbacks. This strip is injected into every page through
  `base.html`, so both headline metrics were hardcoded across the whole console.
- `track04_snapshot()` fell back to `159/239`, `148/239`, `129/239`, `501/800`, `239`, `800`,
  `800/800`, and `1,44,25,758.19` whenever an artifact was missing or unparseable.

Proof: rendering these functions in a working directory with no `artifacts/` at all still
produced `residual-zero 159/239` and `residual-zero 521/800`.

The numbers happened to be correct against the committed cards, so nothing displayed was
wrong. The defect was that a missing or corrupt artifact would silently display
official-looking metrics that had never been computed.

Why the existing guards missed it: `tests/test_console.py::test_batch_template_does_not_hardcode_official_cards`
only inspects `batch.html`, and `hardcoded_metric_scan()` in `scripts/release_certify.py`
classified anything in `facts.py` as `FALLBACK_DEFAULT` by filename.

Fix:

- Both metrics now derive from the committed card via `_residual_zero_cell(split)`, and degrade
  to `—` when the card is absent. No literal remains as a fallback.
- `track04_snapshot()` fallbacks became `—` instead of official-looking values.
- `hardcoded_metric_scan()` gained `fabricated_metric_probe()`, which renders the metric
  surfaces in an empty directory and fails if any official number still appears. Sensitivity
  was verified by reintroducing the defect in a scratch copy: the probe caught it.

Behaviour with real artifacts is byte-identical. The rendered honesty strip before and after
the fix is the same string, and all 586 unit tests plus 12 E2E tests still pass.

## Finding 3 — `AI_BOUNDARY_AUDIT.md` was asserted, not measured (FIXED)

The artifact was a hardcoded string, and it claimed `filesystem | no`. That is not accurate:
the model-reachable layer appends to two observability sinks,
`qa/evidence_extract.py` (extract cache) and `qa/finance_audit.py` (AI audit log). Neither is
financial state, both are append-only, both are suppressed under pytest unless explicitly
opted in, and `record_audit` strips `api_key`.

`write_boundary_md()` now renders from a live `boundary_probe()` that scans the qa layer for
SQL writes, filesystem writes, and shell/eval, probes write-like tool names, and checks every
allowlisted tool for a `writes_cleared` leak. The filesystem row now states the two sinks
precisely instead of claiming none.

## Finding 4 — Terminal block reported Playwright as `passed / passed` (FIXED)

`print_final_block()` printed `{passed} / {passed}`, so a run with failures would still show a
matched pair such as `10 / 10`. The denominator is now the collected suite total, discovered
via `--collect-only` rather than hardcoded, and a mismatch raises a warning.

## Finding 5 — Aggregate "financial regression" was counts only (STRENGTHENED)

The certification compared only `CLEARED` and row count against
`financial_regression_baseline.json`. Section 14 requires exact equality on statuses,
residuals, solution counts, matched IDs, uniqueness, verification, and search status.

`scripts/qa_release_deep_checks.py` now performs that comparison with normalised IDs and
sorted `matched_ids`. Result: **248/248 rows identical across all seven fields**, zero added,
zero missing, `CLEARED = 0`.

## Deliberately not changed

- Auto-clear gates, thresholds, uniqueness, and residual semantics.
- Match rate and solver behaviour.
- `artifacts/test/` — official Test evaluation not rerun, budget exhausted.
- `illegal_clear_transition` remains refuse-all for every actor.
- No `try/except` was wrapped around the `/` handler; loud failure is preferable to a
  dashboard that silently renders partial financial state.
- No tests were added, per the standing instruction; the new checks live in QA tooling.

## Stale artifacts removed

Superseded browser failure traces from earlier runs (`fail_*.png`, `trace_*.zip`,
`console_*.txt` dated 16:05–16:38) were removed from `artifacts/e2e/`. They were browser test
output, not official evaluation evidence, and they described failures that no longer occur.
Their content is summarised in Finding 1 so the record is preserved.
