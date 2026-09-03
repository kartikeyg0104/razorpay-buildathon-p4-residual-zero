# UI/UX final audit

Measured in headless Chromium at 1440×900 against the running console. Numbers are
measured, not estimated.

## 1. Biggest problems found

**a. Sidebar clicks reloaded the whole document.** Every navigation re-fetched the shell,
re-parsed CSS/JS and lost scroll position. The requested fix, and the largest perceived
change in this pass.

**b. A live model could reword a safety-critical refusal.** This was the serious one, and it
was introduced by moving the provider to NVIDIA NIM. On `/ask` the only place the refusal
appeared was the model-rewritten `answer`. Sampling five live runs of *"Clear this
transaction."*, the exact sentence "cannot authorize a financial clear" was present in some
runs and absent in others. One validated rewrite asserted:

> "The reconciliation engine has found a match for transaction crd_001_acc_01_2025-01-09
> against 27 internal…"

The true state is AMBIGUOUS / REVIEW_REQUIRED with two competing solutions. Claim validation
passed it (`provider_error: ''`). The controller return also has no preserved deterministic
string: `summary` is derived from the rewritten text, so once a rewrite succeeded the engine's
own wording was gone.

**c. Repeated safety copy.** "Overlay does not write CLEARED" appeared 275 times across 25
pages, 33× on the credit page. Repetition had turned the product's central claim into
wallpaper.

**d. Prose before numbers.** The dashboard rendered four explanatory cards before any KPI, so
the first viewport contained no figures.

**e. One line repeated 89 times** on `/exceptions`, once per queue card, producing a
14,738 px page.

## 2. Pages changed

| Page | Change |
|---|---|
| all 25 | evaluation strip collapsed into `Evaluation provenance`; thesis de-duplicated; `<main>` landmark |
| `/` | KPI region moved above the prose; two didactic cards collapsed |
| `/credit/{id}` | `WHY NOT CLEARED?` raised 10th → 5th; `decision boundary` and `four-way identity` collapsed |
| `/exceptions` | per-card playbook replaced with one collapsed class legend |
| `/ask` | new deterministic verdict block above a clearly labelled AI explanation |
| `/proof/{id}`, `/demo` | inspected, already correct, left alone apart from the shared chrome |

## 3. Content removed

- 116 redundant repetitions of the safety sentence (275 → **159**), with **no page** losing a
  visible statement.
- The per-card playbook line on `/exceptions` (89 repetitions of "Do not pick Equation SEARCH").
- Three duplicated thesis sentences from the global chrome.
- `/exceptions` words 2,139 → **1,190**.

Nothing auditable was deleted. Every removal was a repetition or a relocation.

## 4. Content collapsed

`<details>` elements went from **24 → 54**. Collapsed: evaluation provenance (all pages),
"These are not the same gate", "Provability waterfall", "decision boundary", "four-way
identity" (count kept in the summary line), exception playbook legend.

## 5. Content reordered

- **Dashboard:** 92 lines of KPI markup moved above the explanatory cards. The first screen
  now shows transactions, residual-zero, settlement-linked, search completed, unique,
  ambiguous, unresolved, unreconciled, then the 0 guesses / 159 proven / 89 human verdict.
- **Credit page:** the ladder `1 MATHEMATICAL · 2 UNIQUENESS · 3 GATE A · 4 AUTO-CLEAR` and
  `FINANCIAL TRUTH` sit in the first viewport, with `WHY NOT CLEARED?` immediately after the
  decision.
- **`/ask`:** deterministic verdict first, AI commentary second.

## 6. Navigation

Client-side navigation added in `static/app.js`: an internal link swaps `main.main` and
`nav.nav`, updates the title and history, restores scroll, moves focus to the new `h1`, and
re-runs the page bindings. Verified in a browser with a `window` sentinel:

```
6 sidebar clicks: 0 document reloads, sentinel survived, active state correct each hop
back/forward correct · queue filter still works after a swap (89 → 29 rows) · 0 console errors
```

Downloads (`.zip .csv .md .tally .json`), `/api/*`, `/docs`, `/metrics`, external links,
new-tab and modified clicks keep native behaviour. Any fetch or parse problem falls back to a
real navigation rather than a broken view.

**No route was removed and the grouping was left alone.** It already groups `pitch` / `close`
with 13 advanced surfaces behind an auto-opening `<details>`, and the active state is correct.

## 7. Accessibility

- `<div class="main">` → `<main class="main">`, so the existing skip link targets a real
  landmark. Present on every page.
- `aria-label` on the queue-status `<select>`; no unlabelled inputs remain.
- `aria-busy` during a swap and a visible focus ring on the focused heading.
- Focus-visible styles on every new disclosure; `<summary>` keyboard toggle verified.

Not fixed: `h1 → h3` heading skips on six pages. Real but cosmetic, and correcting it means
renaming `h3` across ~20 templates with CSS coupled to `h3`. The 6 "unnamed links" my probe
reported are a probe artifact: they have text but sit inside a collapsed `<details>`.

## 8. Tests

`pytest -q` **971 passed, 12 skipped** · `RZ_E2E=1 pytest -q` **983 passed**.

One genuine regression was caught and fixed. `tests/e2e/test_ask.py::test_clear_request_refuses`
failed because the live model had paraphrased the refusal away. It now passes because the
refusal is rendered from engine fields; sampled five consecutive live runs and the sentence is
present every time.

Deep checks contamination / agent / dev-regression / cache / MCP all **PASS**. Write-path audit
**PASS**, only `verify.py` writes financial tables, CLEARED 0 → 0. No horizontal overflow at
1024, 1280 or 1440. No console errors on any page.

## 9. Financial logic untouched

Files modified in this pass: `static/app.js`, `static/app.css`, `templates/base.html`,
`templates/ask.html`. Presentation only. `solver/`, `verify.py`, `orchestrator.py`,
`finance_tools.py` and `agent_loop.py` were not opened.

Dev **159/239** and Test **521/800** unchanged, with unique 0, auto-clear 0, false clears 0.
Source CSV/YAML and `artifacts/test/` byte-identical. The verdict block reads only fields the
engine already returns (`decision`, `intent`, `recommended_action`); no new backend value was
computed.

## Before → after

**Dashboard.** Thesis + dense metric strip + 4 prose cards, no numbers on screen → one-line
thesis, collapsed provenance, then 8 KPIs and the 3-way verdict. 3,057 → **2,404 px**.

**Credit page.** Provenance strip on top, `WHY NOT CLEARED?` ~4 screens down, safety sentence
33× → gate ladder and financial truth in the first viewport, why-not-cleared 5th, sentence at
the 4 places it decides something. 8,285 → **7,629 px**.

**Proof Explorer.** Already correct: A/B, common, only-A, only-B, residuals, distinguishing
evidence, AMBIGUOUS, and no confidence score anywhere. Only the shared chrome changed.
1,598 → **1,501 px**.

**AI Controller.** A single `ANSWER` block whose wording depended on the model → a
`DETERMINISTIC RESULT` block that a model cannot alter, followed by `AI EXPLANATION` labelled
with the provider and the caveat that the verdict block is the record. 1,040 → **969 px**.

**Exceptions.** 119 cards each repeating the same playbook sentence, 14,738 px → ranked
work-first list, filters, one collapsed class legend. Words 2,139 → **1,190**.

## Still open, needs your decision

The claim validator allowed a live rewrite that asserted a match on a refuse-clear intent.
The presentation layer no longer lets that reach the verdict, but the validator itself sits in
AI-authority code, which this pass was scoped out of. Two options: tighten validation to
reject match/clear assertions on `REFUSE_CLEAR`, or set `AI_PROVIDER=stub` for the demo so
answers stay deterministic. I did not change either.
