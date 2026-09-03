# UI/UX audit

Every number below was measured in headless Chromium at 1440×900 against the running
console, not estimated. Probe: page height, word count, DOM element counts, heading order,
repeated-sentence detection, and an overflow sweep at 1024/1280/1440.

Priority codes: **P0** absolutely primary · **P1** important · **P2** secondary ·
**P3** technical/detail.

## Measured baseline

| Page | Height | Words | Tables | Rows | Cards | `<details>` | Overflow |
|---|---:|---:|---:|---:|---:|---:|---|
| `/exceptions` | **14,738 px** | 2,139 | 0 | 0 | **119** | 1 | none |
| `/credit/{id}` | **8,285 px** | 1,725 | 2 | 32 | **31** | 1 | none |
| `/close` | 6,349 px | 1,124 | 6 | 80 | 17 | 1 | none |
| `/clusters` | 6,283 px | 509 | 0 | 0 | 36 | 1 | none |
| `/credit/{twins}` | 5,147 px | 906 | 1 | 5 | 24 | 1 | none |
| `/` (batch) | 3,057 px | **2,510** | 1 | 248 | 18 | 1 | none |
| `/demo` | 2,379 px | 754 | 0 | 0 | 1 | 1 | none |
| `/proof/{id}` | 1,598 px | 360 | 0 | 0 | 4 | 1 | none |
| all others | 900–1,700 px | 189–806 | ≤2 | ≤80 | ≤9 | 1 | none |

A 900 px viewport means `/exceptions` is **16 screens** tall and `/credit/{id}` is **9**.

## The dominant finding: safety-phrase saturation

"Overlay does not write CLEARED" and its variants appear **275 times across 25 pages**.
Every page carries at least 3. The worst offenders:

| Page | Occurrences |
|---|---:|
| `/credit/{id}` | **33** |
| `/credit/{twins}` | 31 |
| `/close` | 22 |
| `/` | 18 |
| `/proof/{id}` | 15 |
| `/demo` | 12 |

Source of the universal floor of 3 — `base.html` global chrome, on *every* page:

1. `.side-foot` — "…Overlay does not write CLEARED. The model never adds, matches, or clears."
2. `.honesty` — the ~400-character evaluation strip, which also contains the phrase
3. `.thesis` — "…Residual-zero is not CLEARED. Gate A is not UNIQUE. Overlay does not write CLEARED."

Then `credit.html` adds 14 more, `batch.html` 4, and the AI answer templates add their own.

This is the central UX problem. The statement is the product's thesis and it is *correct*,
but repeating it 33 times on one page converts it into wallpaper. Banner blindness means the
one place it genuinely decides something — the auto-clear refusal — reads with no more weight
than the footer. **Fewer, louder.**

## Second finding: every page opens with two paragraphs of global boilerplate

`base.html` renders `.honesty` then `.thesis` *before* `{% block body %}`. So every page —
including the operator queue and the demo — begins with a dense monospace evaluation strip
and a thesis paragraph before it says what the page is for. This directly violates
"the user should not need to read 20 paragraphs to understand the page".

The honesty strip is **audit evidence**, not primary content. It should remain on every page
for auditability, but collapsed.

## Third finding: `/exceptions` repeats one line 89 times

`Do not pick Equation SEARCH` appears **89 times** — once per exception card across 119
cards. That is the 14,738 px. The operator cannot scan their own work queue.

## Fourth finding: the credit page buries its own headline question

Rendered heading order, with the priority each *should* have:

| # | Heading | Should be |
|---:|---|---|
| 1 | `crd_001_acc_01_2025-01-09` | P0 |
| 2 | H2 "Zero search-clear is correct. Gate A already has the report." | P3 (engineering voice) |
| 3 | FINANCIAL TRUTH | **P0** ✓ correct |
| 4 | AUTO-CLEAR DECISION | **P0** ✓ correct |
| 5 | PROOF EXPLORER · CANDIDATE EQUATIONS | P1 |
| 6 | SOLUTION A · DECLARED | P1 |
| 7 | SOLUTION B · A2_GREEDY | P1 |
| 8 | DECISION BOUNDARY | P1 |
| 9 | SOURCE COMPARISON | P1 |
| 10 | **WHY NOT CLEARED?** | **P0 — currently ~4 screens down** |
| 11 | FOUR-WAY IDENTITY (EVIDENCE, NOT A MATCHER) | P2 |
| 12 | CAUSAL CHAIN | P2 |
| 13 | **WHY THIS DID NOT RECONCILE** | redundant with #10 |
| 14 | IDENTITY | P3 |

Two separate sections answer "why not cleared". The one the user asks first sits tenth.

## Per-page audit

### `/demo` — primary hackathon surface

- **Purpose** prove the thesis in one scripted pass · **User** judge · **Question** "what am I looking at?"
- **Density** 2,379 px, 754 words, 11 headings. Nine numbered H2 steps.
- **P0** the thesis line; the golden path BATCH → AMBIGUITY → PROOF → AI → HUMAN → REFUSE
- **P1** the per-step links · **P2** "what a judge should be able to answer" · **P3** artifact ids
- **Verdict: already good.** Tight, sequenced, correct voice. Only the inherited global
  chrome hurts it. **KEEP**, fix via chrome.

### `/` (batch dashboard)

- **Purpose** state of the batch · **User** operator + judge · **Question** "what is proven, what is not?"
- **Density** 3,057 px but **2,510 words** — the heaviest prose on the product. 248 rows, 18 cards.
- **P0** total, residual-zero, verified, ambiguous, unique, auto-clear, false clears, search coverage
- **P1** the exception table, AI operations insight
- **P2** PROVABILITY WATERFALL, WHY SO MANY REMAIN UNRESOLVED, THESE ARE NOT THE SAME GATE
- **P3** OVERLAPPING METRICS (NOT ADDITIVE), MUTUALLY EXCLUSIVE UNIQUENESS, eval provenance
- The four explanatory sections are genuinely valuable teaching material for a judge, but
  they are prose where the operator wants numbers.
- **CONDENSE + COLLAPSE**: keep KPIs and the table primary; put the didactic blocks behind
  progressive disclosure. **Do not delete** — they answer "why is 1:1 insufficient?".

### `/credit/{id}` — most important operational page

- **Purpose** decide one credit · **User** operator · **Question** "why is this not cleared and what do I do?"
- **Density** 8,285 px, 31 cards, 26 headings, 33 safety phrases.
- **P0** bank amount · residual · uniqueness · verification · Gate A · **why not cleared**
- **P1** proof equation, competing explanations, source comparison, next action
- **P2** four-way identity, causal chain, timeline, audit
- **P3** engineering H2, artifact ids, feature flags
- **REORDER + MERGE + COLLAPSE**: lift WHY NOT CLEARED directly under AUTO-CLEAR DECISION;
  fold the duplicate WHY THIS DID NOT RECONCILE into it; collapse P2 into detail sections;
  cut the phrase from 33 to the decision points.

### `/proof/{id}` — proof explorer

- **Density** 1,598 px, 360 words, 5 headings: SOLUTION A / SOLUTION B / DECISION BOUNDARY.
- Shows common records, only-A, only-B, residuals, distinguishing evidence. No confidence
  score, no "likely winner" anywhere — checked.
- **Verdict: already good. KEEP as-is.** This page is the product's best argument.

### `/exceptions` — operator queue

- **Purpose** work the queue · **User** operator · **Question** "what do I do next?"
- **Density** 14,738 px, 119 cards, one line repeated 89×.
- **P0** the WORK FIRST list, counts (89 need a human / 159 Gate A proven), value at risk
- **P1** per-item class, amount, gate · **P2** per-item narrative · **P3** the repeated caveat
- **CONDENSE**: state the caveat once at section level, not per card.

### `/close` · `/books` · `/journal` · `/clusters` · `/asof` · `/controller` — operator surfaces

- Each answers a distinct close question (exposure, books tie-out, journal export, duplicate
  clusters, aging, leakage). **None is redundant; keep every route.**
- `/close` 6,349 px / 6 tables and `/clusters` 6,283 px / 36 cards are the two heavy ones.
- **CONDENSE** the repeated caveat; otherwise acceptable for their audience.

### `/ask` — AI controller

- **Density** 1,040 px, 389 words, 3 cards. Already separates deterministic result from AI
  explanation and shows next-best-action. Does not resemble a chatbot.
- **Verdict: already good. KEEP.**

### `/evidence` · `/challenge` · `/safety` · `/alts` · `/human` · `/mixed` · `/extension` · `/whatif` · `/recon`

- All 900–1,700 px, single purpose each, low density. **KEEP as-is.**

## Things I checked and am deliberately not changing

- **Navigation.** 23 entries, but `base.html` already groups them (`pitch`, `close`) and
  already hides the 13 advanced surfaces behind `<details class="nav-more">` that auto-opens
  on the active page. My first extraction reported 13 links with empty text — that was the
  probe reading collapsed content, not a defect. Active state is bound per link and correct.
  **No change.**
- **Responsive.** Zero horizontal overflow at 1024, 1280 and 1440 on `/`, `/demo`,
  `/credit/{id}`, `/proof/{id}`, `/ask`. **No change.**
- **`/certificate`.** Reported 0 headings and 12 words. It is a `JSONResponse` endpoint, not
  an HTML page. **Not a defect, no change.**
- **AI answer templates.** `finance_templates.py` carries the phrase 22 times, but there it
  is the assistant stating its own boundary inside a response. Contextually load-bearing.
  **No change.**
- **`clear_gate.py` reason strings.** That is the deterministic refusal explanation, the one
  place the sentence is doing real work. **No change.**
- **Console errors.** None on any page. **No change.**

## Implementation order

1. Global chrome in `base.html` + CSS — collapse the honesty strip, de-duplicate the thesis.
   One edit, improves the first viewport of all 25 pages.
2. `credit.html` — reorder to put WHY NOT CLEARED under the decision, merge the duplicate,
   collapse P2, thin the repetition.
3. `exceptions.html` — hoist the per-card caveat to section level.
4. `batch.html` — collapse the didactic P2/P3 blocks, keep KPIs primary.

Presentation only: templates, CSS, and one presentation helper if unavoidable. No solver,
orchestrator, verification, finance-tool, MCP or audit change.

---

# Implementation record

Measured again after the changes, same probe, same viewport.

## Outcome

| Metric | Before | After |
|---|---:|---:|
| "does not write CLEARED" occurrences, all pages | 275 | **159** (−42%) |
| Pages with **zero** visible safety statement | 0 | **0** (none lost) |
| `<details>` disclosure elements | 24 | **54** |
| `/exceptions` words | 2,139 | **1,190** (−44%) |
| `/exceptions` height | 14,738 px | 12,661 px |
| `/` height | 3,057 px | **2,404 px** (−21%) |
| `/credit/{id}` height | 8,285 px | 7,629 px |
| `/credit/{twins}` height | 5,147 px | 4,626 px |
| Horizontal overflow @1024/1280/1440 | none | none |
| Console errors | none | none |
| `<main>` landmark | absent | **present** |

## Changes implemented

**1. Global chrome — `base.html`, `app.css`** (affects all 25 pages)

- The evaluation strip moved into a collapsed `<details class="provenance">` labelled
  "Evaluation provenance · official cards, overlay counts, thresholds". Still on every page,
  still in the DOM for auditability, no longer the first thing on the page.
- Thesis paragraph reduced from four sentences to `{{ thesis }}` plus one clause. Removes two
  duplicated statements per page.
- `<div class="main">` → `<main class="main">` so the existing skip link targets a real
  landmark. Asset cache key bumped `desk15` → `desk16`.

**2. Dashboard — `batch.html`**

- **Moved the 92 lines of KPI markup above the explanatory prose.** This was the biggest
  single hierarchy defect and my numeric probe missed it — it took a screenshot to see that
  the first viewport contained no numbers at all. The first screen now leads with
  transactions, residual-zero, settlement-linked, search completed, unique, ambiguous,
  unresolved, unreconciled, then the 0 guesses / 159 proven / 89 human verdict.
- "These are not the same gate" and "Provability waterfall" became collapsed `card fold`
  sections. Both kept in full; they answer the judge's "why is 1:1 insufficient" question.

**3. Credit page — `credit.html`**

- `WHY NOT CLEARED?` moved from 10th to 5th, directly under `AUTO-CLEAR DECISION`.
- `decision boundary` and `four-way identity` became collapsed `card fold`; the four-way
  summary now shows its `n/4` count in the summary line so the number survives collapsing.
- Safety phrase reduced 14 → 4 in the template, keeping it where it decides something: the
  auto-clear lede, the UNIQUE branch of the recommendation, the human decision record, and
  the overlay data field.
- `aria-label` added to the queue work `<select>`.

**4. Queue — `exceptions.html`, one presentation context variable in `app.py`**

- Removed the per-card playbook line, which repeated the identical sentence **89 times**.
  Replaced with one collapsed "Playbook by exception class" legend listing only the classes
  actually present. `data-search` still carries the playbook text, so filtering is unchanged.

**5. Redundancy trim** — `proof_panel.html` 2 → 0, `close.html` 2 → 1. Every page still
carries at least one visible statement.

## Deliberately not implemented

- **Navigation.** Already grouped (`pitch`, `close`, `more`) with the 13 advanced surfaces
  behind an auto-opening `<details>`. Active state correct. My first probe reported 13
  unnamed links; that was the probe reading collapsed content. **No defect.**
- **`h1 → h3` heading skips** on six pages. Real but cosmetic. Fixing means renaming `h3` to
  `h2` across ~20 templates with CSS coupled to `h3`. Risk exceeds the benefit at freeze.
- **`/certificate`.** A `JSONResponse`, not a page.
- **`/exceptions` remaining height.** 12,661 px is 119 genuine queue items. A queue lists its
  work; the fix was the repeated prose, not the item count.
- **AI answer templates and `clear_gate` reason strings** (22 and 2 occurrences). There the
  sentence is the assistant or the engine stating its own boundary in a response.
- **`/demo`, `/proof`, `/ask`.** Inspected and already correct: `/demo` is a clean nine-step
  golden path, `/proof` shows A/B with no confidence score, `/ask` already separates the
  deterministic result from the AI explanation. Left alone apart from the inherited chrome.
- No animation, chart, gradient, mascot, confidence score or "AI powered" badge was added.

## Financial preservation

`pytest -q` **971 passed, 12 skipped**. `RZ_E2E=1 pytest -q` **983 passed**, all 12 browser
tests included. Deep checks contamination/agent/dev-regression/cache/MCP all PASS. Write-path
audit PASS, only `verify.py` writes financial tables, CLEARED 0 → 0. Dev 159/239 and Test
521/800 unchanged with unique 0, auto-clear 0, false clears 0. Source CSV/YAML and
`artifacts/test/` byte-identical. Solver, orchestrator, verification, finance tools, MCP
permissions and audit semantics untouched.

The single backend edit is a template context variable in the `/exceptions` route that passes
the class→playbook pairs already present in the queue, so the legend can render once instead
of 89 times. No financial value passes through it.
