# PLAN-P2.md — Residual Zero, Phase 2

Architect: written 2026-08-28. Read-only for the executor once implementation starts.

Inputs read in full before writing: `CLAUDE.md` (P2-PLAN / P2-EXEC, NN-1 … NN-21),
`PLAN-P1.md` §0 deviations (uniqueness across the window, `ε_R = 7`, generator at
top-level `generator/`, Regime B AMBIGUOUS on the 5-day pool), `PROGRESS.md` (CP0–CP9
VERIFIED, tag `v1-submittable`), `docs/SPEC.md` §6.2 / §9.10 / §11 Phase 2 / §12,
and the live tree: `verify.py`, `db.py`, `orchestrator.py`, `solver/enumerate.py`
(`enumerate_cap: 2`), `exceptions/classify.py`, `semantic/llm.py`, `eval/arms/a3_full.py`.

**How to read this document.** §0 is the part a human should read. §1 is the ladder.
Every checkpoint carries the three §6.2 gate clauses (owed number, config flag,
reviewer question). Estimates sum to **71h** (62h of §6.2 + 9h of F24/F25 carry).

**On numbers.** NN-15. This document contains no result figures. Where a Phase 2
run will produce a number, write `TBD-<what-produces-it>`. Do not copy the spec's
illustrative compression ratio, drift rupees, or invented percentages into the
README, the video, artifacts, or a commit message.

**Phase 1 reality this plan builds against, not the original PLAN-P1 hope.**
Auto-clear coverage on the tagged freeze is zero at threshold `1.000000`. Search
uniqueness under `ε_R = 7` is AMBIGUOUS on the 5-day pool. A3 exacts are Regime A
declared compositions, verified at paise, not auto-cleared. `write_cleared` almost
never fires. F33 must therefore be true on a ledger of mostly unreconciled credits,
not on a sea of CLEARED rows. F31's job is to make arithmetic AMBIGUOUS into
structural UNIQUE or STRUCTURALLY_INFEASIBLE; it does not get to widen the verifier
(NN-12) and it does not get to move the autonomy threshold without an F54 diff.

---

## 0 · Decisions I am least confident about

### 0.1 · Conservation is a batch sweep over credits' value-dates, not an incremental write guard

**The decision.** `src/residual_zero/books.py` reads the sqlite after a run (or any
committed ledger) and checks, per `account_id` and per closed IST calendar period
`[start, end]` inclusive on `BankCredit.value_date`:

```
sum(credit.amount_paise)  =  sum(member.amount_paise of CLEARED decompositions)
                           + sum(credit.amount_paise of credits not CLEARED)
```

and

```
every item_id appears in decomposition_member for at most one CLEARED credit
```

**Period boundary for straddlers.** A ledger item that occurred before `start` or
after `end` is attributed to the **credit it was claimed on**, not to its own
`occurred_at`. Unclaimed items do not appear in the identity at all: they are
neither members of a cleared decomposition nor unreconciled credits. The identity
explains bank credits, not the whole ledger. Publishing unclaimed-item value as a
side number is allowed; stuffing it into the identity is not.

**Batch, not incremental.** `write_cleared` is per-credit. Double-claim is a global
property: credit B can claim an item credit A already claimed. A write-time check
on A cannot see B. `make verify-books` is therefore a sweep. A non-zero
double-claim on the tagged Phase 1 sqlite is an `INCIDENTS.md` entry, a regression,
and genuinely good news.

**Why this could be wrong.** If a future incremental engine (F35, Phase 3) consumes
items, the sweep still has to see the same rows. Keep the check off the write path
so F35 cannot bypass it.

### 0.2 · CP-SAT's variable domain is the DP's enumerated solution set (NN-18)

**The decision.** When `features.f31_disambiguation` is on and the DP returns
`AMBIGUOUS`, `enumerate_solutions` is re-invoked with `cap = features.f31_enumerate_cap`
(default 32, not the Phase 1 uniqueness cap of 2). Each returned index-tuple becomes
one Boolean variable. CP-SAT may set at most one of those variables true. Constraints
**forbid** enumerated solutions that violate structure; they never introduce a
combination the DP did not emit. `AddAllowedAssignments` over the enumerated
bit-vectors is the structural guarantee; `tests/test_disambiguation.py` is the second
line.

If enumeration hits the cap, CP-SAT must **not** declare UNIQUE or INFEASIBLE: more
unenumerated solutions may exist. Leave uniqueness `AMBIGUOUS`.

If enumeration completes (`n_found < cap`) and exactly one enumerated solution
survives, uniqueness becomes `UNIQUE` on structural grounds and the proof gains a
`derived_from="CONSTRAINT:<name>"` line naming the first constraint that eliminated
every other enumerated solution. If zero survive, exception class
`STRUCTURALLY_INFEASIBLE` (additive to the Phase 1 eleven; closed set grows by one).
If two or more survive, still `AMBIGUOUS`.

**Phase 1 `enumerate_cap: 2` stays when the flag is off.** Collecting 32 solutions
would change node counts and, on budget edges, dispositions. Flag off = identical
SolveResult uniqueness and member_ids to `v1-submittable`.

**Constraints, formally, each reading only `LedgerItem` fields plus rate config:**

| Constraint | Predicate on enumerated member set S | Fields |
|---|---|---|
| `order_at_most_one_payment` | at most one `PAYMENT` per distinct `order_id` (None ids ignored) | `kind`, `order_id` |
| `refund_needs_parent` | every `REFUND` has `parent_id` in S, or `parent_id` is a `PAYMENT` settled on an earlier credit already CLEARED | `kind`, `parent_id` |
| `fee_needs_instrument_payment` | every `FEE` shares `instrument` with at least one `PAYMENT` in S (fees are per settlement×instrument, not per payment — Phase 1 reality) | `kind`, `instrument` |
| `gst_equals_fee_rate` | `sum(TAX_GST)` equals `-apply_bps(abs(sum(FEE)), gst.bps)` within 0 paise | `kind`, `amount_paise`; `TaxRates.gst.bps` |
| `reserve_equals_gross` | `sum(RESERVE_HOLD)` equals `-apply_bps(sum(PAYMENT), reserve_bps)` within 0 paise | `kind`, `amount_paise`; profile `reserve_bps` |
| `representment_needs_chargeback` | every `REPRESENTMENT` has `parent_id` in S as a `CHARGEBACK` | `kind`, `parent_id` |

A constraint that does not apply (no FEE in S, no GST line, reserve_bps 0) is vacuously
true. Vacuous truth must not be reported as the tie-breaker.

**Why this could be wrong.** Filtering in pure Python is equivalent for a domain of
size ≤ 32. The plan still requires OR-Tools so the formulation is inspectable and
NN-18 is a model invariant, not a comment.

### 0.3 · Feature flags default ON in `config/features.yaml`; the flags-off test never reads that file

**The decision.** After Gate 2 the product runs with Phase 2 features enabled.
`test_feature_flags_off.py` constructs `FeatureFlags.all_off()` in process and passes
it into `run_split` / `run_a3`. It compares dispositions (`CLEARED` / `FLAGGED` /
`BUDGET_EXCEEDED`) per `bank_credit_id` to `artifacts/v1/dispositions.json`, captured
from the tagged Phase 1 A3/orchestrator map before any Phase 2 flag can fire.

Exception class is allowed to differ only when a flag is on. Dispositions must not.

**Baseline capture is CP2.1 work.** If `artifacts/v1/dispositions.json` is missing,
stop: do not implement F31 against an unfrozen baseline.

### 0.4 · Journal posts unreconciled credits to suspense so bank control ties to all credits

**The decision.** Spec §6.2 F40 says the bank control account ties to the sum of bank
credits for the period with a zero residual. A journal of only CLEARED decompositions
would leave bank control at 0 on this corpus (Phase 1 auto-clear is zero). That would
force a plug or a lie.

Every credit in the period posts `Dr Bank / Cr <contra>`:

- CLEARED: contra accounts follow `config/chart_of_accounts.yaml` from member kinds
  (payments, refunds, fees, tax, reserve, bank charge).
- Not CLEARED: contra is `2300 Unreconciled settlements` (suspense).

Debits equal credits at paise. Bank control equals `sum(credits)`. No rounding line.
This is a file the user imports (spec §1.3). No credentials, no API.

### 0.5 · Class 24 is generated only on an explicit Phase 2 plan; existing `data/dev` is not regenerated

**The decision.** Regenerating the Phase 1 corpus would move every published number.
`phase1_dev_plan()` stays class-24-free. `phase2_drift_plan()` (CP2.7 only) adds
`FEE_RATE_DRIFT`. Detector tests use a fixture corpus. False-positive rate is measured
on the **existing undrifted** `data/dev` before any detection claim.

Classes 25 and 26 do not appear in this plan.

---

## 1 · Checkpoint ladder

Hour column is the spec's. Trip-wire is 1.5×. Protected (NN-21, finish-to-minimum,
no revert): F33, F49, F55, F31, F40, F37, F38, F50. Revertible: F52, F54, F24, F25.

| CP | Feature | h | trip-wire |
|---|---|---:|---:|
| CP2.1 | F33 conservation | 4 | 6 |
| CP2.2 | F49 PII boundary | 7 | 10 |
| CP2.3 | F55 CI | 4 | 6 |
| CP2.4 | F31 CP-SAT disambiguation | 10 | 15 |
| CP2.5 | F40 journal export | 7 | 10 |
| CP2.6 | F37 exception clustering | 8 | 12 |
| CP2.7 | F38 rate drift + class 24 | 8 | 12 |
| CP2.8 | F52 decision trace | 5 | 7 |
| CP2.9 | F50 injection corpus | 5 | 7 |
| CP2.10 | F54 eval-diff | 4 | 6 |
| CP2.11 | F24 adversarial self-test | 4 | 6 |
| CP2.12 | F25 idempotency and crash-resume | 5 | 7 |
| **sum** | | **71** | |

---

### CP2.1 · F33 conservation of money · 4h · trip-wire 6h

**Goal.** A global identity that no per-credit zero residual can fake, plus the
feature-flag surface and the flags-off baseline every later CP must keep green.

**Owns files.**
`src/residual_zero/books.py`, `src/residual_zero/features.py`, `config/features.yaml`,
`tests/test_conservation.py`, `tests/test_feature_flags_off.py`,
`artifacts/v1/dispositions.json`, Makefile `verify-books` target,
`docs/EVALUATION.md` §9.10 F33 row.

**Depends on.** Tag `v1-submittable`.

**Owed number.** From spec §9.10, verbatim: *the period identity itself; items claimed
by >1 decomposition (must be 0); unreconciled value*.

**Config flag.** `features.f33_conservation` (bool, default `true` in yaml). When
false, `verify-books` still runs — conservation is a read-only sweep and cannot
change a disposition. The flags-off test asserts that constructing
`FeatureFlags.all_off()` leaves every credit's disposition identical to
`artifacts/v1/dispositions.json`. F33 does not participate in that map; the test is
born here so CP2.2+ have somewhere to hook.

**Reviewer question.** "You showed me 239 individual zero residuals. How do I know
you did not spend the same refund twice?"

**Signatures.**

```python
# src/residual_zero/features.py
class FeatureFlags(BaseModel):
    f33_conservation: bool = True
    f49_pii: bool = True
    f55_ci: bool = True          # documentary; CI is a workflow, not a runtime branch
    f31_disambiguation: bool = True
    f31_enumerate_cap: int = 32  # used only when f31_disambiguation
    f40_journal: bool = True
    f37_clustering: bool = True
    f38_drift: bool = True
    f52_trace: bool = True
    f50_injection: bool = True   # documentary; corpus is tests
    f54_eval_diff: bool = True   # documentary; make eval-diff
    f24_adversarial: bool = True # documentary
    f25_idempotency: bool = True
    @classmethod
    def all_off(cls) -> "FeatureFlags": ...

def load_features(path: Path = Path("config").joinpath("features.yaml")) -> FeatureFlags: ...

# src/residual_zero/books.py
class ConservationReport(BaseModel):
    period_start: date
    period_end: date
    account_id: str
    credits_paise: int
    cleared_members_paise: int
    unreconciled_credits_paise: int
    double_claimed_item_ids: tuple[str, ...]
    identity_holds: bool

def check_account(conn, credits, ledger, account_id: str, start: date, end: date) -> ConservationReport: ...
def check_books(conn, credits, ledger) -> tuple[ConservationReport, ...]: ...
def format_identity(report: ConservationReport) -> str: ...
```

**SQL for double-claim** (batch sweep, owner `verify` tables, readonly connection):

```sql
SELECT item_id, COUNT(DISTINCT bank_credit_id) AS n
FROM decomposition_member
GROUP BY item_id
HAVING n > 1
```

Restrict to credits whose `reconciliation.disposition = 'CLEARED'` by joining
`reconciliation`. Uncleared credits must not contribute members.

**Definition of done.**

```
make verify-books
python -m pytest -q tests/test_conservation.py tests/test_feature_flags_off.py
```

Must produce: printed identity on the existing Phase 1 `artifacts/dev` ledger (or a
fresh flags-off `run_split` into a temp db — same dispositions); double-claim count
0 or an INCIDENTS.md entry; `artifacts/v1/dispositions.json` committed; §9.10 F33
row populated from that run.

**Notes for the executor.**

1. Run verify-books against Phase 1 output **before** any other feature. Expected
   honest shape: cleared members 0, unreconciled = all credits, identity holds.
2. Capture the baseline by running A3/orchestrator with `FeatureFlags.all_off()`
   on `data/dev` and writing `{credit_id: disposition}`. Do not hand-edit it.
3. `test_feature_flags_off.py` may take tens of seconds. Do not skip it, do not
   slice to N credits, do not hash-and-hope.

---

### CP2.2 · F49 PII boundary · 7h · trip-wire 10h

**Goal.** Nothing matching a PII detector reaches a model provider. Raise, do not warn.

**Owns files.**
`src/residual_zero/semantic/redact.py`, `src/residual_zero/semantic/llm.py` (guard),
`tests/test_pii_boundary.py`, §9.10 F49 row.

**Depends on.** CP2.1.

**Owed number.** From spec §9.10, verbatim: *raw VPAs, card fragments, phone numbers
in the model call log (must be 0); accuracy delta redacted vs raw*.

**Config flag.** `features.f49_pii` (default true). When false, `CachedLLMClient`
does not run the PII guard and `resolve()` sends `counterparty_raw` as Phase 1 did.
Flags-off: dispositions unchanged because the stub never resolves tier 4 on this
corpus (Q2=C); the test still asserts the guard is not invoked.

**Reviewer question.** "Bank narration has VPAs. What actually leaves the box?"

**Signatures.**

```python
# src/residual_zero/semantic/redact.py
class PiiLeakError(RuntimeError): ...

DETECTORS: tuple[tuple[str, re.Pattern], ...]  # (name, compiled)
# vpa:        r"(?i)\b[\w.\-]{2,}@(?:okaxis|okhdfcbank|oksbi|paytm|ybl|upi|ibl|axl|okicici|okyesbank|apl|waaxis)\b"
#             plus a generic [\w.\-]{2,}@[a-z0-9.\-]{2,64} used only after the bank suffix miss,
#             so emails in display names are treated as PII too (that is the point)
# card:       r"\b(?:\d{4}[\s\-*]?){3}\d{1,4}\b" and r"(?i)\b(?:xx+|x{2,})[\s\-]*\d{4}\b"
# phone:      r"(?:\+91[\s\-]?)?[6-9]\d{9}\b"
# acct_tail:  r"(?i)\b(?:a/?c|acct|account|acc)[^\d]{0,8}\d{4,}\b"

class RedactionSession:
    """In-memory, per-run. Never written to disk. Stable substitution within the run."""
    def redact(self, text: str) -> str: ...
    def deredact(self, text: str) -> str: ...

def assert_no_pii(payload: bytes) -> None:
    """Raise PiiLeakError on the first detector hit. Called on the bytes about to leave."""
```

**Enforcement placement.** `CachedLLMClient.resolve_entity` and `.narrate` call
`assert_no_pii` on `canonical_json(request)` **after** redaction, **before**
`assert_no_amounts`, **before** cache lookup and **before** `provider.*`. A future
caller that constructs `CachedLLMClient` cannot skip it without editing this
module. Stub responses are also scanned on the way in to the cache write.

Redact in `semantic/tiers.py` `resolve()` when building `EntityResolutionRequest`,
only if `f49_pii`. Candidate `display_name` is redacted; candidate `id` is `ent_*`
and must not be rewritten (closed-set bind would break). De-redact `reason` only;
`selected_id` is an entity id.

**Accuracy delta.** Run entity-resolution over the residue that would hit tier 4,
once redacted and once raw, on the stub. If both are 0 resolutions (Q2=C), publish
the delta as not estimable and say so. Do not invent a point of accuracy.

**Definition of done.**

```
python -m pytest -q tests/test_pii_boundary.py tests/test_feature_flags_off.py
# then grep the cache: no VPA/card/phone patterns in data/cache and artifacts
```

---

### CP2.3 · F55 continuous integration · 4h · trip-wire 6h

**Goal.** A workflow that fails the build without a live model, and a stated epsilon
on the flags-off exact-decomposition count.

**Owns files.**
`.github/workflows/ci.yml`, `config/ci.yaml` (epsilon only), §9.10 F55 row.

**Depends on.** CP2.1 (verify-books), CP2.2 (no live model).

**Owed number.** From spec §9.10, verbatim: *green build; run history; dev-split
regression epsilon*.

**Config flag.** `features.f55_ci` (default true, documentary). Runtime flags-off
path does not consult it. CI itself invokes tests with `FeatureFlags.all_off()` for
the regression floor, then the default yaml for the rest of pytest.

**Reviewer question.** "Did these numbers exist last Tuesday, or only on freeze day?"

**Workflow.**

```yaml
# .github/workflows/ci.yml
# push + pull_request. Python 3.13. pip install -e ".[dev]".
# No OR-Tools required until CP2.4; add it in the CP2.4 commit.
# Steps: make test; generate data/dev if missing; make verify-audit;
#        make verify-books; python -m eval.cli --split dev --full --out artifacts/ci
#        with features all-off overlay; compare A3 exact count to epsilon.
# Offline: config/llm.yaml already model_id stub / token_budget 0. Do not set API keys.
# reproduce.sh is two full evals — run it. If the runner times out, split to a
# nightly job but do not silently drop it from the documented target list.
```

**Epsilon.** Integer, not a float band: flags-off A3 exact count must equal the
Phase 1 freeze count recorded in `config/ci.yaml` as `dev_exact_floor: "<n>/<n>"`
copied from the tagged README (the count, not a new measurement). Any drop fails
the job. Upward movement with flags off is also a fail: the core moved.

**Definition of done.** Workflow file exists; `make test` is the first step; a
comment in the workflow names the epsilon and the offline policy.

---

### CP2.4 · F31 constraint-based disambiguation · 10h · trip-wire 15h

**Goal.** Arithmetic AMBIGUOUS credits may become UNIQUE or STRUCTURALLY_INFEASIBLE
without ever expressing a subset the DP did not enumerate.

**Owns files.**
`src/residual_zero/solver/disambiguate.py`, `src/residual_zero/solver/enumerate.py`
(additive field on SolveResult), `pyproject.toml` (`ortools`),
`tests/test_disambiguation.py`, ExceptionClass `STRUCTURALLY_INFEASIBLE`,
classify.py signal, §9.10 F31 row.

**Depends on.** CP2.1 flags, CP2.3 (add ortools to CI).

**Owed number.** From spec §9.10, verbatim: *% of `AMBIGUOUS` credits resolved to
unique by structural constraints; auto-clear error on that subset; count proven
structurally infeasible*.

**Config flag.** `features.f31_disambiguation` (default true) and
`features.f31_enumerate_cap` (default 32). When false, `solve_search` uses
`enumerate_cap: 2` from `solver.yaml` and never imports ortools. Flags-off
dispositions stay the v1 map. When true, uniqueness may change from AMBIGUOUS to
UNIQUE; auto-clear still requires score ≥ threshold (`1.000000` on the freeze), so
dispositions may remain FLAGGED. Do not touch the threshold. If a UNIQUE-on-
constraints credit would auto-clear, that is an F54-worthy event: stop and diff.

**Reviewer question.** "You turned an ambiguous pile into one answer. What made the
others illegal, and could CP-SAT have invented a third?"

**Signatures.**

```python
# src/residual_zero/solver/disambiguate.py
class Disambiguation(BaseModel):
    uniqueness: Uniqueness          # UNIQUE | AMBIGUOUS | (infeasible -> keep AMBIGUOUS)
    member_ids: tuple[str, ...]
    constraint_named: str | None    # first constraint that cut the field to one, or None
    structurally_infeasible: bool
    n_enumerated: int
    n_feasible: int
    enumeration_capped: bool        # if True, must not declare UNIQUE or infeasible

def disambiguate(
    pool: CandidatePool,
    enumerated: tuple[tuple[int, ...], ...],  # index tuples from enumerate_solutions
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int,
    cleared_parent_ids: frozenset[str],
) -> Disambiguation: ...
```

`SolveResult` gains `enumerated_indices: tuple[tuple[int, ...], ...] = ()` with
default empty so existing constructors stay valid. Populate only when the flag is on.

CP-SAT: `BoolVar` per enumerated solution; `sum(x) <= 1`; `x[i] == 0` if solution i
fails a predicate; if `enumeration_capped`, skip the solver and return AMBIGUOUS.
Assert every CP-SAT support is a subset of `enumerated` (NN-18 test).

Hand-check three resolved credits before publishing the rate; name the constraint
in the §9.10 note.

**Definition of done.**

```
python -m pytest -q tests/test_disambiguation.py tests/test_feature_flags_off.py tests/test_classify.py
```

---

### CP2.5 · F40 double-entry journal export · 7h · trip-wire 10h

**Goal.** A file a CA can import. Debits equal credits at paise. Bank control ties
to the period's credits. No plug.

**Owns files.**
`src/residual_zero/journal.py`, `config/chart_of_accounts.yaml`,
`tests/test_journal.py`, §9.10 F40 row.

**Depends on.** CP2.1 (same period/account scoping).

**Owed number.** From spec §9.10, verbatim: *debits = credits (exact); control-account
tie-out residual (0); entries per cleared credit*.

**Config flag.** `features.f40_journal` (default true). When false, `run_split` does
not write `journal.csv`. Flags-off: no journal, dispositions unchanged.

**Reviewer question.** "Does this post, or does it just match?"

**Chart (codes are labels, not a claim about Tally's built-in numbering):**

```yaml
# config/chart_of_accounts.yaml
bank_control: {code: "1100", name: "Bank"}
unreconciled: {code: "2300", name: "Unreconciled settlements"}
kind_map:
  PAYMENT:           {credit: {code: "4100", name: "Settled payments"}}
  REFUND:            {debit:  {code: "5100", name: "Refunds"}}
  CHARGEBACK:        {debit:  {code: "5200", name: "Chargebacks"}}
  REPRESENTMENT:     {credit: {code: "4100", name: "Settled payments"}}
  FEE:               {debit:  {code: "6100", name: "Platform fees"}}
  TAX_GST:           {debit:  {code: "6200", name: "GST on fees"}}
  TAX_WITHHOLDING:   {debit:  {code: "2100", name: "Withholding payable"}}
  RESERVE_HOLD:      {debit:  {code: "1400", name: "Reserve receivable"}}
  RESERVE_RELEASE:   {credit: {code: "1400", name: "Reserve receivable"}}
  ADJUSTMENT:        {debit:  {code: "7100", name: "Adjustments"}}  # sign-dependent: see journal.py
  BANK_CHARGE:       {debit:  {code: "6300", name: "Bank charges"}}
```

`ADJUSTMENT` uses debit if amount < 0, credit if amount > 0, always to 7100.
Each journal line: `date, account_code, account_name, debit_paise, credit_paise,
narration, reference`. Exactly one of debit/credit is non-zero per line. Date is
the credit's `value_date`. Reference is `bank_credit_id`.

**Definition of done.**

```
python -m pytest -q tests/test_journal.py tests/test_feature_flags_off.py
```

Debits minus credits is the integer 0. Control residual is the integer 0. If they
do not balance, fix the mapping; do not add a rounding line.

---

### CP2.6 · F37 root-cause clustering · 8h · trip-wire 12h

**Goal.** Deterministic signatures. One model call per cluster. Cause labels eval-only.

**Owns files.**
`src/residual_zero/cluster.py`, `eval/cluster_eval.py` (purity; may import
`eval/truth_loader.py`), `tests/test_cluster.py`, §9.10 F37 row.

**Depends on.** CP2.2 (cluster model call goes through the PII guard).

**Owed number.** From spec §9.10, verbatim: *exception compression ratio; cluster
purity against true cause labels*. Plan-time placeholders: `TBD-F37-run`.

**Config flag.** `features.f37_clustering` (default true). When false, the console
lists exceptions ungrouped and no cluster model call is made. Flags-off:
dispositions unchanged (clustering is post-disposition).

**Reviewer question.** "Is this nine problems or two hundred?"

**Signature fields, in order, joined by `|`:**

1. `exception_class`
2. `delta_sign` in `{neg, zero, pos, none}`
3. `delta_bps_bucket`: `abs(delta_paise)*10000 // max(gross, 1)` then
   `0 | 1-10 | 11-50 | 51-100 | 101-500 | 501+`
4. `instrument` of the first PAYMENT in the pool, else `none` (lexicographically
   first item id to break ties)
5. `missing_kind`: kind of the unique `delta_matches_pool_member_ids` item if
   that tuple has length 1, else `none`
6. `iso_week` of `credit.value_date` (`YYYY-Www`)

Tie-break for cluster ordering: signature string, then min credit id. Prefer more
clusters: do not merge adjacent buckets.

**Leakage guard.** `cluster.py` lives under `src/` and must not import
`eval.truth_loader` or open `truth.jsonl`. Purity is `eval/cluster_eval.py` only.
`test_no_leakage.py` gains an assertion that `cluster.py` does not mention
`cause_labels` or `truth.jsonl`.

One `NarrationRequest` per cluster; facts are qualitative; amounts stay in slots
substituted after return (existing narrate path). Model never assigns a class.

**Definition of done.**

```
python -m pytest -q tests/test_cluster.py tests/test_feature_flags_off.py tests/test_no_leakage.py
```

Compression ratio is exceptions/clusters from a real flags-on exception set, not
an invented illustration.

---

### CP2.7 · F38 effective-rate regression and class 24 · 8h · trip-wire 12h

**Goal.** Alert only when the contracted rate lies outside a fitted interval and
`n` meets a floor. Add `FEE_RATE_DRIFT` here and only here.

**Owns files.**
`src/residual_zero/rates.py`, `generator/corrupt.py` (class 24),
`tests/test_rates.py`, `tests/test_generator.py` (forbidden-class assertion
narrows to 25–26), §9.10 F38 row.

**Depends on.** CP2.1. Does **not** depend on auto-clear: triples can be taken from
Regime A declared compositions that verified at paise, even when disposition is
FLAGGED, because those member sets are known correct against the charged fee.
State that in EVALUATION.md. Using only CLEARED rows would give n=0 on this corpus
and a vacuous detector.

**Owed number.** From spec §9.10, verbatim: *detection latency in windows;
false-positive rate on undrifted profiles; rupee estimation error*. Placeholders
in this plan: `TBD-F38-run`.

**Config flag.** `features.f38_drift` (default true). When false, `rates.py` is not
consulted and class 24 still must not appear in `phase1_dev_plan()`. Flags-off:
dispositions unchanged.

**Reviewer question.** "The books balance. Are the fees the contracted fees?"

**Estimator.** Per `(instrument, iso_week)`: `fee_sum_paise` (absolute),
`gross_sum_paise` (PAYMENT members of the verified set). Effective bps =
`round_half_up_div(abs(fee_sum) * 10000, gross_sum)` when gross_sum > 0.

**Significance.** `min_sample` = 8 payments in the instrument-week. Alert iff
`n >= min_sample` and contracted_bps is **outside** `[lo, hi]` where
`lo, hi` are `effective_bps ± max(1, round_half_up_div(2 * 10000, isqrt(n)))`
— integer two-standard-error band under a 1-percentage-point-scale conservative
σ, no float, no sklearn. If that band is too wide to ever alert, say so and
publish the FP rate anyway. Do not switch to a float t-test inside `src/`.

**Class 24.** `CorruptionClass.FEE_RATE_DRIFT = 24`. From a stated `drift_from`
date in the plan, scale rendered FEE amounts for CARD (or configured instrument)
by `new_bps / old_bps` via `apply_bps` inverse: `new = -apply_bps(gross, new_bps)`
replacing the posted fee, truth `member_ids` untouched (NN-7). `FORBIDDEN_PHASE1`
becomes `{25, 26}`. `phase2_drift_plan()` is the only plan that includes 24.
Do not use the spec's invented from/to percentages as literals anywhere.

**FP protocol.** Run the detector on current `data/dev` (no class 24). Alerts must
be 0 or the detector is too noisy — fix before claiming detection on a drifted
fixture.

**Definition of done.**

```
python -m pytest -q tests/test_rates.py tests/test_generator.py tests/test_feature_flags_off.py
```

Class 24 appears in `CorruptionClass`. Classes 25 and 26 do not.

---

### CP2.8 · F52 full decision trace · 5h · trip-wire 7h

**Goal.** Every credit has an ordered gate list that still exists if a stage raises.

**Owns files.**
`src/residual_zero/trace.py`, orchestrator + a3 hooks, console credit template,
`tests/test_trace.py`, §9.10 F52 row.

**Depends on.** CP2.4 (CP-SAT outcome is a gate).

**Owed number.** From spec §9.10, verbatim: *% of credits with a complete trace
terminating in exactly one disposition*.

**Config flag.** `features.f52_trace` (default true). When false, no trace object
is attached to the audit payload. Flags-off: dispositions unchanged (trace is
observability).

**Reviewer question.** "Which gate failed, and can I see it without reading the
source?"

**Schema.**

```python
class Gate(BaseModel):
    name: str
    passed: bool
    detail: str

class DecisionTrace(BaseModel):
    bank_credit_id: str
    gates: tuple[Gate, ...]
    disposition: Disposition | None  # None if still running
    error: str | None                # set if a stage raised
```

Gates, in order: `pool`, `regime`, `declared_verify`, `dp`, `cpsat` (skipped
when flag off, recorded as skipped not failed), `paise_verify`, `ordering`,
`disposition`. A `try/finally` around the credit loop body always appends the
trace to the audit `metrics` dict (metrics are unhashed — timings already live
there — but the gate names are also copied into the hashed payload as
`trace_gates` so an auditor can replay). A raise sets `error`, disposition
FLAGGED if one was not already chosen, and still writes the row.

**Definition of done.**

```
python -m pytest -q tests/test_trace.py tests/test_feature_flags_off.py
```

Include a test that raises mid-credit and still finds a trace terminating in
exactly one disposition.

---

### CP2.9 · F50 prompt-injection corpus · 5h · trip-wire 7h

**Goal.** ~30 planted strings. Zero auto-clears. A written structural argument.

**Owns files.**
`fixtures/injections/corpus.jsonl`, `tests/test_injection.py`,
`docs/EVALUATION.md` F50 argument + §9.10 row.

**Depends on.** CP2.2 (payloads are redacted then PII-scanned; injections that
look like VPAs are still injections).

**Owed number.** From spec §9.10, verbatim: *injections causing an auto-clear
(must be 0 of ~30); disposition of each*.

**Config flag.** `features.f50_injection` (default true, documentary). The corpus
is tests. Flags-off: production `resolve()` path unchanged.

**Reviewer question.** "Narration is attacker-controlled. Why is that not an
authorisation oracle?"

**Corpus categories (build by hand, ~30 rows):** instruction override (5),
forged system / XML-ish wrappers (4), unicode bidi marks (3), base64 blobs (3),
developer-mode / DAN (4), prior-authorisation claims (4), mixed with a real
merchant-like name (4), empty/control-char (3). Each row:
`{id, category, narration, expected_max_disposition}` where expected is FLAGGED
or BUDGET_EXCEEDED, never CLEARED.

**Structural argument (write in EVALUATION.md, not as a hope):** the model
returns an id from a closed candidate set; it never sees or emits an amount
(NN-3); auto-clear requires UNIQUE + zero paise residual + ordering score from
observables. A wrong entity cannot mint a zero residual. That chain is the
deliverable.

**Definition of done.**

```
python -m pytest -q tests/test_injection.py tests/test_feature_flags_off.py
```

If any injection auto-clears: INCIDENTS.md, stop the phase, regression, then
continue.

---

### CP2.10 · F54 disposition diff · 4h · trip-wire 6h

**Goal.** `make eval-diff` plus the rule that no config change ships without a
diff attached in EVALUATION.md.

**Owns files.**
`eval/diff.py`, Makefile `eval-diff`, `tests/test_eval_diff.py`,
`docs/EVALUATION.md` rule + §9.10 F54 row.

**Depends on.** CP2.1 baseline file format.

**Owed number.** From spec §9.10, verbatim: *disposition deltas attached to every
config change in `docs/EVALUATION.md`*.

**Config flag.** `features.f54_eval_diff` (default true, documentary). Flags-off
unaffected.

**Reviewer question.** "What moved when you turned F31 on?"

**Format.** JSON and a markdown table: `credit_id, class, from, to`. Exit 0 even
on non-empty diffs (a diff is information). Exit 1 if either run is missing
dispositions. File diffs at `docs/diffs/YYYYMMDD-<reason>.md` and link them from
EVALUATION.md. First attached diff: flags-off vs flags-on after F31, even if
zero rows.

**Rule text** (paste into EVALUATION.md): no change to `config/solver.yaml`,
`config/features.yaml`, or the autonomy threshold ships without an eval-diff
link in this file.

Do not change the Phase 1 threshold in this checkpoint.

**Definition of done.**

```
make eval-diff RUN_A=artifacts/v1 RUN_B=artifacts/v1
python -m pytest -q tests/test_eval_diff.py tests/test_feature_flags_off.py
```

---

### CP2.11 · F24 adversarial self-test · 4h · trip-wire 6h

**Goal.** Spend the hours trying to make the system auto-clear something wrong.
Publish the search, including a negative result.

**Owns files.**
`artifacts/adversarial/catalogue.md`, `tests/test_adversarial.py` (fixtures that
must not auto-clear), §6.1 owed number (no §9.10 row exists).

**Depends on.** CP2.4 (constraint bugs are in-scope attacks), CP2.9.

**Owed number.** From spec §6.1 F24, not §9.10: *publish what you found —
including anything you could not fix*. PROPOSED measurable companion (labelled
PROPOSED, not a fake §9.10 row): count of attacks attempted; count that produced
an auto-clear of a non-truth member set (must be 0 or INCIDENT).

**Config flag.** `features.f24_adversarial` (documentary). Flags-off unaffected.

**Reviewer question.** "Did you try to break your own uniqueness story?"

**Attack catalogue (attempt all, record each):**

1. Two disjoint payment pairs with equal rupee sums inside `ε_R` (class 23 shape)
   plus a fee line that arithmetically fits both.
2. Near-tolerance: member set residual 1 paise from zero on the rupee axis after
   rounding, inside `ε_R`, truth just outside verifier.
3. Pathological pool: many 1-rupee items, `max_pool` just below n.
4. Deductions that sum to the credit with an extra decoy refund cancelled by a
   decoy representment.
5. Duplicate credit pair, one claimed, one left — can the claimed members be
   reused.
6. Sign-reversed payment that restores the sum.
7. Constraint-model attack: two enumerated solutions, the **wrong** one is the
   only one that satisfies a buggy `fee_needs_instrument_payment` if instrument
   is null — assert we do not UNIQUE it.
8. Injection from F50 that also amounts to a plausible counterparty.

If none auto-clear, the catalogue still ships. That is the likely outcome and it
is still worth reporting.

**Definition of done.**

```
python -m pytest -q tests/test_adversarial.py tests/test_feature_flags_off.py
```

`artifacts/adversarial/catalogue.md` exists with attempted / outcome / fixed-or-not.

---

### CP2.12 · F25 idempotency and crash-resume · 5h · trip-wire 7h

**Goal.** Replay is a no-op. A mid-batch kill resumes without double-counting or
breaking the audit chain.

**Owns files.**
orchestrator skip-if-present path, `tests/test_idempotency.py`,
docs note in EVALUATION.md. No §9.10 row; owed from spec §6.1 F25.

**Depends on.** CP2.1 (conservation after replay), CP2.8 (trace must not duplicate
into a broken chain).

**Owed number.** From spec §6.1 F25: *same batch twice → ledger unchanged, no
duplicate entries*; *kill mid-batch, restart, no double-count, audit chain
verifies*. Those two assertions are the number.

**Config flag.** `features.f25_idempotency` (default true). When false, `run_split`
always appends (Phase 1 behaviour). Flags-off test runs a single pass, so skip-
if-present never fires; dispositions still match v1.

**Reviewer question.** "I kicked the process. Are the books double-posted?"

**Idempotency key.** `(bank_credit_id, config_digest)`. Resume checkpoint: a credit
already present in `audit_entry.payload.bank_credit_id` is skipped. Kill
simulation: `run_split(..., halt_after=k)` raises `CrashSimulated` after k
successful appends; the test catches, calls `run_split` again on the same db,
asserts `verify_chain` ok, `check_books` identity holds, audit seq count equals
the number of credits not the number of attempts.

**Definition of done.**

```
python -m pytest -q tests/test_idempotency.py tests/test_conservation.py tests/test_feature_flags_off.py
```

---

## 2 · Risks from spec §12 and what in this plan mitigates them

| Risk | Mitigation in this plan |
|---|---|
| CP-SAT modelling error (narrows wrongly) | NN-18: domain is enumerated solutions; cap-hit refuses UNIQUE; test_disambiguation strict-subset; three hand-checks before the rate |
| Drift-detector false positives | min_sample 8; contracted rate must fall outside the integer band; FP measured on undrifted `data/dev` before any detection claim |
| Cluster mis-grouping | conservative signature, more clusters, purity vs cause_labels only in eval/, labels unreachable from `cluster.py` |
| Extended-runway drift | flags-off test after every CP; F54 diffs on config change; do not move the Phase 1 threshold |

## 3 · Video (§14) — two swaps and one sentence, no growth

- Evidence segment, swap 1: fee-drift finding (`TBD-F38-run`), fifteen seconds.
- Evidence segment, swap 2: exception compression (`TBD-F37-run`), fifteen seconds.
- Architecture beat: **one sentence** on F33's conservation identity.
- Do not re-record the first screen. Do not add a fourth beat.

## 4 · README below the fold (§15)

The first screen (headline table through Reproduce) does not change. Append:

1. Controller results (journal tie-out, drift, compression) with measured figures only.
2. The §9.10 table, rows F33, F49, F55, F31, F40, F37, F38, F52, F50, F54 populated.
3. Test-split evaluation log — Phase 2 test eval is optional (NN-16, 1 of 4 already
   spent). If nothing could move test behaviour, skip and say so.
4. Safety: PII boundary, injection corpus, degradation ladder **in that order**.
   F51 is Phase 3; the safety section says the ladder is not in this tag rather
   than inventing a rung.

## 5 · Self-check

- [x] Twelve checkpoints, fixed build order, estimates 4+7+4+10+7+8+8+5+5+4+4+5 = 71h.
- [x] Every checkpoint has owed number, config flag, reviewer question.
- [x] Owed numbers sourced: §9.10 for F31–F55 as listed; §6.1 for F24 and F25; no
      invented §9.10 rows.
- [x] F31 domain is the DP enumerated set (NN-18).
- [x] F49 raises (`PiiLeakError`), does not warn-and-send.
- [x] F38 requires min_sample and contracted-outside-band before alert.
- [x] F37 cause labels eval-only; `cluster.py` cannot see `truth.jsonl`.
- [x] Class 24 only at CP2.7. Classes 25 and 26 nowhere.
- [x] `test_feature_flags_off.py` designed at CP2.1.
- [x] No `200:9`, `47,200`, `43`, `2.04`, `1.95` as capability claims in this file
      (grep before handing to the executor). Spec citations that mention those
      illustrations as illustrations are not copied forward.

---

*End of PLAN-P2.md. Implementation starts at CP2.1. Do not skip F33.*
