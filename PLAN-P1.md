# PLAN-P1.md — Residual Zero, Phase 1

Architect: Opus 5. Written 2026-08-27. Read-only for the executor.

Inputs read in full before writing: `CLAUDE.md` (NN-1 … NN-21), `docs/SPEC.md` (all 18
sections; §5, §8, §9, §11 load-bearing), `solver.py`, `test_solver.py`.

**Status of the repo at the time of writing.** Two commits: `7ff66aa` SPEC.md verbatim,
`606923a` CLAUDE.md bootstrap. `docs/SPEC.md` is byte-identical to
`residual-zero-build-spec.md` (sha256 `354bfdb3…`), so CP0's first obligation is already
satisfied and only needs confirming. `solver.py` and `test_solver.py` pass. Empty
directories exist for `artifacts/ config/ data/ src/residual_zero/{generator,solver}
tests/regressions`. No `PROGRESS.md`, no `PLAN-QUESTIONS.md`, no `docs/INCIDENTS.md`, no
`docs/EVALUATION.md`, no `.gitignore`, no `Makefile`, no `pyproject.toml`.

**How to read this document.** §0 is the part a human should read; it is the five places I
had to close a gap the spec left open, ordered by what they cost if I closed one wrongly.
§1 is the ladder the executor works through. §2 is the design record: where the spec
already decided, I restate and cite; where I closed a gap, I say so in the words
"**Gap closed here.**" §3–§6 are the accounting.

**On numbers.** Per NN-15 this document contains no result figures. Every number below is
a design parameter, a bound, a count of things to build, or an hour estimate. Where a
result will exist later I write `TBD-<what-produces-it>`. The spec's own illustrative
tables in §9.3 and §9.8, its quoted solver benchmark in §5.6, and its worked figures in
§5.10, §6.1, §6.2 and §17 are format illustrations from its author's machine and
imagination; not one of them is reproduced here, and none may be copied into `README.md`,
`artifacts/`, a commit message or the video script as though measured.

---

## 0 · Decisions I am least confident about

### 0.1 · Uniqueness under tolerance must be counted across every reachable total in the window, not within one

**The decision.** `solver.py` is correct for the problem it was tested on and subtly wrong
for the problem Phase 1 actually poses. Lines 84–119 compute the set of reachable totals
inside `[target-tol, target+tol]`, then pick exactly one of them —

```python
matched = target if target in hits else min(hits, key=lambda t: abs(t - target))
_backtrack(n, matched, [])
```

— and assess uniqueness *within that single total*. With `tol = 0` that is exactly right,
and `tol = 0` is what `test_matches_brute_force_on_signed_instances` exercises.
`test_tolerance_mode` runs `tol > 0` but only asserts `found == (truth > 0)`; it never
compares uniqueness. So uniqueness-under-tolerance is untested in the reference, and it is
wrong: two distinct subsets that both sum to the true target at **paise** granularity can
land on **different** bits of the rupee axis, because they accumulate different rounding
residues (§2, D6). The solver would enumerate at one of those totals, find one solution,
and report `UNIQUE` for a credit that has two genuine explanations.

That is precisely the failure mode F3 exists to prevent, arriving through the rounding
bridge rather than through the DP. I am confident the analysis is right and less confident
that I have found every instance of the same shape, which is why it is first.

**What I chose.** `UNIQUE` means: across **all** reachable totals `t` with
`|t - r(T)| <= ε_R`, the total number of distinct non-empty subsets summing to any such `t`
is exactly one. Enumeration walks every hit total in a fixed ascending order and
accumulates into one shared solution list with one shared cap of 2.

**What changes downstream if I am wrong.** If this is over-cautious, some credits that are
in truth uniquely explainable are reported `AMBIGUOUS` and we lose coverage. That is the
safe direction. If I had left it alone, the cost is auto-clear error — the one metric §9.2
calls the most important number in the project — and it would not have shown up in any
test the reference ships.

**Cheapest way to find out early.** At CP3, before touching the implementation, extend the
brute-force oracle to count subsets *within tolerance* rather than at one total, and run it
against the unmodified reference. It should fail. That failure is the evidence the change
is needed, and it is the first entry `docs/INCIDENTS.md` is likely to earn.

### 0.2 · The rounding bridge is bounded by the count of sub-rupee members, not the member count — which makes the generator's fee itemisation a correctness decision

**The decision.** D6 works the bridge out properly. The accumulated rupee-axis error is
bounded by `(m+1)/2` where `m` is the number of selected members whose paise amount is
**not** a whole multiple of 100 — whole-rupee members contribute exactly zero. So `ε_R` is
not a function of how many payments a settlement has; it is a function of how many
*computed* lines it has, and that is something the generator decides.

**What I chose.** The Phase 1 profile emits fee and GST **aggregated per (settlement,
instrument)** rather than per payment, and withholding, reserve and bank charge once per
settlement. That caps `m` at `2 × 5 + 3 = 13`, hence `ε_R = 7` rupee units, *derived*
rather than picked. Payments, refunds, chargebacks and adjustments are whole-rupee by
construction in the profile.

**What changes downstream if I am wrong.** If a reviewer expects per-payment fee rows —
which is the shape Razorpay's real settlement report has — then `m` grows with the payment
count, the bound goes to `(n+1)/2`, and `ε_R = 7` stops covering large decompositions.
Those credits fall to `NONE_FOUND`, get diagnosed as `ROUNDING_RESIDUE`, and cost coverage.
They never cause a wrong clear, because NN-12 keeps the verifier at zero paise. So the
blast radius is coverage and a reviewer question, not correctness.

**Cheapest way to find out early.** CP1 prints the distribution of `m` over every generated
credit and asserts `max(m) <= 13` before CP3 fixes `ε`. If the assert fires at CP1, `ε` is
still a free parameter and the itemisation is still a free choice.

### 0.3 · A `UNIQUE` found on a reduced pool is not uniqueness, so it must not auto-clear

**The decision.** §5.5 says that over `MAX_POOL` we "split by sub-window and attempt each,
and if that fails, emit `BUDGET_EXCEEDED`." Taken literally that reintroduces the exact
hazard NN-11 exists to prevent from the other direction: a solution found on a strict
subset of the candidate pool may not be unique over the full pool, because a second
explanation could use the items the split excluded.

**What I chose. Gap closed here.** Every `SolveResult` carries `pool_scope: FULL |
REDUCED`. Auto-clear requires `FULL`. A `UNIQUE` on a `REDUCED` pool is presented as a
`BUDGET_EXCEEDED` exception with the proposed decomposition attached as a suggestion for
the human — honest about what was and was not established.

**What changes downstream if I am wrong.** If over-cap pools turn out to be common in the
Phase 1 profile, this decision costs real coverage and the alternative (clearing on a
reduced pool) buys it back at the cost of the correctness claim. I would not make that
trade, but the size of it should be known rather than assumed.

**Cheapest way to find out early.** CP6 reports the count of `REDUCED` outcomes on dev. If
it is zero or near it, the decision was free and the argument is still worth having in
`docs/DECISIONS.md`.

### 0.4 · A wall-clock time budget and NN-9 determinism are in direct conflict; the operative budget must be deterministic

**The decision.** §5.5 and §12 both want a per-credit time budget. NN-9 and F16 require two
runs of `make eval` to produce byte-identical reports. A wall-clock cutoff decides
dispositions on machine load, so the two requirements cannot both hold if timing gates the
answer.

**What I chose. Gap closed here.** The operative budget is deterministic and computed from
the input alone: `MAX_POOL` on pool size, `MAX_AXIS_WIDTH_RUPEES` on `POS - NEG + 1`, and
`MAX_ENUM_NODES` on backtracking work. All three are pure functions of the instance, so
`BUDGET_EXCEEDED` is reproducible. A wall-clock backstop exists at a much higher setting,
is recorded in the non-hashed metrics channel, and if it ever fires `report.py` refuses to
publish the run and says why. Determinism therefore stays a tested property rather than a
hope, and the backstop stays available as a genuine safety net.

**What changes downstream if I am wrong.** If the deterministic caps are too loose, a
pathological instance burns seconds before hitting one of them and CP3's trip-wire fires.
The response is the one §12 already specifies: stop optimising, ship the budget path.

**Cheapest way to find out early.** CP3 benchmarks on real generated pools on the executor's
own machine and records the machine in `PROGRESS.md`. Axis width from real data is the
number that decides whether the caps are set sanely.

### 0.5 · NN-3 forbids amounts in prompts, so exception narrative and Q&A prose must be written against placeholder slots

**The decision.** NN-3 is absolute: the model never sees an amount, "not in a prompt, not in
a response, not in a log line that a prompt is built from." But §5.10 wants the model to
write the human-facing narrative for an exception, and a useful narrative mentions the
shortfall.

**What I chose. Gap closed here.** The §5.11 structural trick, generalised from Q&A to
narration. The model receives the exception class, the deterministic facts, and a set of
**slot names** — `{DELTA}`, `{GROSS}`, `{PCT}`, `{CREDIT}` — with no values. It returns
prose containing those slots. A deterministic formatter substitutes the rendered figures
afterwards. Any money-shaped literal in the model's output is rejected by the same detector
that guards egress, and the response falls back to a deterministic template. So NN-3 is
literally true of narration, and F9's "a hallucinated number is architecturally impossible"
becomes true of exceptions too, which is a stronger claim than the spec asks for.

**What changes downstream if I am wrong.** If slotted narratives read badly, the fallback is
fully deterministic templates and no model in the narration path at all — which costs a
feature and is defensible in the README on its own terms.

**Cheapest way to find out early.** CP5 generates narratives for ten exceptions across
distinct classes and the executor reads them.

### 0.6 · Sign validation must not reject corruption class 18

Pydantic enforcing "REFUND is negative" would make class 18 `SIGN_REVERSAL` un-ingestible:
the loader would raise on the corrupted view instead of producing the case the system is
supposed to diagnose. **Gap closed here:** sign is a *derived* check, not a model
constraint. `models.py` validates `amount_paise: int` and `!= 0` only, and exposes
`expected_sign(kind)` and `has_expected_sign(item)`. Generator stage 2 asserts
`has_expected_sign` over every truth item; ingest does not, and `normalise.py` computes the
anomaly flag that feeds the classifier. If I am wrong, the symptom appears immediately at
CP1 as an ingest exception on a class-18 fixture.

### 0.7 · `n` is whatever the generator produces from a stated scenario, not a target to be trimmed to

§8.4's "~200" and "~800" are corpus design targets. I have specified a scenario that lands
on them by construction — 40 settlement dates per account per horizon, 2 accounts × 3 seeds
for dev and 4 accounts × 5 seeds for test — rather than generating more and trimming, since
trimming would orphan ledger items and quietly weaken the F33 conservation identity in
Phase 2. The realised counts go in `docs/DATA.md` and the README, and even the spec's own
"800" is a design target rather than a measured n. If CP1's realised counts land far from
the targets, the knob to turn is `orders_per_day` and `accounts`, at CP1, while it is still
cheap.

---
## 1 · Checkpoint ladder

Ten checkpoints mapped one-to-one onto §11 Phase 1 Days 0–9. Estimates are the spec's own:
`8 + 16×8 + 10 = 146h`. F56 adds ~5h that is mostly the raters' time, which is why the
phase reads ~151h; that 5h is not in the ladder, exactly as §11 says.

A checkpoint is done when its definition-of-done command has exited zero in output the
executor showed. Not when the code looks finished.

---

### CP0 · Foundation, config and the definition of success · 8h · trip-wire 12h

**Goal.** Make the repository buildable, put the canonical model and the sourced rate
configuration in place, and write down what counts as success before any logic exists.

**Owns files.**
`pyproject.toml`, `Makefile`, `.gitignore`, `README.md` (stub), `docs/INCIDENTS.md`,
`docs/EVALUATION.md`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md` (stub),
`docs/DATA.md` (stub), `config/tax_rates.yaml`, `config/fees.yaml`, `config/solver.yaml`,
`config/profiles/phase1.yaml`, `src/residual_zero/__init__.py`,
`src/residual_zero/models.py`, `src/residual_zero/money.py`,
`src/residual_zero/tz.py`, `src/residual_zero/config.py`,
`tests/test_models.py`, `tests/test_config.py`, `tests/test_money.py`,
`tests/test_no_floats.py`, `tests/test_plan_arithmetic.py`.

**Depends on.** Nothing.

**Signatures.**

`src/residual_zero/money.py` — the only module permitted to do arithmetic on money.

```python
Paise = int   # type alias, documentary only; every monetary value is a plain int

def round_half_up_div(numerator: int, denominator: int) -> int:
    """Integer division rounding halves toward +inf. The single rounding rule in the system."""

def apply_bps(amount_paise: int, bps: int) -> int:
    """Apply a basis-point rate to a paise amount, rounded by round_half_up_div. No floats."""

def to_rupee_units(amount_paise: int) -> int:
    """Map signed paise onto the rupee-granular search axis: (amount_paise + 50) // 100."""

def is_whole_rupee(amount_paise: int) -> bool:
    """True when amount_paise is an exact multiple of 100, i.e. contributes zero rounding error."""

def format_rupees(amount_paise: int) -> str:
    """Render signed paise as Indian-grouped rupees, e.g. -482150 -> '-4,821.50'. Display only."""
```

`src/residual_zero/tz.py` — the only module permitted to name a timezone.

```python
UTC: ZoneInfo
IST: ZoneInfo

def ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes; convert any tz-aware datetime to UTC. Used by model validators."""

def to_ist_display(value: datetime) -> str:
    """Render a stored-UTC datetime for human display in IST. The only IST conversion point."""

def iso_utc(value: datetime) -> str:
    """Canonical serialisation: ISO 8601, '+00:00' suffix, always 6 microsecond digits."""
```

`src/residual_zero/models.py` — Pydantic v2, `model_config = ConfigDict(frozen=True,
extra="forbid")` on every model.

```python
class Kind(str, Enum):
    PAYMENT = "PAYMENT"; REFUND = "REFUND"; CHARGEBACK = "CHARGEBACK"
    REPRESENTMENT = "REPRESENTMENT"; FEE = "FEE"; TAX_GST = "TAX_GST"
    TAX_WITHHOLDING = "TAX_WITHHOLDING"; RESERVE_HOLD = "RESERVE_HOLD"
    RESERVE_RELEASE = "RESERVE_RELEASE"; ADJUSTMENT = "ADJUSTMENT"
    BANK_CHARGE = "BANK_CHARGE"

class Instrument(str, Enum):
    CARD = "CARD"; UPI = "UPI"; NETBANKING = "NETBANKING"; WALLET = "WALLET"; EMI = "EMI"

class Source(str, Enum):
    SETTLEMENT_REPORT = "SETTLEMENT_REPORT"; INTERNAL_LEDGER = "INTERNAL_LEDGER"
    BANK_STATEMENT = "BANK_STATEMENT"; API = "API"

class Regime(str, Enum):
    A_DECLARED = "A_DECLARED"; B_SEARCHED = "B_SEARCHED"

class Uniqueness(str, Enum):
    UNIQUE = "UNIQUE"; AMBIGUOUS = "AMBIGUOUS"
    NONE_FOUND = "NONE_FOUND"; BUDGET_EXCEEDED = "BUDGET_EXCEEDED"

class PoolScope(str, Enum):
    FULL = "FULL"; REDUCED = "REDUCED"

class Disposition(str, Enum):
    CLEARED = "CLEARED"; FLAGGED = "FLAGGED"; BUDGET_EXCEEDED = "BUDGET_EXCEEDED"

class ExceptionClass(str, Enum):
    AMBIGUOUS_DECOMPOSITION = "AMBIGUOUS_DECOMPOSITION"; MISSING_RECORD = "MISSING_RECORD"
    DUPLICATE_CREDIT = "DUPLICATE_CREDIT"; SUSPECTED_WITHHOLDING = "SUSPECTED_WITHHOLDING"
    UNITEMISED_FEE = "UNITEMISED_FEE"; ROUNDING_RESIDUE = "ROUNDING_RESIDUE"
    CROSS_WINDOW_UNRESOLVED = "CROSS_WINDOW_UNRESOLVED"; SIGN_REVERSAL = "SIGN_REVERSAL"
    ENTITY_UNRESOLVED = "ENTITY_UNRESOLVED"; BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    RATE_MISMATCH = "RATE_MISMATCH"

class ResolutionTier(int, Enum):
    EXACT_NORM = 1; REFERENCE_TOKEN = 2; FUZZY = 3; MODEL = 4; UNRESOLVED = 5

class LedgerItem(BaseModel):
    id: str = Field(min_length=1)
    kind: Kind
    amount_paise: int                    # SIGNED; validator forbids 0; sign is a DERIVED check
    occurred_at: datetime                # tz-aware, coerced to UTC by validator
    account_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    instrument: Instrument | None = None
    order_id: str | None = None
    parent_id: str | None = None         # refund->payment, representment->chargeback
    narration_raw: str
    narration_norm: str
    counterparty_raw: str | None = None
    counterparty_id: str | None = None   # set only by the semantic layer
    source: Source

class BankCredit(BaseModel):
    id: str = Field(min_length=1)
    amount_paise: int = Field(gt=0)
    value_date: date
    account_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    narration_raw: str
    narration_norm: str
    utr: str | None = None

class ProofLine(BaseModel):
    label: str                           # '+ payments', '- GST on fee', ...
    detail: str                          # '(37 items)', 'per config/tax_rates.yaml', ...
    amount_paise: int
    member_ids: tuple[str, ...]
    derived_from: str                    # 'LEDGER' | 'RATE_TABLE:fees.gst' | 'DECLARED'

class ProofRecord(BaseModel):
    bank_credit_id: str
    lines: tuple[ProofLine, ...]
    computed_total_paise: int
    residual_paise: int                  # verifier accepts only 0
    regime: Regime
    uniqueness: Uniqueness
    alternate_count: int
    pool_size: int
    pool_scope: PoolScope
    tier_mix: dict[ResolutionTier, int]
    rate_config_digest: str              # sha256 of the canonicalised config actually used
    audit_entry_hash: str | None = None

class Decomposition(BaseModel):
    bank_credit_id: str
    member_ids: tuple[str, ...]          # sorted; empty unless uniqueness is UNIQUE
    claimed_total_paise: int
    residual_paise: int
    regime: Regime
    uniqueness: Uniqueness
    alternate_count: int
    pool_scope: PoolScope
    ordering_score: float                # observable quantities only; NEVER model confidence
    proof: ProofRecord

def expected_sign(kind: Kind) -> Literal[-1, 0, 1]:
    """+1 inflow, -1 deduction, 0 either (ADJUSTMENT only). Convention made checkable."""

def has_expected_sign(item: LedgerItem) -> bool:
    """Whether the item's sign matches its kind. Asserted over truth; DERIVED on ingest."""
```

`src/residual_zero/config.py`

```python
class RateEntry(BaseModel):
    bps: int                             # integer basis points; sub-bp precision is forbidden
    source_url: str
    as_of: date
    note: str | None = None
    synthetic: bool = False              # True only for private contract terms, never for statute

class UnverifiedRateError(RuntimeError):
    """Raised when a config value is still TBD-VERIFY. Makes NN-8 a mechanism, not a promise."""

class TaxRates(BaseModel):
    gst_on_fee: RateEntry
    withholding: RateEntry

class FeeSchedule(BaseModel):
    per_instrument_bps: dict[Instrument, RateEntry]
    bank_charge_paise: int
    reserve_bps: RateEntry

class SolverConfig(BaseModel): ...       # exact schema in D2
class MerchantProfile(BaseModel): ...    # exact schema in D3

def load_tax_rates(path: Path = Path("config/tax_rates.yaml")) -> TaxRates:
    """Load and validate rates. Raises UnverifiedRateError on any TBD-VERIFY value."""

def load_fees(path: Path = Path("config/fees.yaml")) -> FeeSchedule: ...
def load_solver_config(path: Path = Path("config/solver.yaml")) -> SolverConfig: ...
def config_digest(*models: BaseModel) -> str:
    """sha256 over the canonical JSON of the configs actually used, for the proof record."""
```

Config file schemas: given as annotated YAML in D2. Merchant profile: D3.

**Invariants asserted here.**

- **NN-1** — `tests/test_no_floats.py` walks the AST of every module under
  `src/residual_zero/` and `generator/` and fails on any `float` literal, any `float()` call,
  and any use of `/` (true division) outside `src/residual_zero/money.py` and the two
  allow-listed non-monetary modules (`eval/stats.py`, and the `ordering_score` computation).
  The allow-list is explicit in the test, so adding to it is a visible diff.
- **NN-8** — `tests/test_config.py` asserts every `RateEntry` carries a non-empty
  `source_url` and an `as_of` date, and that `load_tax_rates` raises `UnverifiedRateError`
  when any value is `TBD-VERIFY`. Nothing in the system can run against an unverified rate.
- **NN-15** — `tests/test_plan_arithmetic.py` asserts the three §6.2 identities
  (`39+50+33+23+26 == 171`, `171-5+26 == 192`, `71+69+52 == 192`) and that `README.md`
  contains no `TBD-` marker at tag time (the check is skipped before CP9).
- **NN-19** — `docs/INCIDENTS.md` exists and is committed before any logic module.

**Tests.**

| File · function | Claim, stated so it could be false |
|---|---|
| `tests/test_money.py::test_round_half_up_div_matches_exact_halves` | `round_half_up_div` rounds `.5` toward `+inf` for both signs and never uses float division. |
| `tests/test_money.py::test_to_rupee_units_error_bounded_by_half` | For every `a`, `abs(100*to_rupee_units(a) - a) <= 50`. |
| `tests/test_money.py::test_whole_rupee_amounts_have_zero_rounding_error` | `is_whole_rupee(a)` implies `100*to_rupee_units(a) == a`. |
| `tests/test_money.py::test_apply_bps_is_exact_for_representative_rates` | `apply_bps` agrees with hand-computed integer arithmetic on a fixed table of amounts and rates. |
| `tests/test_models.py::test_amount_zero_rejected` | A `LedgerItem` with `amount_paise=0` fails validation. |
| `tests/test_models.py::test_naive_datetime_rejected` | A naive `occurred_at` fails validation; an IST-aware one is stored as UTC. |
| `tests/test_models.py::test_sign_is_derived_not_enforced` | A `REFUND` with a positive amount **constructs successfully** and `has_expected_sign` returns False. This is what keeps class 18 ingestible. |
| `tests/test_models.py::test_expected_sign_covers_every_kind` | `expected_sign` has a branch for every `Kind` member; adding a kind breaks the test. |
| `tests/test_config.py::test_every_rate_has_source_and_as_of` | No `RateEntry` lacks `source_url` or `as_of`. |
| `tests/test_config.py::test_tbd_verify_raises` | `load_tax_rates` raises `UnverifiedRateError` on a `TBD-VERIFY` fixture. |
| `tests/test_config.py::test_rates_are_integer_bps` | A fractional-bp rate in a fixture fails validation rather than silently truncating. |
| `tests/test_no_floats.py::test_no_float_arithmetic_on_money_paths` | No module outside the allow-list performs float arithmetic. |
| `tests/test_plan_arithmetic.py::test_feature_hour_identities_hold` | The three §6.2 identities hold. |

**Definition of done.**

```
make test && python -c "from residual_zero.config import load_tax_rates, load_fees; load_tax_rates(); load_fees(); print('rates verified')"
```

Must produce: `docs/EVALUATION.md` containing the §9.2 metric definitions **written before
any logic**, `docs/INCIDENTS.md`, `docs/DECISIONS.md` with the four ADRs named in §10
(no agent framework, no LLM arithmetic, no LLM-confidence gating, integer paise), and a
`config/` in which every rate carries a `source_url` and an `as_of`.

**Notes for the executor.**

1. Confirm `docs/SPEC.md` is byte-identical to `residual-zero-build-spec.md` — it already is,
   sha256 `354bfdb33a23eacdcbf20b42533680f08fe4c8d3529db9f1861a010f54c46dc6`. Just verify and
   say so in `PROGRESS.md`; do not re-copy.
2. Write `docs/EVALUATION.md`'s metric definitions **first**, before `models.py`. §11 calls
   this the highest-leverage hour in the project and it is the one ordering in CP0 that
   matters.
3. The rates you must source are a finite list: GST on the platform fee, one withholding
   provision, per-instrument platform fee for the five instruments, the bank charge, and the
   reserve percentage. The last two are private contract terms for a synthetic merchant —
   mark them `synthetic: true` with a note. That is honest; inventing a `source_url` for them
   is not. If you cannot source a **statutory** rate from a primary source (CBDT / GST
   notification / Razorpay's published pricing), leave `TBD-VERIFY` and append to
   `PLAN-QUESTIONS.md`. Do not fill in a plausible number — NN-8, and this panel spots it.
4. `python3` on this machine is 3.14.6. Pin `requires-python = ">=3.11"` and check that every
   dependency actually has a wheel for the interpreter you use; if one does not, create the
   venv on 3.12 or 3.13 rather than fighting it. Record the interpreter in `PROGRESS.md` —
   the CP3 benchmark is meaningless without it.
5. Add every Makefile target now, even as a stub that exits non-zero with "not implemented
   until CPn": `demo eval test verify-audit verify-books reproduce challenge evidence
   eval-diff`. A target named in three documents and absent from the repo is the cheapest way
   to look careless, and `verify-books` / `eval-diff` are named in §7 and §10 even though F33
   and F54 are Phase 2 work.
6. `.gitignore` must exclude `data/` except manifests and seeds, `**/__pycache__`, `.venv`,
   and any `.env`. It must **not** exclude `artifacts/` — that directory is committed on
   purpose (§10).
7. **`solver.py` and `test_solver.py` are currently untracked in this repository** — the two
   existing commits carry only `docs/SPEC.md` and `CLAUDE.md`. Commit them unmodified in CP0,
   before any refactor. CP3's whole approach is to start from the validated reference rather
   than reimplement it, and that is only checkable if the reference is in the history to diff
   against. Also gitignore the stray `__pycache__/` that is sitting beside them.

---

### CP1 · Generator stages 1–2, render, corruption 1–4 and 23 · 16h · trip-wire 24h

**Goal.** Produce a dev split end to end: a scenario, an exact ground-truth answer key the
system cannot reach, three rendered source views, and the five corruption classes that make
the N:M shape and the uniqueness guarantee testable from the start.

**Owns files.**
`generator/__init__.py`, `generator/scenario.py`, `generator/profiles.py`,
`generator/truth.py`, `generator/corrupt.py`, `generator/render.py`, `generator/cli.py`,
`src/residual_zero/ingest/__init__.py`, `src/residual_zero/ingest/source_root.py`,
`src/residual_zero/ingest/csv_bank.py`, `src/residual_zero/ingest/csv_ledger.py`,
`src/residual_zero/ingest/settlement_report.py`, `src/residual_zero/normalise.py`,
`docs/DATA.md`, `tests/test_no_leakage.py`, `tests/test_generator.py`,
`tests/test_normalise.py`, `tests/test_ingest.py`.

**Depends on.** CP0.

**Signatures.**

```python
# generator/scenario.py  — stage 1
class Order(NamedTuple):
    order_id: str; account_id: str; instrument: Instrument
    gross_paise: int; captured_at: datetime; counterparty: str

class Scenario(NamedTuple):
    profile: MerchantProfile; seed: int
    orders: tuple[Order, ...]
    settlement_dates: tuple[date, ...]          # exactly profile.settlement_dates_per_horizon

def build_scenario(profile: MerchantProfile, seed: int) -> Scenario:
    """Deterministically sample orders and settlement dates. Seeded RNG, no global random."""

# generator/truth.py  — stage 2, the answer key
class TruthRecord(BaseModel):
    bank_credit_id: str
    member_ids: tuple[str, ...]                 # the exact composing set, sorted
    total_paise: int
    regime: Regime
    corruption_classes: tuple[int, ...]         # stable class ids applied to this credit
    cause_labels: dict[str, str]                # for F37 purity in Phase 2; eval-only
    subrupee_member_count: int                  # 'm' from D6; asserted <= profile bound

class TruthSet(NamedTuple):
    items: tuple[LedgerItem, ...]
    credits: tuple[BankCredit, ...]
    records: tuple[TruthRecord, ...]

def build_truth(scenario: Scenario, rates: TaxRates, fees: FeeSchedule) -> TruthSet:
    """Compute settlements exactly from the payment stream and rate config. Asserts, per credit:
    signed members sum to the credit at paise; has_expected_sign holds for every item."""

# generator/corrupt.py  — stage 3, rendered views only
class CorruptionClass(int, Enum):
    CLEAN_1_1 = 1; AGGREGATE_N_1 = 2; SPLIT_1_N = 3; MIXED_N_M = 4
    AMOUNT_TRANSPOSE = 5; DATE_SHIFT_TZ = 6; OFF_BY_ONE_DAY = 7
    PARTIAL_PAYMENT = 8; OVERPAYMENT = 9; DUPLICATE_CREDIT = 10
    MISSING_REFUND = 11; NETTED_FEE = 12; WITHHOLDING_GAP = 13
    GST_ON_FEE_OMITTED = 14; ROUNDING_RESIDUE = 15; NARRATION_TRUNCATION = 16
    NARRATION_NOISE = 17; SIGN_REVERSAL = 18; CHARGEBACK_REPRESENTMENT = 19
    PRIOR_PERIOD_ADJUSTMENT = 20; RESERVE_HOLD_RELEASE = 21; BANK_CHARGE = 22
    AMBIGUOUS_BY_CONSTRUCTION = 23
    # 24, 25, 26 are FORBIDDEN in Phase 1: their detectors do not exist yet.

class RenderedViews(NamedTuple):
    bank_rows: tuple[dict[str, str], ...]
    ledger_rows: tuple[dict[str, str], ...]
    settlement_rows: tuple[dict[str, str], ...]   # empty for Regime B credits

def apply_corruptions(views: RenderedViews, truth: TruthSet, plan: CorruptionPlan,
                      rng: Random) -> tuple[RenderedViews, tuple[TruthRecord, ...]]:
    """Mutate rendered views only. Returns updated TruthRecords carrying the applied class
    ids. NN-7: member_ids and total_paise of every record are asserted unchanged."""

# generator/render.py  — stage 4
def render(truth: TruthSet) -> RenderedViews:
    """Emit the three source views, dates in IST, amounts as rupee strings, before corruption."""

def write_split(split: str, views: RenderedViews, records: Sequence[TruthRecord],
                out_root: Path) -> SplitManifest:
    """Write data/{split}/rendered/*.csv and data/{split}/truth.jsonl. Two different roots."""

# src/residual_zero/ingest/source_root.py  — the NN-6 mechanism
class SourceRoot:
    def __init__(self, rendered_dir: Path) -> None:
        """Resolve to an absolute path. This object is the ONLY way the system reads inputs."""
    def open(self, relative_name: str) -> TextIO:
        """Open a file inside the root. Rejects absolute paths, '..', and symlinks escaping it."""
    def list_csv(self) -> tuple[str, ...]:
        """Names of readable CSVs, sorted. There is no API that can name a path above the root."""

# src/residual_zero/normalise.py
def normalise_narration(raw: str) -> str:
    """NFKC, case fold, collapse whitespace, strip punctuation, expand abbreviations,
    strip rail prefixes. Deterministic: the baselines depend on it (§5.4)."""

def extract_reference_token(raw: str) -> str | None:
    """Pull a UTR or reference token into its own field."""

def sign_anomaly(item: LedgerItem) -> bool:
    """Derived class-18 signal: item's sign contradicts expected_sign(kind)."""
```

**Invariants asserted here.**

- **NN-6** — enforced by construction, three ways. (a) `SourceRoot` is the sole input path
  and cannot name anything above `data/{split}/rendered/`; `truth.jsonl` is written to
  `data/{split}/` which is *outside* that root. (b)
  `tests/test_no_leakage.py::test_source_root_cannot_escape` asserts `open("../truth.jsonl")`,
  `open("/etc/passwd")` and a symlink escape all raise. (c)
  `test_no_leakage.py::test_src_never_references_truth` greps every module under
  `src/residual_zero/` for the substrings `truth` and `member_ids` and fails on a hit —
  `generator/` and `eval/` are exempt and that boundary is the whole point.
- **NN-7** — `apply_corruptions` asserts, for every `TruthRecord`, that `member_ids` and
  `total_paise` are byte-identical before and after corruption.
  `tests/test_generator.py::test_corruption_never_mutates_truth` re-asserts it independently
  by hashing `truth.jsonl` across a corrupted and an uncorrupted generation of the same seed.
- **NN-1** — every amount in `truth.py` is produced by `money.apply_bps` /
  `round_half_up_div`; `test_no_floats.py` from CP0 already covers `generator/`.
- **NN-9** — `build_scenario` takes a `Random(seed)` instance; no module-level `random` call
  anywhere in `generator/`. `test_generator.py::test_two_generations_byte_identical` asserts
  it.

**Tests.**

| File · function | Claim |
|---|---|
| `tests/test_no_leakage.py::test_source_root_cannot_escape` | `SourceRoot.open` cannot reach `truth.jsonl` by relative path, absolute path or symlink. |
| `tests/test_no_leakage.py::test_src_never_references_truth` | No module under `src/residual_zero/` mentions truth or member ids. |
| `tests/test_no_leakage.py::test_rendered_views_carry_no_class_labels` | No column in any rendered view correlates 1:1 with an applied corruption class. |
| `tests/test_generator.py::test_truth_sums_exactly_at_paise` | For every credit, the signed sum of its truth members equals the credit amount exactly. |
| `tests/test_generator.py::test_corruption_never_mutates_truth` | `truth.jsonl` is identical with corruption on and off for a fixed seed. |
| `tests/test_generator.py::test_two_generations_byte_identical` | Two runs at one seed produce identical rendered views and truth. |
| `tests/test_generator.py::test_subrupee_member_count_within_design_bound` | Every credit's `m` is `<= profile.subrupee_member_max`. **This is the D6 guard; it must pass at CP1, before CP3 fixes ε.** |
| `tests/test_generator.py::test_class4_is_genuinely_n_to_m` | Every class-4 credit has `>= 2` payments **and** `>= 1` refund, and at least one class-4 order settles across two credits. |
| `tests/test_generator.py::test_class23_two_distinct_subsets_within_tolerance` | For every class-23 credit, two subsets exist whose rupee sums are equal, whose id sets are disjoint in the swapped part, and whose symmetric difference has size `>= 3`. |
| `tests/test_generator.py::test_forbidden_classes_absent` | Class ids 24, 25, 26 appear nowhere in the enum or the corpus. |
| `tests/test_normalise.py::test_normalisation_is_idempotent` | `normalise_narration(normalise_narration(s)) == normalise_narration(s)`. |
| `tests/test_normalise.py::test_truncation_survives_normalisation` | A 35-char truncated name normalises without raising and remains distinguishable from its untruncated form. |
| `tests/test_ingest.py::test_sign_reversed_row_ingests_and_flags` | A class-18 row loads successfully and `sign_anomaly` returns True. This is the CP0 §0.6 decision, verified. |
| `tests/test_ingest.py::test_ingest_is_total_or_raises` | A malformed row produces a typed ingestion error naming the line, never a partial load. |

**Definition of done.**

```
make test && python -m generator.cli --split dev --profile config/profiles/phase1.yaml && python -m generator.cli --print-class 4 --limit 3
```

Must produce `data/dev/rendered/{bank,ledger,settlement}.csv`, `data/dev/truth.jsonl`,
`data/dev/manifest.json`, and `docs/DATA.md` with the realised credit and item counts and an
explicit "assumptions we are least confident about" section (§8.1).

**Notes for the executor.**

1. `--print-class 4 --limit 3` exists for one reason: §12 names the wrong data model as the
   mistake that kills competitors, and CP1 is the first moment insurance is available.
   **Print three class-4 `MIXED_N_M` cases and look at them until the N:M shape is
   undeniable.** Many payments *and* many refunds, spanning more than one credit. If what you
   see is really 1:1 with extra rows, stop and fix the generator now — everything after CP3
   stands on this.
2. Stage order is non-negotiable (§8.2): scenario, then truth, then corruption, then render.
   Inverting truth and corruption destroys the answer key, and it will not announce itself.
3. `m` — the sub-rupee member count — is written into every `TruthRecord` and asserted against
   the profile bound. §0.2 explains why this is a correctness quantity and not a curiosity.
4. Build class 23 in this checkpoint, not later. §8.3 says so twice, and it is the only way
   the uniqueness guarantee is ever provable. The construction procedure is in D4.7 and it is
   precise; follow it rather than improvising an "amounts that happen to collide" heuristic,
   which is how you get a class-23 case that is accidentally unique.
5. Corruption classes 5–22 are CP2 work. Do not start them here even if there is time; CP1
   ends with the dev split generating and the two structural assertions passing.

---
### CP2 · Corruption 5–22, the test-split config, and the first two baselines · 16h · trip-wire 24h

**Goal.** Complete the Phase 1 corruption taxonomy, freeze the test-split configuration
including stacked corruptions and the held-out class, and measure A0 and A1 on dev —
baselines before the arm they are a baseline for, per NN-13.

**Owns files.**
`generator/corrupt.py` (extend), `config/profiles/phase1_test.yaml`,
`eval/__init__.py`, `eval/arms/__init__.py`, `eval/arms/a0_exact.py`,
`eval/arms/a1_fuzzy.py`, `eval/loader.py`, `eval/truth_loader.py`,
`eval/metrics.py` (assignment P/R and exact-decomposition only; the rest at CP6),
`tests/test_corruption_classes.py`, `tests/test_arms_baseline.py`.

**Depends on.** CP0, CP1.

**Signatures.**

```python
# eval/loader.py — the system-side loader, restricted
def load_split(split: str) -> tuple[tuple[LedgerItem, ...], tuple[BankCredit, ...]]:
    """Load rendered views for a split through a SourceRoot. Cannot reach truth.jsonl."""

# eval/truth_loader.py — the eval-side loader, unrestricted, NEVER imported by src/
def load_truth(split: str) -> tuple[TruthRecord, ...]:
    """Read data/{split}/truth.jsonl. Importing this from src/residual_zero/ fails a test."""

# eval/arms/a0_exact.py
class ArmResult(BaseModel):
    arm: str
    predictions: dict[str, tuple[str, ...]]          # credit_id -> predicted member ids
    dispositions: dict[str, Disposition]
    has_exception_path: bool                          # False for A0 and A1 -> dashes, not zeros
    has_budget_path: bool

def run_a0(items: Sequence[LedgerItem], credits: Sequence[BankCredit],
           cfg: SolverConfig) -> ArmResult:
    """Exact single-item amount match inside the base window. Predicts only when exactly one
    item matches; structurally cannot express N:M, which is what makes it informative."""

# eval/arms/a1_fuzzy.py
def build_cost_matrix(items: Sequence[LedgerItem], credits: Sequence[BankCredit],
                      cfg: A1Config) -> tuple[NDArray, tuple[int, ...], tuple[int, ...]]:
    """Cost = w_sim*(1 - normalised similarity) + w_amt*min(1, |delta|/amount_tol);
    ineligible pairs get a large finite sentinel and are filtered after assignment."""

def run_a1(items: Sequence[LedgerItem], credits: Sequence[BankCredit],
           cfg: A1Config) -> ArmResult:
    """Optimal 1:1 assignment via scipy.optimize.linear_sum_assignment, NOT greedy (§9.1)."""

def tune_a1_on_dev(items, credits, truth: Sequence[TruthRecord]) -> tuple[A1Config, TuningLog]:
    """Sweep similarity threshold and amount tolerance; pick the pair maximising A1's OWN
    exact-decomposition rate. The sweep is written to docs/EVALUATION.md."""

# eval/metrics.py (partial at this checkpoint)
def pair_set(predictions: Mapping[str, Sequence[str]]) -> frozenset[tuple[str, str]]:
    """Flatten to (credit_id, item_id) pairs — the unit §9.2 defines precision and recall over."""

def assignment_precision_recall(pred: frozenset, truth: frozenset) -> tuple[Fraction, Fraction]:
    """TP/(TP+FP), TP/(TP+FN) as exact Fractions. No floats in a metric that gets published."""

def exact_decomposition_rate(pred: Mapping[str, Sequence[str]],
                             truth: Mapping[str, Sequence[str]]) -> Fraction:
    """Fraction of credits whose predicted member set equals truth exactly. Unpredicted -> not exact."""
```

**Invariants asserted here.**

- **NN-13** — A0 and A1 exist and are measured on dev before any line of the solver is
  written. The ladder enforces it by ordering; `PROGRESS.md` records their dev figures at CP2,
  which is a timestamp no later reordering can fake.
- **NN-6** — `tests/test_no_leakage.py::test_src_never_imports_truth_loader` (added here)
  asserts no module under `src/residual_zero/` imports `eval.truth_loader`.
- **NN-16** — `config/profiles/phase1_test.yaml` is written and committed at this checkpoint
  and `docs/EVALUATION.md` records the held-out class id **before** the test split is ever
  generated. Choosing a held-out class after seeing results is the failure this ordering
  prevents.
- **NN-7** — the class 5–22 recipes extend `apply_corruptions`, so CP1's truth-immutability
  assertion covers them automatically.

**Tests.**

| File · function | Claim |
|---|---|
| `tests/test_corruption_classes.py::test_every_phase1_class_has_instances` | Classes 1–23 each have at least one instance in dev and at least 25 in test (§8.3). |
| `tests/test_corruption_classes.py::test_held_out_class_absent_from_dev` | The declared held-out class has zero instances in dev and non-zero in test. |
| `tests/test_corruption_classes.py::test_test_split_has_stacked_corruptions` | At least one test credit carries two or three class ids; dev carries at most one per credit. |
| `tests/test_corruption_classes.py::test_range_b_is_wider_than_range_a` | For every parameterised class, the test-split parameter range strictly contains the dev range. |
| `tests/test_corruption_classes.py::test_class15_rounding_does_not_break_truth_sum` | Class 15 alters only rendered fee lines; truth still sums exactly. |
| `tests/test_arms_baseline.py::test_a0_never_predicts_multi_item` | A0's predictions all have length 0 or 1 — it cannot express N:M by construction. |
| `tests/test_arms_baseline.py::test_a1_assignment_is_injective` | No ledger item is assigned to two credits and no credit to two items. |
| `tests/test_arms_baseline.py::test_a1_beats_greedy_on_a_fixture` | On a fixture where greedy is suboptimal, `linear_sum_assignment` finds strictly lower total cost. This is the test that proves the baseline is honest. |
| `tests/test_arms_baseline.py::test_arms_without_exception_path_report_na` | A0 and A1 `ArmResult.has_exception_path` is False, and the metric cell for exceptions is `NA`, not `0`. |
| `tests/test_metrics.py::test_precision_recall_on_hand_worked_example` | P and R agree with a hand-computed fixture, as exact Fractions. |

**Definition of done.**

```
make test && python -m eval.cli --split dev --arms a0,a1 --out artifacts/dev/cp2 && cat artifacts/dev/cp2/baselines.md
```

Must produce `artifacts/dev/cp2/baselines.md` with A0 and A1 assignment P/R and
exact-decomposition on dev, the A1 tuning sweep appended to `docs/EVALUATION.md`, and the
held-out class id recorded there.

**Notes for the executor.**

1. **Tune A1 properly.** §9.1 is blunt about this and NN-13 restates it: a sandbagged baseline
   is worse than no baseline, because a reviewer who spots it discounts every number you
   produced. Sweep on dev, pick the setting that is best *for A1*, and write the sweep down.
   The README sentence that documents this is fixed in D15.5 — use it verbatim.
2. The held-out class choice is frozen here. Criteria and the selection are in D4.8; record the
   id in `docs/EVALUATION.md` in this checkpoint's commit.
3. Stacked corruptions belong to the test split only. Dev carries at most one class per credit
   so that per-class dev tuning is attributable; test carries two or three so the
   generalisation claim means something (§8.4).
4. Do not build A2 here. A2 needs the real deduction-stack arithmetic and the same
   cross-window logic as A3, neither of which exists until CP3/CP4, and a rules-only baseline
   built without them would be exactly the sandbagging the previous note forbids. A2 is CP4.

---

### CP3 · Candidate generation and the solver · 16h · trip-wire 24h

**Goal.** Turn `solver.py` into the three modules §10 names, fix the uniqueness-under-tolerance
defect from §0.1, add the Regime A fast path, and prove that a class-4 `MIXED_N_M` credit
decomposes end to end.

**This is the highest-risk checkpoint in the project (§12).** Read §6 of this plan before
starting.

**Owns files.**
`config/solver.yaml` (fill in), `src/residual_zero/candidates.py`,
`src/residual_zero/solver/__init__.py`, `src/residual_zero/solver/bitset_dp.py`,
`src/residual_zero/solver/enumerate.py`, `src/residual_zero/solver/fastpath.py`,
`tests/test_solver_properties.py`, `tests/test_uniqueness.py`,
`tests/test_candidates.py`, `tests/test_fastpath.py`, `tests/bench_solver.py`.

**Depends on.** CP0, CP1.

**Signatures.**

```python
# src/residual_zero/candidates.py
class CandidatePool(BaseModel):
    bank_credit_id: str
    item_ids: tuple[str, ...]              # sorted by (occurred_at, id) — the determinism key
    amounts_paise: tuple[int, ...]         # parallel to item_ids
    amounts_rupees: tuple[int, ...]        # money.to_rupee_units of the above
    scope: PoolScope
    sub_window: tuple[date, date] | None   # set only when scope is REDUCED
    gross_paise: int                       # sum of positive members, for the diagnosis rules

WIDENED_KINDS: frozenset[Kind]             # REFUND CHARGEBACK REPRESENTMENT ADJUSTMENT RESERVE_RELEASE

def build_pool(credit: BankCredit, items: Sequence[LedgerItem],
               cfg: SolverConfig) -> CandidatePool:
    """Filter by account and currency, apply the asymmetric date windows, sort deterministically.
    Returns the FULL pool even when it exceeds MAX_POOL — the cap is the solver's decision."""

def split_pool(pool: CandidatePool, credit: BankCredit,
               cfg: SolverConfig) -> tuple[CandidatePool, ...]:
    """Suffix-growing day sub-windows, each retaining every widened-kind item. Deterministic,
    bounded by cfg.sub_window_split.max_attempts. Every result has scope REDUCED."""

# src/residual_zero/solver/bitset_dp.py
class ReachabilityIndex:
    """Bitset DP over the shifted rupee axis. The NN-10 bounds guard lives inside this class and
    there is no public accessor for the raw bitmask, so no caller can bypass it."""
    NEG: int
    POS: int
    axis_width: int
    def __init__(self, amounts_rupees: Sequence[int]) -> None: ...
    def is_reachable(self, total: int) -> bool:
        """Range-checked bit test on the final mask. Returns False outside [NEG, POS]."""
    def was_reachable_at(self, prefix_len: int, total: int) -> bool:
        """Range-checked bit test on snapshot `prefix_len`. Used only by backtracking."""
    def hits_in_window(self, target: int, epsilon: int) -> tuple[int, ...]:
        """Every reachable total in [target-eps, target+eps], ascending. May be empty."""
    def nearest_reachable(self, target: int) -> int | None:
        """Closest reachable total to target; its delta is the diagnosis layer's primary input."""
    def memory_bytes(self) -> int:
        """(n+1) * axis_width / 8, reported into the audit metrics channel."""

class BudgetExceeded(Exception):
    """Raised internally when a deterministic cap is hit; converted to a SolveResult by solve_search."""

# src/residual_zero/solver/enumerate.py
class SolveResult(BaseModel):
    uniqueness: Uniqueness
    matched_total_rupees: int | None
    member_ids: tuple[str, ...]            # empty unless UNIQUE
    alternates: int                        # solutions found, capped at cfg.enumerate_cap
    nearest_total_rupees: int | None
    nearest_delta_rupees: int | None
    pool_scope: PoolScope
    pool_size: int
    axis_width: int
    hit_totals: tuple[int, ...]            # every reachable total considered — see §0.1
    slack_rupees: int | None               # |matched_total - r(T)|, an ordering_score input
    margin_rupees: int | None              # distance to the nearest OTHER reachable total
    enum_nodes: int

def enumerate_solutions(index: ReachabilityIndex, amounts_rupees: Sequence[int],
                        totals: Sequence[int], cap: int, max_nodes: int,
                        require_nonempty: bool) -> tuple[tuple[int, ...], ...]:
    """Backtrack across EVERY total in `totals` into one shared solution list with one shared
    cap. The empty subset is never a solution. This is the §0.1 correction."""

def solve_search(pool: CandidatePool, target_paise: int,
                 cfg: SolverConfig) -> SolveResult:
    """Regime B. Rupee-granular signed subset-sum with tolerance and uniqueness detection.
    Performs at most cfg.sub_window_split.max_attempts internal attempts when the pool is over
    cap; the pipeline sees ONE solver invocation, so the DAG stays acyclic (§5.1, NN-5)."""

# src/residual_zero/solver/fastpath.py
class DeclaredLine(NamedTuple):
    item_id: str; kind: Kind; amount_paise: int; instrument: Instrument | None

class FastPathResult(BaseModel):
    ok: bool
    member_ids: tuple[str, ...]
    computed_total_paise: int
    residual_paise: int
    line_deltas: tuple[tuple[str, int], ...]   # (item_id, declared - recomputed); drives RATE_MISMATCH
    missing_item_ids: tuple[str, ...]

def verify_declared(credit: BankCredit, declared: Sequence[DeclaredLine],
                    ledger: Mapping[str, LedgerItem],
                    rates: TaxRates, fees: FeeSchedule) -> FastPathResult:
    """Regime A. Re-derive every rate-derived line from the INSTRUMENT and the RATE TABLE,
    never from the declared amount, then sum and require a zero paise residual (D9)."""
```

**Invariants asserted here.**

- **NN-10** — the bounds guard is not a call site, it is the class boundary. `ReachabilityIndex`
  keeps the mask and snapshots private; the only ways to test a bit are `is_reachable` and
  `was_reachable_at`, both of which range-check first.
  `tests/test_solver_properties.py::test_no_public_raw_bitmask` asserts no public attribute of
  the class exposes an `int` mask, so a future caller cannot bypass the guard even carelessly.
- **NN-11** — `build_pool` never truncates; it returns the full pool and marks scope. Over-cap
  handling is `split_pool` plus `BUDGET_EXCEEDED`, and
  `tests/test_candidates.py::test_over_cap_pool_is_never_truncated` asserts the returned pool
  size equals the eligible item count regardless of `MAX_POOL`.
- **NN-9** — `hits_in_window` returns ascending order; `enumerate_solutions` walks totals in
  that order; `build_pool` sorts by `(occurred_at, id)`. No iteration over a set anywhere in
  the module. `test_solver_properties.py::test_order_independence` asserts that permuting the
  input items leaves the returned member **id set** unchanged.
- **NN-12** — nothing in this checkpoint accepts anything. `solve_search` proposes; CP4 decides.
  The word "verify" appears in `fastpath.py` only in the sense of re-deriving a declared
  composition, and its result still passes through CP4's verifier before any ledger write.

**Tests.**

`tests/test_solver_properties.py` is the test that licenses every claim in §9, so it is
specified in full. Oracle:

```python
def brute_force_solutions(amounts: Sequence[int], target: int, tol: int) -> set[frozenset[int]]:
    """Every non-empty index subset whose signed sum lies within tol of target. Exhaustive
    over 2**n. This is the definition the DP must agree with — including under tolerance."""
```

| Property | Claim |
|---|---|
| `test_reachability_agrees_with_brute_force` | `uniqueness in (UNIQUE, AMBIGUOUS)` iff the oracle finds at least one subset. |
| `test_uniqueness_agrees_with_brute_force_under_tolerance` | Oracle count `== 1` iff `UNIQUE`; oracle count `>= 2` iff `AMBIGUOUS`. **Run this against the unmodified reference first — it should fail, and that failure is the evidence for the §0.1 change.** |
| `test_claimed_match_verifies` | `UNIQUE` implies the members' signed sum is within tolerance of the target and equals `matched_total_rupees`. The F14 invariant. |
| `test_members_empty_unless_unique` | Any non-`UNIQUE` result has `member_ids == ()` — never expose a guess. |
| `test_empty_subset_is_never_a_solution` | A target inside tolerance of zero does not return the empty set as a decomposition. |
| `test_bounds_guard_returns_cleanly` | Targets far outside `[NEG, POS]` return `NONE_FOUND` and never raise, at both signs. |
| `test_nearest_reachable_is_the_true_argmin` | `nearest_total_rupees` equals the oracle's closest reachable sum to the target. |
| `test_solution_count_monotone_in_tolerance` | Widening tolerance never decreases the oracle solution count, and never turns `AMBIGUOUS` into `UNIQUE`. |
| `test_order_independence` | Permuting the input yields the same member id set. |
| `test_no_public_raw_bitmask` | No public attribute of `ReachabilityIndex` is an `int` bitmask. |
| `test_budget_exceeded_rather_than_silent_truncation` | A pool over `MAX_POOL` returns `BUDGET_EXCEEDED`, not a truncated answer. |
| `test_axis_width_cap_is_deterministic` | Two runs on the same over-wide instance both return `BUDGET_EXCEEDED`. |

Hypothesis domain: `amounts = lists(integers(-60, 60).filter(lambda x: x != 0), min_size=1,
max_size=14)`, `target = integers(-200, 200)`, `tol = integers(0, 5)`. Bounded at 14 so the
`2**n` oracle stays honest. The three seeded loops carried over from `test_solver.py`
(800 signed instances, 300 tolerance instances, 500 invariant instances) are retained as
regression cases against the new module path, with the tolerance loop upgraded to compare
uniqueness rather than only reachability.

| Other files | Claim |
|---|---|
| `tests/test_uniqueness.py::test_every_class23_credit_is_ambiguous` | Every class-23 credit in dev returns `AMBIGUOUS` with `alternates >= 2` and empty members. This is the proof the uniqueness detector works. |
| `tests/test_uniqueness.py::test_no_class23_credit_is_ever_cleared` | No class-23 credit reaches a `CLEARED` disposition. |
| `tests/test_candidates.py::test_window_asymmetry` | Only the five widened kinds appear from before `D-5`; a `PAYMENT` at `D-10` is excluded. |
| `tests/test_candidates.py::test_deterministic_sort` | Pool order is `(occurred_at, id)` and stable across input permutation. |
| `tests/test_candidates.py::test_over_cap_pool_is_never_truncated` | Pool size equals the eligible count regardless of `MAX_POOL`. |
| `tests/test_candidates.py::test_split_is_deterministic_and_bounded` | `split_pool` returns the same sub-windows every run, at most `max_attempts` of them, each marked `REDUCED`. |
| `tests/test_fastpath.py::test_fee_is_recomputed_not_copied` | Corrupting the **declared** fee changes `line_deltas` but does not change `computed_total_paise`. This is the test that proves the fast path verifies rather than restates (D9). |
| `tests/test_fastpath.py::test_gst_derives_from_recomputed_fee` | GST is computed from the recomputed fee, so a wrong declared fee does not propagate into a matching wrong GST. |
| `tests/test_fastpath.py::test_missing_ledger_item_is_reported` | A declared line with no ledger counterpart appears in `missing_item_ids`. |

**Definition of done.**

```
make test && python -m residual_zero.cli solve --split dev --class 4 --limit 5 --show-proof && python -m tests.bench_solver --pools-from data/dev
```

Must produce: five class-4 credits decomposed with a residual of zero, and a benchmark line
recording median and worst solve time **with the machine and interpreter named**, appended to
`PROGRESS.md`.

**Notes for the executor.**

1. **Start from `solver.py`, do not reimplement it.** The DP, the axis offset, the snapshot
   backtracking and the bounds guard are all validated. What changes is the module boundary,
   the private-mask encapsulation, and the enumeration-across-all-hits correction.
2. **Do the §0.1 correction as the first thing in this checkpoint**, not the last. Write the
   corrected oracle, watch it fail against the reference, then fix. That ordering is what makes
   the incident log entry real rather than reconstructed.
3. **Class 4 `MIXED_N_M` must pass end to end before you write a line of CP5, CP6 or CP7.**
   §12 names the wrong data model as the risk that kills competitors and this is the moment it
   is retired. The definition-of-done command exists for exactly that.
4. **The trip-wire is quantitative.** If median solve time exceeds 2s per credit, stop
   optimising and ship the `BUDGET_EXCEEDED` path (§12). An honest exception costs coverage; a
   hang costs the submission. Record the decision in `PROGRESS.md` either way.
5. Snapshot memory is `(n+1) * axis_width / 8` bytes. At the configured caps that is bounded;
   report `memory_bytes()` into the metrics channel so it is observable rather than assumed. If
   it bites, §12's documented fallback is to recompute forward instead of snapshotting and
   accept the constant factor — do not invent a third option.
6. The sub-window retry is **internal to `solve_search`** and bounded. It is not a pipeline
   retry and must not be implemented as one: NN-5 and §5.1 permit exactly one forward-branching
   edge, which is fail-or-ambiguous into diagnosis, and it must stay the only one.
7. `ε` comes from D6/D7 and is already derived. Do not widen it to make a failing case pass.
   Widening trades a coverage loss for an ambiguity loss and buys nothing, and F32 in Phase 3
   is where the constant properly goes away.

---
### CP4 · Verifier, proof, hash-chained audit, property tests, A2 · 16h · trip-wire 24h

**Goal.** Make the verifier the sole writer to the reconciliation ledger at the connection
level, emit the §5.7 proof block, hash-chain the audit log for real, put Hypothesis on the
arithmetic invariant, and build the strongest non-AI, non-exact-solver baseline.

**Owns files.**
`src/residual_zero/db.py`, `src/residual_zero/verify.py`, `src/residual_zero/proof.py`,
`src/residual_zero/audit.py`, `src/residual_zero/canonical.py`,
`src/residual_zero/orchestrator.py` (first version), `src/residual_zero/cli.py`,
`eval/arms/a2_rules.py`, `tests/test_verify.py`, `tests/test_proof.py`,
`tests/test_audit_chain.py`, `tests/test_least_privilege.py`,
`tests/test_arithmetic_invariant.py`, `tests/test_arms_rules.py`.

**Depends on.** CP0, CP1, CP2, CP3.

**Signatures.**

```python
# src/residual_zero/canonical.py — D11 pins every byte of this
def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    allow_nan=False).encode('utf-8'), with every string NFC-normalised first and every
    datetime rendered by tz.iso_utc. Floats are forbidden in a payload and raise."""

def payload_digest(payload: Mapping[str, Any]) -> str:
    """Lowercase hex sha256 of canonical_json(payload)."""

# src/residual_zero/db.py — least privilege, visible in code (§5.12)
def open_readonly(path: Path) -> sqlite3.Connection:
    """sqlite3.connect('file:...?mode=ro', uri=True). Writes are rejected by the driver."""

def _open_readwrite(path: Path, owner: str) -> sqlite3.Connection:
    """Module-private. `owner` must be one of the three declared table owners; anything else
    raises. WAL mode. The owner->tables map is a literal in this module, so the privilege
    boundary is readable in one screen."""

TABLE_OWNERS: dict[str, frozenset[str]] = {
    "verify":     frozenset({"reconciliation", "decomposition_member"}),
    "audit":      frozenset({"audit_entry"}),
    "exceptions": frozenset({"exception", "exception_resolution"}),
}

# src/residual_zero/verify.py — the ONLY writer to the reconciliation tables
class VerificationOutcome(BaseModel):
    accepted: bool
    residual_paise: int
    derived_lines: tuple[ProofLine, ...]
    mismatched_line_ids: tuple[str, ...]
    reason: str | None                    # populated only when accepted is False

def verify_decomposition(credit: BankCredit, member_ids: Sequence[str],
                         ledger: Mapping[str, LedgerItem], regime: Regime,
                         rates: TaxRates, fees: FeeSchedule) -> VerificationOutcome:
    """Re-derive every rate-derived line at PAISE granularity, independently of the search,
    in the fixed order given in D10. Accepts only on a zero residual and a fully consistent
    derivation. NN-12: this condition never widens, whatever the search tolerance is."""

def write_cleared(conn: sqlite3.Connection, decomposition: Decomposition) -> None:
    """Insert a cleared decomposition. The only function in the codebase that writes here."""

# src/residual_zero/proof.py
def build_proof(credit: BankCredit, outcome: VerificationOutcome, solve: SolveResult,
                regime: Regime, tier_mix: Mapping[ResolutionTier, int],
                rate_digest: str) -> ProofRecord: ...

def render_proof(proof: ProofRecord, credit: BankCredit) -> str:
    """The §5.7 calculator-checkable block, aligned, IST dates, rupees from money.format_rupees.
    Every figure is rendered here; nothing downstream formats a number."""

# src/residual_zero/audit.py
class AuditEntry(BaseModel):
    seq: int
    payload: dict[str, Any]          # deterministic; hashed
    metrics: dict[str, Any]          # timings, memory; NOT hashed, NOT diffed by make reproduce
    prev_hash: str
    entry_hash: str

GENESIS_PREV_HASH: str = "0" * 64

def append_entry(conn: sqlite3.Connection, payload: Mapping[str, Any],
                 metrics: Mapping[str, Any]) -> AuditEntry:
    """entry_hash = sha256(canonical_json(payload) || 0x00 || prev_hash_ascii). D11 pins it."""

def verify_chain(conn: sqlite3.Connection) -> tuple[bool, int | None, str]:
    """Walk the chain. Returns (ok, first_broken_seq, head_hash). Powers make verify-audit."""

# eval/arms/a2_rules.py
def run_a2(items: Sequence[LedgerItem], credits: Sequence[BankCredit],
           rates: TaxRates, fees: FeeSchedule, cfg: SolverConfig) -> ArmResult:
    """Full deduction-stack arithmetic plus largest-first greedy subset selection. Uses the SAME
    candidates.build_pool as A3, so it inherits the same windows and the same MAX_POOL budget
    path. No model, no exact solver, no uniqueness check: clears on the first subset within
    tolerance (§9.1)."""
```

**Invariants asserted here.**

- **NN-12** — `verify_decomposition` accepts only `residual_paise == 0` with no mismatched
  lines. `tests/test_verify.py::test_acceptance_never_widens_with_tolerance` runs the verifier
  with `ε` set to its maximum and asserts acceptance is unchanged: search tolerance is not an
  input to this function's signature, which is the structural half of the guarantee.
- **§5.12 least privilege** — `_open_readwrite` is module-private and rejects an unknown owner.
  `tests/test_least_privilege.py::test_only_verify_writes_reconciliation` greps for importers
  of `_open_readwrite` and asserts the set is exactly the three declared owners, and
  `::test_readonly_connection_rejects_write` asserts a write on an `open_readonly` handle
  raises at the driver level.
- **NN-9** — timings live in `metrics`, never in `payload`, so the chain hash and the report are
  both reproducible. `canonical_json` raises on a float, which is what stops a stray
  `ordering_score` from making the chain machine-dependent; the score enters the payload as its
  fixed six-decimal string.
- **NN-1** — `verify_decomposition` operates entirely on `int` paise. The residual is an `int`
  and the acceptance test is `== 0`, not a comparison against an epsilon.
- **F14** — `tests/test_arithmetic_invariant.py` puts Hypothesis on the whole path: for any
  generated pool and target, if the system reports `CLEARED` then the verifier re-derives a
  zero residual.

**Tests.**

| File · function | Claim |
|---|---|
| `tests/test_verify.py::test_accepts_only_zero_residual` | A one-paise residual is rejected. |
| `tests/test_verify.py::test_acceptance_never_widens_with_tolerance` | Acceptance is identical at minimum and maximum `ε`. |
| `tests/test_verify.py::test_rederives_rather_than_trusts` | Mutating a member's declared fee flips acceptance to False, because the line is recomputed from instrument and rate. |
| `tests/test_verify.py::test_rounding_is_rederived_not_tolerated` | A class-15 rounding case is rejected with a named mismatched line rather than accepted within a tolerance. |
| `tests/test_proof.py::test_proof_lines_sum_to_computed_total` | The sum of `ProofLine.amount_paise` equals `computed_total_paise` exactly. |
| `tests/test_proof.py::test_rendered_block_is_calculator_checkable` | Parsing the rupee figures back out of `render_proof` and summing them reproduces the credit amount. This is the reviewer's eight-second check, automated. |
| `tests/test_proof.py::test_every_line_names_its_derivation` | Every `ProofLine.derived_from` is `LEDGER`, a `RATE_TABLE:` path, or `DECLARED`. |
| `tests/test_audit_chain.py::test_chain_verifies_end_to_end` | `verify_chain` returns ok on a freshly written chain. |
| `tests/test_audit_chain.py::test_edit_breaks_chain_at_that_entry` | Mutating entry `k`'s payload makes `verify_chain` report `first_broken_seq == k`. |
| `tests/test_audit_chain.py::test_genesis_seeds_with_zeroes` | Entry 0's `prev_hash` is 64 zeros. |
| `tests/test_audit_chain.py::test_canonical_json_is_byte_stable` | Key order, separators, unicode form and datetime format are identical across two processes. |
| `tests/test_audit_chain.py::test_metrics_do_not_affect_entry_hash` | Changing `metrics` leaves `entry_hash` unchanged. |
| `tests/test_least_privilege.py::test_only_verify_writes_reconciliation` | The importer set of `_open_readwrite` is exactly the three declared owners. |
| `tests/test_least_privilege.py::test_readonly_connection_rejects_write` | A write through `open_readonly` raises. |
| `tests/test_arithmetic_invariant.py::test_claimed_clear_verifies_at_paise` | Hypothesis: `CLEARED` implies a zero paise residual. The invariant the whole product rests on. |
| `tests/test_arms_rules.py::test_a2_uses_the_same_pool_as_a3` | A2 and A3 receive byte-identical candidate pools for the same credit. |
| `tests/test_arms_rules.py::test_a2_has_no_uniqueness_check` | On a class-23 credit A2 clears something, demonstrating what the uniqueness check is worth. |

**Definition of done.**

```
make test && make verify-audit && python -m eval.cli --split dev --arms a2 --out artifacts/dev/cp4
```

`make verify-audit` must exit zero and print the chain head hash and the entry count.

**Notes for the executor.**

1. **Pin canonical JSON exactly as D11 specifies and do not improvise.** Two implementations
   that differ by one space produce a chain that fails to verify on a different machine, and
   that failure looks like tampering.
2. The `payload` / `metrics` split is load-bearing, not tidiness. §5.8 asks for wall time in the
   log; putting wall time in the hashed payload would make `make reproduce` fail for a reason
   that has nothing to do with determinism of the decisions. Timings go in `metrics`.
3. A2 gets the real tax config, the real cross-window widening and the same pool builder. §9.1
   is explicit that the baselines must be good. The only things A2 lacks are the exact solver
   and the uniqueness check, because those are the two things it exists to measure.
4. `orchestrator.py` at this checkpoint is the plain DAG for the arithmetic path only: ingest,
   normalise, candidates, solve, verify, proof, audit, disposition. No semantic layer yet, no
   exception classification yet. Keep it a sequence of typed function calls in one file — NN-5,
   and the argument for it goes in `docs/DECISIONS.md` if it is not there from CP0.

---

### CP5 · Semantic tiers, exceptions, ordering score, and the human baseline · 16h · trip-wire 24h

**Goal.** Build the five-tier resolution cascade with an on-disk cache, the deterministic
exception decision table with model-written narrative, and the ordering score. Then stop
coding and run F19 and F56.

**Owns files.**
`config/llm.yaml`, `src/residual_zero/semantic/__init__.py`,
`src/residual_zero/semantic/tiers.py`, `src/residual_zero/semantic/llm.py`,
`src/residual_zero/semantic/schema.py`, `src/residual_zero/exceptions/__init__.py`,
`src/residual_zero/exceptions/classify.py`, `src/residual_zero/exceptions/narrate.py`,
`src/residual_zero/ordering.py`, `src/residual_zero/orchestrator.py` (extend),
`tests/test_tiers.py`, `tests/test_no_amounts_to_model.py`, `tests/test_classify.py`,
`tests/test_ordering_score.py`, `artifacts/human_study/` (protocol, sheets, results).

**Depends on.** CP0–CP4.

**Signatures.**

```python
# src/residual_zero/semantic/schema.py — the NN-3 mechanism is the TYPE
class CandidateEntity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    display_name: str
    # There is deliberately no numeric field on this model, or on the request below.

class EntityResolutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    narration_norm: str
    counterparty_text: str
    candidates: tuple[CandidateEntity, ...]      # the closed set

class EntityResolutionResponse(BaseModel):
    selected_id: str | None                      # None is a valid abstention
    reason: str
    # A model validator rejects any selected_id not in the request's candidate ids.

class NarrationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    exception_class: ExceptionClass
    facts: tuple[str, ...]                       # qualitative only, e.g. 'delta is negative'
    slots: tuple[str, ...]                       # '{DELTA}', '{GROSS}', '{PCT}' — names, no values

class NarrationResponse(BaseModel):
    prose: str                                   # may contain only slots present in the request

class AmountLeakError(RuntimeError):
    """Raised before egress when a payload contains a money-shaped literal. NN-3 as a mechanism."""

MONEY_PATTERN: re.Pattern      # r'\d[\d,]*\.\d{2}' | r'(?:₹|Rs\.?|INR)\s*\d'

def assert_no_amounts(payload_bytes: bytes) -> None:
    """Scan an outbound payload for money-shaped literals and raise AmountLeakError on a hit.
    Deliberately does not reject bare digit runs: UTRs and invoice numbers are legitimate."""

# src/residual_zero/semantic/llm.py
class LLMClient(Protocol):
    def resolve_entity(self, request: EntityResolutionRequest) -> EntityResolutionResponse | None: ...
    def narrate(self, request: NarrationRequest) -> NarrationResponse | None: ...

class CachedLLMClient:
    """Wraps a provider. Cache key = sha256(canonical_json({'prompt_version': int,
    'model_id': str, 'request': request.model_dump()})). Stored at data/cache/llm/{key}.json.
    In offline mode a miss raises instead of calling out, so make eval is reproducible and a
    provider outage becomes a cache hit (§5.9)."""
    def __init__(self, provider: LLMClient, cache_dir: Path, offline: bool,
                 token_budget: int) -> None: ...

class TokenBudgetExceeded(RuntimeError):
    """Raised when the hard per-run token budget is exhausted. Fails loudly (§12)."""

# src/residual_zero/semantic/tiers.py
class Resolution(NamedTuple):
    counterparty_id: str | None
    tier: ResolutionTier
    score: int | None                # rapidfuzz score when tier 3, else None

def resolve(counterparty_raw: str, narration_norm: str, reference_token: str | None,
            registry: EntityRegistry, cfg: SemanticConfig,
            client: LLMClient | None) -> Resolution:
    """Tier 1 exact-normalised, tier 2 reference token, tier 3 rapidfuzz above threshold with a
    top-two margin, tier 4 model over a closed shortlist, tier 5 unresolved -> exception.
    The model is reached only on the residue of 1-3, and only ever returns an id (§5.9, NN-2)."""

def tier_mix(resolutions: Iterable[Resolution]) -> dict[ResolutionTier, int]:
    """Counts per tier. This is F6's published number."""

# src/residual_zero/exceptions/classify.py
class ExceptionSignals(BaseModel):
    """Every input to classification, all observable. No model output appears here."""
    uniqueness: Uniqueness
    pool_scope: PoolScope
    alternates: int
    pool_size: int
    pool_gross_paise: int
    nearest_delta_paise: int | None
    delta_matches_pool_member_ids: tuple[str, ...]
    delta_matches_out_of_window_item_ids: tuple[str, ...]
    delta_equals_twice_member_ids: tuple[str, ...]     # the SIGN_REVERSAL signature
    duplicate_credit_ids: tuple[str, ...]
    declared_line_deltas: tuple[tuple[str, int], ...]
    unresolved_entity_count: int
    cross_window_member_count: int
    max_resolution_tier: ResolutionTier

class Classification(BaseModel):
    exception_class: ExceptionClass
    matched_rule: str
    rule_matched: bool                 # False when the declared fallback fired

def classify(signals: ExceptionSignals, rates: TaxRates, fees: FeeSchedule,
             cfg: SolverConfig) -> Classification:
    """Deterministic decision table, first match wins, precedence exactly as D13 lists it.
    The model never assigns the class (§5.10)."""

# src/residual_zero/exceptions/narrate.py
def narrate(classification: Classification, signals: ExceptionSignals,
            slot_values: Mapping[str, str], client: LLMClient | None) -> str:
    """Model writes prose containing slot names; this function substitutes the pre-rendered
    figures. A money-shaped literal in the model's output rejects the response and falls back
    to the deterministic template — never a retry loop (§5.12, §0.5)."""

# src/residual_zero/ordering.py
def ordering_score(solve: SolveResult, resolutions: Sequence[Resolution],
                   cross_window_members: int, member_count: int,
                   cfg: SolverConfig) -> float:
    """Weighted geometric mean of six observable terms (D14). NEVER model confidence (NN-4).
    Rendered as a fixed six-decimal string everywhere it is compared or published."""
```

**Invariants asserted here.**

- **NN-2** — the model's only two jobs are selecting a `counterparty_id` from a closed set and
  writing slotted prose. `tests/test_classify.py::test_classification_is_pure` asserts
  `classify` has no `LLMClient` parameter and no model output in `ExceptionSignals`, so a model
  cannot reach the class assignment even by accident.
- **NN-3** — enforced twice. Type level: neither `EntityResolutionRequest` nor
  `NarrationRequest` has a numeric field, and both forbid extras. Runtime:
  `assert_no_amounts` scans every outbound payload.
  `tests/test_no_amounts_to_model.py::test_no_cached_prompt_contains_an_amount` re-checks the
  claim against every file in the on-disk cache after a full dev run, which is the version of
  the test that would catch a future regression.
- **NN-4** — `ordering_score`'s signature has no confidence parameter and `Resolution` carries
  a `tier` and a `rapidfuzz` score, both observable.
  `tests/test_ordering_score.py::test_no_model_confidence_input` asserts the term list is
  exactly the six declared observables.
- **NN-9** — the cache makes model calls reproducible; `--offline` turns a miss into a failure
  rather than a nondeterministic call.

**Tests.**

| File · function | Claim |
|---|---|
| `tests/test_tiers.py::test_tier_order_is_respected` | An item resolvable at tier 1 never reaches tier 3 or 4. |
| `tests/test_tiers.py::test_model_only_sees_the_residue` | With a stub client that records calls, the call count equals the count of items unresolved by tiers 1–3. |
| `tests/test_tiers.py::test_out_of_shortlist_response_becomes_an_exception` | A stub returning an id absent from the candidate set yields `ENTITY_UNRESOLVED`, never a free-text write. |
| `tests/test_tiers.py::test_abstention_is_not_a_failure` | `selected_id=None` routes to exception cleanly with no retry. |
| `tests/test_tiers.py::test_cache_hit_avoids_a_call` | A second identical request makes zero provider calls. |
| `tests/test_tiers.py::test_offline_miss_raises` | In offline mode a cache miss raises rather than calling out. |
| `tests/test_tiers.py::test_token_budget_fails_loudly` | Exceeding the per-run budget raises `TokenBudgetExceeded`. |
| `tests/test_no_amounts_to_model.py::test_request_types_have_no_numeric_fields` | Neither request model has an int, float or Decimal field, at any nesting depth. |
| `tests/test_no_amounts_to_model.py::test_money_shaped_payload_raises` | A payload containing a rupee figure raises `AmountLeakError`. |
| `tests/test_no_amounts_to_model.py::test_utr_is_not_mistaken_for_an_amount` | A payload containing a UTR passes — the guard is precise, not paranoid. |
| `tests/test_no_amounts_to_model.py::test_no_cached_prompt_contains_an_amount` | After a full dev run, no cached prompt matches `MONEY_PATTERN`. |
| `tests/test_no_amounts_to_model.py::test_narration_response_with_a_literal_is_rejected` | Model prose containing a rupee figure is rejected and the deterministic template is used. |
| `tests/test_classify.py::test_one_case_per_class` | Eleven fixtures, one per `ExceptionClass`, each classified as intended. |
| `tests/test_classify.py::test_precedence_when_two_rules_match` | A fixture matching both `SUSPECTED_WITHHOLDING` and `UNITEMISED_FEE` resolves by the D13 tie-break, and a fixture that is both `AMBIGUOUS` and over-cap classifies as `BUDGET_EXCEEDED`. |
| `tests/test_classify.py::test_fallback_is_flagged_as_such` | An unexplained delta gets the declared fallback class with `rule_matched=False`. |
| `tests/test_classify.py::test_classification_is_pure` | `classify` takes no client and no model output. |
| `tests/test_ordering_score.py::test_unresolved_entity_annihilates_the_score` | Any unresolved entity gives a score of exactly 0, so the credit can never clear. |
| `tests/test_ordering_score.py::test_each_term_is_monotone` | Worsening any single observable never raises the score. |
| `tests/test_ordering_score.py::test_score_renders_identically_across_processes` | The six-decimal rendering is byte-stable. |
| `tests/test_ordering_score.py::test_no_model_confidence_input` | The term list is exactly the six declared observables. |

**Definition of done.**

```
make test && python -m residual_zero.cli run --split dev --offline --out artifacts/dev/cp5 && ls artifacts/human_study/results.json
```

Must produce: the tier mix for the dev split, exception classes assigned across the dev
split, and — before this checkpoint closes — `artifacts/human_study/` containing the frozen
credit selection, three sealed rater sheets, the pre-registered question, and `results.json`.

**Notes for the executor.**

1. **This checkpoint has a hard stop in the middle of it.** When the code above works, stop
   coding and run F19 and F56 to the protocol in D18. Twenty dev credits, stopwatch running,
   your own accuracy against truth scored afterwards, the places you personally got confused
   written down, and two other raters briefed in the same window. §6.1 and §6.2 both say this
   cannot be done later and they are right: once you know the system's answers an honest human
   baseline no longer exists, and that applies to briefing raters as much as to reconciling
   yourself. F56 is in the NN-21 protected set, so if it runs long it gets finished to its
   minimum measurable version and the overrun is logged — it does not get reverted.
2. Register the F56 question **before** scoring anything, in `docs/EVALUATION.md`, with a
   timestamp: on the credits where raters disagreed with each other, did the system flag rather
   than clear? Pre-registering is what makes the answer count either way, and CP6 answers it.
3. The twenty credits come from **dev**. Using test credits here would spend part of the
   NN-16 test budget on a human study and contaminate the split.
4. PII redaction is **not** in Phase 1 — F49 is Phase 2 and §8's scope is fixed. What CP5 owes
   is the *amount* boundary (NN-3), which is a different guarantee. Note the PII gap explicitly
   in the README limitations section at CP9 rather than leaving a reviewer to find it; naming it
   yourself is worth more than the Phase 1 hours it would cost to fix.
5. `config/llm.yaml` holds the model id, the effort setting, the prompt version integer and
   the per-run token budget. Credentials come from the environment and are never committed.
   Bump `prompt_version` whenever a prompt changes — it is part of the cache key, and forgetting
   it is how you serve stale answers to a new prompt and cannot work out why.
6. The provider choice and the spend ceiling are the user's call, not yours — see
   `PLAN-QUESTIONS.md` Q2. If the answer has not arrived, build against the `LLMClient`
   protocol with a stub, run the dev split `--offline`, and report the tier 1–3 mix. That is a
   real and publishable F6 result on its own; tier 4's contribution then lands when the
   provider does.

---
### CP6 · The evaluation harness · 16h · trip-wire 24h

**Goal.** Complete every §9.2 metric, the §9.3 per-class table, Wilson intervals with a
per-seed range beside them, the §9.5 risk-coverage curve, the §9.6 ablations and the §9.7 cost
accounting. Run the harness at full scale. Read the autonomy threshold off the curve.

**Gap closed here — and read this before you run anything.** §11 Day 6 says "first full
800-credit run" and also "all tuning on dev only". The 800-credit corpus of §8.4 *is* the test
split, and NN-16 permits one test-split evaluation per tagged release, taken at the gate — which
is CP9, not CP6. So CP6 does **not** touch the test split. It generates it and leaves it
sealed. The full-scale run happens on `data/devscale/` — seeds 11–18, corruption parameter
range A, counterparty pool A, the same size as the test split — whose only published outputs
are throughput, cost and memory. Every quality number at CP6 comes from `data/dev/`. Running
the test split here would spend one of four project-lifetime evaluations on a checkpoint that
is still being tuned, and it is unrecoverable.

**Owns files.**
`eval/metrics.py` (complete), `eval/stats.py`, `eval/ablate.py`, `eval/report.py`,
`eval/cli.py`, `eval/arms/a3_full.py`, `eval/arms/a4_human.py`, `eval/curve.py`,
`config/profiles/phase1_devscale.yaml`, `docs/EVALUATION.md` (extend),
`tests/test_metrics.py`, `tests/test_stats.py`, `tests/test_report_assertions.py`,
`tests/test_curve.py`.

**Depends on.** CP0–CP5.

**Signatures.**

```python
# eval/metrics.py
class NA:
    """Sentinel for a metric an arm structurally cannot have. Renders '—'. The distinction
    between 'not applicable' and 'zero' lives in the DATA STRUCTURE, not the formatter (D16)."""

MetricCell = Fraction | int | NA

class ArmMetrics(BaseModel):
    arm: str
    regime: Regime | None                       # None means 'both regimes pooled'
    n_credits: int
    n_cleared: int
    n_cleared_correct: int
    n_flagged: MetricCell
    n_budget_exceeded: MetricCell
    n_exact: int
    assignment_precision: MetricCell
    assignment_recall: MetricCell
    exception_precision: MetricCell
    residual_median_paise: MetricCell
    residual_p95_paise: MetricCell
    residual_median_bp: MetricCell              # integer basis points of credit value
    tokens: int
    cost_paise: int
    cache_hit_rate: Fraction
    wall_clock_ms: int
    machine: str                                # §9.2 requires throughput on stated hardware

def genuinely_required_human(record: TruthRecord, pool: CandidatePool) -> bool:
    """The exception-precision predicate, defined over TRUTH at CP0 in docs/EVALUATION.md and
    frozen: a member is absent from every rendered view, or the credit is class 23, or a truth
    member falls outside the candidate window. This is what stops 'flag everything' from
    gaming the safety metric (§9.2)."""

def compute_arm_metrics(result: ArmResult, truth: Sequence[TruthRecord],
                        pools: Mapping[str, CandidatePool], regime: Regime | None) -> ArmMetrics: ...

def per_class_table(results: Mapping[str, ArmResult],
                    truth: Sequence[TruthRecord]) -> tuple[ClassRow, ...]:
    """One row per corruption class 1–23 with n, assignment P/R, exact, coverage, error and a
    note column (§9.3). Classes with no meaningful P/R — class 23 — render NA, not zero."""

# eval/stats.py
class ProportionEstimate(BaseModel):
    pooled: Fraction
    wilson_lo: float
    wilson_hi: float
    per_seed: tuple[Fraction, ...]
    seed_min: Fraction
    seed_max: Fraction
    n: int

def wilson_interval(successes: int, n: int, z: float = 1.959963984540054
                    ) -> tuple[float, float]:
    """Wilson score interval. Used because the most important number lives near 0, where the
    normal approximation misbehaves (§9.4)."""

def pooled_with_per_seed(per_seed_counts: Sequence[tuple[int, int]]) -> ProportionEstimate:
    """Pool across seeds, compute the Wilson interval on the pooled proportion, and carry the
    per-seed proportions separately. There is no code path that returns pooled ± seed spread."""

def cohens_kappa(rater_a: Sequence[str], rater_b: Sequence[str]) -> float:
    """Pairwise Cohen's kappa over the three-category disposition vocabulary (D18)."""

def wilson_at_n50_example() -> tuple[float, float]:
    """Compute the §9.4 small-sample interval rather than quoting it, so the README's
    justification for the batch size is reproduced by code and not copied from the spec."""

# eval/curve.py
class CurvePoint(NamedTuple):
    threshold: str          # the six-decimal rendering, so the sweep is byte-stable
    coverage: Fraction
    error: Fraction
    n_cleared: int

def risk_coverage_curve(decompositions: Sequence[Decomposition],
                        truth: Sequence[TruthRecord]) -> tuple[CurvePoint, ...]:
    """Order by ordering_score, sweep the threshold, return (coverage, error) at each point.
    Computed for A3 and for A2, so the comparison is visible rather than asserted (§9.5)."""

def threshold_at_error_budget(curve: Sequence[CurvePoint],
                              error_budget: Fraction) -> tuple[str, CurvePoint]:
    """Read the operating threshold OFF the curve at a declared error budget. The budget is an
    input recorded in docs/EVALUATION.md; the threshold is a result. Never the other way round."""

# eval/ablate.py
class Ablation(str, Enum):
    NO_LLM_TIER = "NO_LLM_TIER"
    NO_UNIQUENESS = "NO_UNIQUENESS"
    NO_CROSS_WINDOW = "NO_CROSS_WINDOW"
    NO_PAISE_VERIFICATION = "NO_PAISE_VERIFICATION"
    GREEDY_INSTEAD_OF_DP = "GREEDY_INSTEAD_OF_DP"

def run_ablation(which: Ablation, split: str) -> tuple[ArmMetrics, ArmMetrics]:
    """Return (baseline A3, ablated) on the same batch so Δcoverage and Δerror are exact (§9.6)."""

# eval/report.py
def assert_dispositions_sum_to_one(m: ArmMetrics) -> None:
    """For an arm with all three dispositions, n_cleared + n_flagged + n_budget_exceeded ==
    n_credits, as an INTEGER identity. Arms with NA cells are skipped, not coerced to zero."""

def assert_exact_bounded_by_coverage(m: ArmMetrics) -> None:
    """For an arm with no exception path, n_exact <= n_cleared_correct — the integer form of
    exact <= coverage x (1 - error). A3 is exempt because a flagged credit can still carry a
    correct member set (§9.8)."""

def render_headline(metrics: Sequence[ArmMetrics]) -> str: ...
def render_report(...) -> None:
    """Write artifacts/. Calls both assertions before writing anything, so an impossible table
    cannot be published."""
```

`config/solver.yaml` gains, at this checkpoint and not before:

```yaml
autonomy:
  error_budget: TBD-CP6-DECLARED     # the budget you choose and state, e.g. as a Fraction
  threshold: TBD-CP6-CURVE           # READ OFF the curve at that budget. Never hand-picked.
  threshold_source: artifacts/dev/curve_a3.json
```

**Invariants asserted here.**

- **NN-16** — the test split is generated and left sealed. `tests/test_report_assertions.py::
  test_eval_cli_refuses_test_split_without_flag` asserts `eval.cli` requires an explicit
  `--i-am-at-a-gate` flag plus a `docs/EVALUATION.md` log row to run on test, so spending the
  budget is a deliberate act rather than a default.
- **NN-4** — the curve is built from `ordering_score`, whose inputs are the six observables
  fixed at CP5. `tests/test_curve.py::test_curve_inputs_are_observable` re-asserts it at the
  harness boundary.
- **NN-14** — `render_report` writes only figures computed in the same process from the split it
  was given, and stamps every artifact with the split name, the seed list, the commit hash and
  the machine. Nothing is transcribed.
- **§9.8's two constraints** — both assertions run before any write.

**Tests.**

| File · function | Claim |
|---|---|
| `tests/test_metrics.py::test_na_is_not_zero` | An `NA` cell renders `—` and any arithmetic on it raises rather than coercing to 0. |
| `tests/test_metrics.py::test_unpredicted_credit_is_not_exact` | A credit with no prediction counts against exact-decomposition. |
| `tests/test_metrics.py::test_error_rate_on_empty_cleared_set_is_na` | An arm that clears nothing reports `NA` for error rate, not `0`. |
| `tests/test_metrics.py::test_exception_precision_predicate_is_frozen` | `genuinely_required_human` matches the definition committed in `docs/EVALUATION.md` at CP0. |
| `tests/test_metrics.py::test_regime_split_partitions_the_batch` | Regime A and Regime B credit counts sum to the batch. |
| `tests/test_stats.py::test_wilson_contains_pooled` | `wilson_lo <= pooled <= wilson_hi` for a table of fixtures including successes at 0 and at n. |
| `tests/test_stats.py::test_pooled_lies_within_per_seed_range` | `seed_min <= pooled <= seed_max`. |
| `tests/test_stats.py::test_no_api_returns_pooled_plus_seed_spread` | `ProportionEstimate` has no method or property combining the Wilson bounds with the per-seed spread. The §9.4 sloppiness is structurally unavailable. |
| `tests/test_stats.py::test_kappa_on_hand_worked_example` | `cohens_kappa` agrees with a hand-computed 3-category fixture. |
| `tests/test_report_assertions.py::test_impossible_disposition_sum_raises` | A fabricated `ArmMetrics` whose dispositions do not sum to n fails before writing. |
| `tests/test_report_assertions.py::test_exact_exceeding_cleared_correct_raises` | For a no-exception-path arm, `n_exact > n_cleared_correct` fails. |
| `tests/test_report_assertions.py::test_a3_is_exempt_from_the_coverage_cap` | A3 with `n_exact > n_cleared_correct` passes, because flagged credits can be correct. |
| `tests/test_report_assertions.py::test_eval_cli_refuses_test_split_without_flag` | Running on test without the gate flag and log row exits non-zero. |
| `tests/test_curve.py::test_curve_is_monotone_in_threshold` | Raising the threshold never raises coverage. |
| `tests/test_curve.py::test_threshold_is_derived_not_configured` | Changing `error_budget` changes the derived threshold; setting `threshold` by hand in the config is rejected by the loader. |
| `tests/test_curve.py::test_curve_inputs_are_observable` | The curve's ordering key is `ordering_score` and nothing else. |

**Definition of done.**

```
make eval && make test && cat artifacts/dev/headline.md artifacts/dev/per_class.md artifacts/dev/ablations.md
```

Must produce, all from dev or devscale: the four-arm headline table with A4 beside it, the
per-class table for classes 1–23, the risk-coverage curves for A3 and A2, the five ablations,
the cost and throughput block with the machine named, and in `docs/EVALUATION.md` the declared
error budget, the threshold read off the curve, and the answer to the pre-registered F56
question.

**Notes for the executor.**

1. **Read the threshold off the curve and record both numbers.** Declare the error budget first,
   in `docs/EVALUATION.md`, then take the threshold the curve gives you at that budget. §9.5 is
   unusually pointed about this: a threshold picked by hand is a guess wearing a suit. If the
   curve's shape means your budget yields uncomfortably low coverage, publish the low coverage —
   §9.9 says leading with the error rate is the defensible move and it is right.
2. **All tuning on dev.** Every threshold, every prompt, every tolerance. The test split is
   sealed until CP9.
3. Answer the pre-registered F56 question here, whichever way it goes. §9.10 calls F56 one of the
   two rows worth more than all the others; a negative answer honestly reported is still worth
   more than no study.
4. Report every metric separately for Regime A and Regime B. §9.2 and §3.3 both insist, and
   blending them hides that the declared-report path is the easy half.
5. The ablation to be most careful with is `NO_PAISE_VERIFICATION`: it must trust the
   rupee-granularity search result, which means temporarily accepting a non-zero paise residual.
   Implement it as a flag inside the harness, never as a change to `verify.py` — NN-12 says the
   verifier's acceptance never widens, and an ablation is not a licence to widen it.

---

### CP7 · Q&A, console, and the three reviewer-facing commands · 16h · trip-wire 24h

**Goal.** Ship the Q&A surface with structural hallucination prevention, the four console views
with the waterfall, and `make reproduce`, `make challenge`, `make evidence`.

**Owns files.**
`src/residual_zero/qa/__init__.py`, `src/residual_zero/qa/retrieve.py`,
`src/residual_zero/qa/format.py`, `src/residual_zero/qa/compose.py`,
`src/residual_zero/console/__init__.py`, `src/residual_zero/console/app.py`,
`src/residual_zero/console/templates/*.html`, `src/residual_zero/console/static/htmx.min.js`,
`src/residual_zero/console/waterfall.py`, `eval/diff.py` (stub for F54, Phase 2),
`fixtures/challenges/{solvable_aggregate,ambiguous_refused,unsolvable_missing_record}.json`,
`scripts/reproduce.sh`, `scripts/evidence.py`,
`tests/test_qa.py`, `tests/test_console.py`, `tests/test_challenge.py`,
`tests/test_reproducible_report.py`.

**Depends on.** CP0–CP6.

**Signatures.**

```python
# src/residual_zero/qa/retrieve.py
class Intent(str, Enum):
    WHY_SHORT = "WHY_SHORT"; DEDUCTION_STACK = "DEDUCTION_STACK"
    CREDIT_DETAIL = "CREDIT_DETAIL"; EXCEPTION_SUMMARY = "EXCEPTION_SUMMARY"
    TIER_MIX = "TIER_MIX"; UNRECOGNISED = "UNRECOGNISED"

class RetrievedRows(BaseModel):
    intent: Intent
    rows: tuple[dict[str, int | str], ...]      # typed rows straight from parameterised SQL
    citations: tuple[str, ...]                  # transaction and decomposition ids

def classify_intent(question: str, client: LLMClient | None) -> Intent:
    """Rules first over a closed intent set; the model may only choose among these ids, never
    generate SQL. UNRECOGNISED is a valid, non-failing answer."""

def retrieve(intent: Intent, params: Mapping[str, str], conn: sqlite3.Connection
             ) -> RetrievedRows:
    """Run one of a closed set of parameterised queries against the RECONCILED ledger only,
    over a read-only connection. Cannot trigger a re-solve and cannot see un-reconciled state."""

# src/residual_zero/qa/format.py
def render_slots(rows: RetrievedRows) -> dict[str, str]:
    """Every figure in an answer is rendered HERE, deterministically, from typed rows."""

def deterministic_answer(rows: RetrievedRows, slots: Mapping[str, str]) -> str:
    """The template answer, used directly when composition is unavailable or rejected."""

# src/residual_zero/qa/compose.py
def compose(question: str, rows: RetrievedRows, slot_names: Sequence[str],
            client: LLMClient | None) -> str:
    """The model receives the question, the intent, and slot NAMES with no values, and returns
    prose containing only those slots. Substitution is total; any money-shaped literal in the
    model's output rejects the response and falls back to deterministic_answer. A hallucinated
    number is therefore architecturally impossible rather than unlikely (§5.11, F9)."""

# src/residual_zero/console/waterfall.py
def waterfall_svg(proof: ProofRecord, credit: BankCredit) -> str:
    """Server-rendered inline SVG: credit at top, each deduction stepping down, residual zero at
    the bottom. Every coordinate and every label computed server-side from integer paise; no
    client-side arithmetic and no chart library."""
```

Console routes, FastAPI with Jinja templates and HTMX, no build step:
`GET /` batch view — three buckets with counts and rupee totals plus the audit chain head;
`GET /credit/{id}` decomposition view — the §5.7 proof block and the waterfall;
`GET /exceptions` queue — diagnosis, candidates, and accept/correct/escalate;
`POST /exceptions/{id}/resolve` — the only write, and it writes to the exception-resolution
table, never to the reconciliation ledger;
`GET /audit` — replay a historical decomposition and report chain integrity.

**Invariants asserted here.**

- **F9 structurally** — `compose` cannot emit a number: its model input carries slot names
  only, and its output passes through the same `MONEY_PATTERN` rejection as CP5's narration.
- **NN-9 / F16 / F20** — `make reproduce` runs `make eval` twice into two directories and diffs
  them, excluding only the `metrics` timing channel, and exits non-zero on any difference.
- **§5.12 least privilege** — the console holds read-only connections except for the single
  exception-resolution write, and `tests/test_console.py::test_console_cannot_write_ledger`
  asserts a ledger write attempt from a console handler raises.

**Tests.**

| File · function | Claim |
|---|---|
| `tests/test_qa.py::test_every_figure_is_slot_substituted` | For a set of questions, every numeral in the final answer traces to a value produced by `render_slots`. |
| `tests/test_qa.py::test_model_prose_with_a_literal_is_rejected` | A stub returning a rupee figure falls back to the deterministic answer. |
| `tests/test_qa.py::test_answers_carry_citations` | Every answer names at least one transaction or decomposition id. |
| `tests/test_qa.py::test_qa_cannot_see_unreconciled_state` | A question about an un-reconciled credit returns nothing rather than partial state. |
| `tests/test_qa.py::test_qa_connection_is_readonly` | The Q&A layer's connection rejects writes. |
| `tests/test_console.py::test_all_four_views_render` | Each of the four routes returns 200 with its expected landmark content. |
| `tests/test_console.py::test_waterfall_lines_sum_to_zero_residual` | The rendered SVG's step values sum to the credit amount. |
| `tests/test_console.py::test_console_cannot_write_ledger` | A ledger write from a console handler raises. |
| `tests/test_challenge.py::test_three_challenge_files_run` | All three fixtures run to a terminal disposition. |
| `tests/test_challenge.py::test_the_unsolvable_challenge_is_refused` | The third fixture reaches an exception with a diagnosis, and is never cleared. |
| `tests/test_reproducible_report.py::test_two_eval_runs_are_byte_identical` | Two dev runs produce identical reports outside the timing channel. |
| `tests/test_reproducible_report.py::test_wallclock_backstop_did_not_fire` | The run is marked reproducible; if the backstop fired, the report is refused. |

**Definition of done.**

```
make test && make reproduce && make challenge FILE=fixtures/challenges/unsolvable_missing_record.json && make evidence && ls -l artifacts/evidence.html
```

`make reproduce` exits zero. `make challenge` on the unsolvable fixture exits zero having
*refused* it — an honest refusal is a success, not a failure. `make evidence` writes one
self-contained HTML file into `artifacts/` containing the headline table, the per-class table,
the risk-coverage curve, the ablations, the audit chain head, the environment fingerprint and
the test-split evaluation count.

**Notes for the executor.**

1. **Ship a challenge case the system genuinely cannot solve** and say so in the file's own
   comment. §6.1 is right that inviting falsification reads as confidence in a way polish never
   does, and the third fixture is the cheapest part of this checkpoint.
2. The waterfall is the highest-value-per-hour visual in the project (§5.13) and it earns that
   only by making the proof legible in four seconds. Inline SVG, server-rendered, no chart
   library, no client-side arithmetic. Resist making it pretty at the cost of making it readable.
3. `make evidence` should assume the reviewer will not run your code. One click to the strongest
   material.
4. If this checkpoint runs long, the cut order from §6.1 as revised is: F17 waterfall, then F9
   Q&A. Both are outside the NN-21 protected set. F20 `make reproduce` and F22 `make evidence`
   are **inside** it and cannot be cut.

---
### CP8 · Razorpay test mode behind an adapter, then failure injection · 16h · trip-wire 24h

**Goal.** Wire Razorpay test mode strictly behind an adapter so it can be cut without touching
another line, then spend the rest of the checkpoint deliberately breaking the system and
writing down what happened.

**Owns files.**
`src/residual_zero/ingest/razorpay.py`, `src/residual_zero/ingest/adapter.py`,
`config/razorpay.yaml`, `tests/test_razorpay_adapter.py`,
`tests/regressions/` (one file per incident), `docs/INCIDENTS.md` (extend),
`fixtures/malformed/` (only what the injection session actually needs).

**Depends on.** CP0–CP7.

**Signatures.**

```python
# src/residual_zero/ingest/adapter.py
class SourceAdapter(Protocol):
    """Every ingestion source implements exactly this. Razorpay is one implementation among
    the CSV adapters, which is what makes it cuttable (§8.5)."""
    def fetch_credits(self, window: tuple[date, date]) -> tuple[BankCredit, ...]: ...
    def fetch_items(self, window: tuple[date, date]) -> tuple[LedgerItem, ...]: ...

# src/residual_zero/ingest/razorpay.py
class RazorpayTestModeAdapter:
    """Reads real test-mode orders, payments, refunds and settlement reports and maps them onto
    LedgerItem / BankCredit. Holds a read-only credential. Never writes anything anywhere."""
    def __init__(self, key_id: str, key_secret: str, enabled: bool) -> None: ...

def normalise_webhook(event: Mapping[str, Any]) -> tuple[str, LedgerItem | None]:
    """Return (idempotency_key, item). Duplicate delivery of the same event id is a no-op."""
```

**The injection session.** Eight injections, all named in §11 Day 8. Each one that breaks
something earns three artifacts: the fix, a regression test under `tests/regressions/`, and a
contemporaneous `docs/INCIDENTS.md` entry.

| # | Injection | The property it probes |
|---|---|---|
| 1 | Kill the model provider mid-run | Tier 4 failure degrades to `ENTITY_UNRESOLVED` exceptions; no partial ledger write, no retry loop. |
| 2 | Corrupt an on-disk cache entry | A malformed cached response is detected and treated as a miss or a hard failure, never parsed into a wrong id. |
| 3 | Deliver a duplicate webhook | Idempotency by event id; ledger state identical after the duplicate. |
| 4 | Truncate a source CSV mid-row | A typed ingestion error naming the line, and **no partial load**. |
| 5 | Feed a pool at and just over `MAX_POOL` | `BUDGET_EXCEEDED` deterministically, and the sub-window path marks `REDUCED` and does not auto-clear. |
| 6 | Skew the clock backwards during a run | Nothing in a hashed payload depends on wall time; the audit chain still verifies. |
| 7 | Force SQLite lock contention | WAL plus the three-owner privilege split survives concurrent readers; a writer conflict raises rather than corrupting. |
| 8 | Plant a wrong rate in `config/fees.yaml` | The verifier rejects, `RATE_MISMATCH` is raised on the Regime A path, and `rate_config_digest` in the proof record changes so the run is not confusable with a correct one. |

**Invariants asserted here.**

- **NN-19** — every incident is written the same hour, raw, contemporaneous: timestamp, symptom,
  what you first thought it was, what it actually was, the fix, the commit hash, the regression
  test. Never smoothed into narrative, never invented.
- **NN-11** — injection 5 is the direct test of it.
- **NN-9** — injection 6 is the direct test of the payload/metrics split from CP4.
- **§8.5** — `tests/test_razorpay_adapter.py::test_disabling_razorpay_changes_nothing` asserts
  that with `enabled: false` the dev-split dispositions are byte-identical, which is what "cut it
  without touching another line" means operationally.

**Tests.** One regression file per incident found, named for the symptom, under
`tests/regressions/`. Plus:

| File · function | Claim |
|---|---|
| `tests/test_razorpay_adapter.py::test_adapter_holds_no_write_capability` | The adapter exposes no method that writes to Razorpay. |
| `tests/test_razorpay_adapter.py::test_disabling_razorpay_changes_nothing` | Dev dispositions are identical with the adapter disabled. |
| `tests/test_razorpay_adapter.py::test_duplicate_webhook_is_idempotent` | Replaying an event id leaves ledger state unchanged. |

**Definition of done.**

```
make test && make verify-audit && make reproduce && python -m tests.injection_session --report artifacts/injections.md
```

Must produce `artifacts/injections.md` listing all eight injections with their outcome, at least
one new file under `tests/regressions/`, and matching `docs/INCIDENTS.md` entries.

**Notes for the executor.**

1. **This checkpoint is supposed to hurt.** An injection session that finds nothing means the
   injections were too gentle — say so in the report and make them harder rather than recording a
   clean sweep.
2. Razorpay wiring goes **first**, so that if it is going to be cut, it is cut early and the
   afternoon is spent on the injections, which are worth more (§6 cut order puts test-mode wiring
   above F24 and below F9).
3. Write incidents **while they are fresh**. §13.2 is blunt about why: the wrong hypothesis you
   chased for forty minutes is exactly what you cannot reconstruct on the last day, and a
   retrospectively smoothed entry reads like fiction because it is. An empty incident log is
   better than an invented one.
4. Do not use a generic AI-generated failure narrative. §13.2 explains the specific risk this
   year, and it is the section the panel reads first.

---

### CP9 · Freeze, one test-split evaluation, README, tag · 10h · trip-wire 15h

**Goal.** Freeze the code, spend exactly one of four project-lifetime test-split evaluations,
finalise the README to §15, regenerate and commit `artifacts/`, tag `v1-submittable`.

**Owns files.**
`README.md` (final), `docs/EVALUATION.md` (the evaluation log row),
`docs/ARCHITECTURE.md`, `docs/DATA.md` (final), `artifacts/**` (regenerated and committed),
`docs/VIDEO.md` (the script, consistent with the numbers on disk).

**Depends on.** CP0–CP8.

**Signatures.** None. This checkpoint writes prose, runs the evaluation once, and tags.

**Invariants asserted here.**

- **NN-16** — exactly one test-split evaluation, logged in `docs/EVALUATION.md` with timestamp,
  commit hash and tag. This is evaluation 1 of a project-lifetime ceiling of 4.
- **NN-14** — every number in `README.md` and `artifacts/` is reproduced by `make eval`. The
  check is mechanical: `tests/test_readme_numbers.py` extracts every numeric literal from the
  README's results tables and asserts each appears in a committed artifact from the same commit.
- **NN-15** — no illustrative figure from `docs/SPEC.md` appears anywhere as though measured. The
  same test greps the README and `artifacts/` for the spec's illustrative values and fails on a
  hit outside a block explicitly labelled as the spec's example.
- **NN-20** — README current, `artifacts/` regenerated, tests green, video script consistent with
  the numbers on disk. Tagged, not "nearly ready".

**Tests.**

| File · function | Claim |
|---|---|
| `tests/test_readme_numbers.py::test_every_readme_number_is_in_an_artifact` | No results figure in the README is absent from a committed artifact. |
| `tests/test_readme_numbers.py::test_no_spec_illustrative_figure_is_republished` | None of the spec's illustrative values appears as a measured result. |
| `tests/test_readme_numbers.py::test_no_tbd_markers_remain` | No `TBD-` marker survives in the README at tag time. |

**Definition of done.**

```
make test && make verify-audit && make reproduce && make eval-test --i-am-at-a-gate && make evidence && git tag v1-submittable && git describe --tags
```

Then, from a clean clone in a private window: `make demo` completes in under two minutes.

**Notes for the executor.**

1. **The README's first screen is exactly four things** (§15): one sentence on what this is, the
   headline four-arm table, one proof block, the four-vector rubric map from §4. Nothing else. No
   badges, no philosophy, no roadmap.
2. Include the test-split evaluation log table. §11 is right that a reviewer with an ML
   background reads it as the most credible artifact on the page, precisely because nobody
   fabricating results would think to include it.
3. State the limitations honestly: the corpus is synthetic, the PII boundary is Phase 2 work, the
   ordering-score weights are uniform rather than fitted, `ε` is derived from the worst case
   rather than fitted (F32 fixes it), and the reserve percentage and bank charge are synthetic
   contract terms rather than sourced rates. §2.3 forbids any ROI claim; do not make one.
4. If the test-split numbers are less impressive than the dev numbers, publish them. §9.9 is the
   section to reread. The one unrecoverable move is publishing a number `make eval` cannot
   reproduce.
5. **Gate 1 is a real gate.** Do not begin Phase 2 until `make demo` runs from a clean clone in a
   private window, every README number is reproduced by `make eval`, the four-arm table carries
   real figures, `docs/INCIDENTS.md` has real entries, and the video exists.

---

**Ladder total.** `8 + 16 + 16 + 16 + 16 + 16 + 16 + 16 + 16 + 10 = 146h`, matching §11's
`8 + 16×8 + 10` exactly. F56's ~5h sits outside the ladder, which is why the phase reads ~151h.

---
## 2 · Design decisions, with reasons

Where §5 already decided something I restate the decision and cite the section rather than
re-deriving it. Where the spec left a genuine gap I close it and mark it **Gap closed here**,
so a reviewer of this plan can see exactly which lines are mine.

### D1 · Canonical model

Field-by-field definitions are in CP0's signature block, which is the single copy. This entry
records the four decisions inside them.

**D1.1 Signedness is enforced by a derived check, not a validator.** §5.3 says inflows positive
and deductions negative, and says to resist storing magnitude plus a direction flag. A Pydantic
validator rejecting a positive `REFUND` would be the natural reading — and it would make
corruption class 18 `SIGN_REVERSAL` un-ingestible, because the loader would raise on the
corrupted view instead of producing the case the system is meant to diagnose. **Gap closed
here:** `models.py` validates only `amount_paise: int` and `!= 0`; `expected_sign(kind)` and
`has_expected_sign(item)` make the convention checkable; generator stage 2 asserts it over
truth; `normalise.sign_anomaly` computes it on ingest and feeds the classifier. Rejected
alternative: a strict and a lenient model class. Two models of the same entity is how a
codebase acquires a silent divergence.

**D1.2 Timezone: tz-aware, stored UTC, displayed IST.** Restated from §5.3. Conversion is
permitted in exactly three places — `proof.render_proof`, the console templates, and
`generator/render.py`, because a real bank statement carries local dates — and all three go
through `tz.to_ist_display`. `tz.py` is the only module that names a timezone, and
`tests/test_models.py::test_naive_datetime_rejected` plus a grep in `tests/test_no_floats.py`'s
sibling scan keep it that way. Rejected alternative: storing IST throughout. Corruption class 6
`DATE_SHIFT_TZ` exists precisely to punish that.

**D1.3 `ordering_score` is the one float in a published record, and it is published as a
string.** §5.3 types it `float` and it is not monetary, so NN-1 is not engaged. But NN-9 is: a
last-bit difference would change a threshold comparison and break `make reproduce`. So the score
is computed in a fixed expression order, rendered once as `f"{score:.6f}"`, and every comparison
and every serialisation uses that string. `canonical_json` raises on a float, which makes this
structural rather than remembered.

**D1.4 `ProofRecord` carries `rate_config_digest`.** Not in §5.3's sketch. **Gap closed here:**
a proof that does not name the rate table it was derived from cannot be replayed, and CP8's
injection 8 plants a wrong rate specifically to check that a run against bad config is not
confusable with a correct one.

### D2 · Config schemas

**Units, decided once: every rate is an integer count of basis points; every amount is integer
paise; nothing is a fraction or a percentage.** §3.2 and NN-8 require externalised rates; the
units question is mine to settle and mixing them is, as CLAUDE.md says, an afternoon of phantom
residuals. A rate needing finer resolution than one basis point gets a new key suffixed
`_micro_bps` rather than becoming a float; the config loader rejects a non-integer `bps`.

`config/tax_rates.yaml` — statutory rates only.

```yaml
# Every entry: integer basis points, a primary source URL, and the date it was verified.
# The loader RAISES UnverifiedRateError on any TBD-VERIFY value, so nothing can run
# against an unverified rate. NN-8.
gst_on_fee:
  bps: TBD-VERIFY            # int. GST is levied on the platform FEE, not on transaction value
  source_url: TBD-VERIFY     # a GST notification or Razorpay's published tax documentation
  as_of: TBD-VERIFY          # YYYY-MM-DD, the date you read the source
  note: "gst = fee x rate. The compounding in §3.2 that spreadsheets drift on."
withholding:
  bps: TBD-VERIFY            # int. ONE provision, named in `note`. See PLAN-QUESTIONS Q1.
  source_url: TBD-VERIFY     # CBDT circular or notification
  as_of: TBD-VERIFY
  note: TBD-VERIFY           # name the section and the base it applies to
```

`config/fees.yaml` — commercial terms. Public pricing gets a source; private contract terms are
marked `synthetic: true`, which is honest rather than evasive.

```yaml
per_instrument_bps:
  CARD:       {bps: TBD-VERIFY, source_url: TBD-VERIFY, as_of: TBD-VERIFY}
  UPI:        {bps: TBD-VERIFY, source_url: TBD-VERIFY, as_of: TBD-VERIFY, note: "frequently zero-rated (§3.2)"}
  NETBANKING: {bps: TBD-VERIFY, source_url: TBD-VERIFY, as_of: TBD-VERIFY}
  WALLET:     {bps: TBD-VERIFY, source_url: TBD-VERIFY, as_of: TBD-VERIFY}
  EMI:        {bps: TBD-VERIFY, source_url: TBD-VERIFY, as_of: TBD-VERIFY}
bank_charge_paise: 0         # int paise per transfer; synthetic contract term
reserve_bps:
  bps: 0                     # int; synthetic contract term for our synthetic merchant
  source_url: "synthetic"
  as_of: "2026-08-27"
  synthetic: true
  note: "A merchant's rolling-reserve percentage is private contract data. Labelled synthetic."
```

`config/solver.yaml` — every tunable in one file, with units in the key or the comment.

```yaml
search:
  epsilon_rupees: 7              # DERIVED in D6 from the itemisation model, not chosen.
  epsilon_paise_equivalent: 700  # documentary: the accumulated residue the window covers
  max_pool: 400                  # §5.5
  max_axis_width_rupees: 2000000 # deterministic memory/work cap; over this -> BUDGET_EXCEEDED
  max_enum_nodes: 200000         # deterministic backtracking cap
  enumerate_cap: 2               # §5.6: zero -> NONE_FOUND, one -> UNIQUE, two+ -> AMBIGUOUS
  require_nonempty: true         # the empty subset is never a decomposition
  wallclock_backstop_ms: 5000    # BACKSTOP ONLY. If it fires, report.py refuses to publish.
windows:
  base_days_before: 5            # [D-5, D-1]
  widened_days_before: 35        # [D-35, D-1], widened kinds only
  widened_kinds: [REFUND, CHARGEBACK, REPRESENTMENT, ADJUSTMENT, RESERVE_RELEASE]
sub_window_split:
  enabled: true
  strategy: SUFFIX_GROWING_BY_DAY
  max_attempts: 5
diagnosis:
  rate_match_tolerance_bps: 15   # how close a delta ratio must be to a configured rate
  min_rate_delta_paise: 100      # below this, a percentage match is noise
  rounding_delta_ceiling_paise: 700  # = epsilon_paise_equivalent; moves with D6, not independently
ordering_score:
  expected_max_members: 120
  terms: [slack, margin, pool, tier, cross_window, size]
  weights: uniform               # deliberately not fitted; see D14
autonomy:
  error_budget: TBD-CP6-DECLARED
  threshold: TBD-CP6-CURVE       # read off the §9.5 curve. The loader rejects a hand-set value.
  threshold_source: TBD-CP6-CURVE
```

`config/llm.yaml` — model id, effort, prompt version, per-run token budget. Credentials from the
environment, never committed. `prompt_version` is part of the cache key.

### D3 · Merchant profile

Parameterised now even though F23's three profiles are Phase 3, because retrofitting a
parameterisation onto a hardcoded generator costs more than writing it once.

```python
class MerchantProfile(BaseModel):
    name: str                                   # 'phase1'
    accounts: int                               # dev 2, test 4, devscale 4
    settlement_dates_per_horizon: int           # 40, chosen so credit counts land on §8.4's targets
    horizon_days: int                           # 60 (§8.2 stage 1)
    settlement_cycle_days: int                  # 2, i.e. T+2
    business_days_only: bool                    # True
    orders_per_day_per_account: int             # ~15; the knob for the ~18,000 item target
    instrument_mix_weights: dict[Instrument, int]   # integer weights summing to 100
    order_amount_min_paise: int                 # whole rupees only: validator asserts % 100 == 0
    order_amount_max_paise: int
    refund_rate_bps: int
    cross_window_refund_fraction_bps: int       # of refunds, how many relate to earlier windows
    dispute_rate_bps: int
    representment_rate_bps: int                 # of disputes, how many are represented
    representment_lag_days: tuple[int, int]
    adjustment_rate_bps: int
    reserve_release_lag_days: int
    fee_itemisation: Literal["PER_SETTLEMENT_INSTRUMENT", "PER_PAYMENT"]  # D6 depends on this
    subrupee_member_max: int                    # 13 for the Phase 1 profile; asserted at CP1
    counterparty_pool: Literal["A", "B"]
    corruption_range: Literal["A", "B"]
    stacked_corruptions: bool                   # False for dev, True for test
    held_out_class: CorruptionClass | None      # excluded from this profile entirely
```

Phase 1 values: `accounts` 2 (dev) / 4 (test and devscale), 40 settlement dates, 60-day horizon,
T+2, business days only, ~15 orders per day per account, whole-rupee order amounts,
`fee_itemisation: PER_SETTLEMENT_INSTRUMENT`, `subrupee_member_max: 13`. Instrument mix spreads
across all five with UPI and CARD dominant, since UPI being frequently zero-rated (§3.2) is what
makes a flat-percentage baseline fail instructively. Dev is seeds 1–3, pool A, range A, no
stacking; test is seeds 101–105, pool B, range B, stacking on; devscale is seeds 11–18, pool A,
range A, no stacking, and exists only to measure throughput (see CP6).

**Gap closed here:** §8.4 gives credit targets (~200 dev, ~800 test) and seed counts (3 and 5)
whose ratio does not match, which means credits-per-seed must differ between splits. Rather than
generating more and trimming — which orphans ledger items and would weaken Phase 2's F33
conservation identity — the `accounts` parameter differs by split and the realised counts are
whatever the scenario produces. `docs/DATA.md` records them. Rejected alternative: trimming to
exactly 800. Deterministic trimming is easy; deciding which non-member in-window distractors to
drop with it is not, and those distractors are what make the search hard.

### D4 · Corruption recipes, classes 1–23

All mutations apply to rendered views only (NN-7). "Ledger" means
`data/{split}/rendered/ledger.csv`, "bank" means `bank.csv`, "settlement" means
`settlement.csv`. Instance targets: dev at least 8 per class except the held-out class at zero;
test at least 25 per class (§8.3). Class 1 gets more than the minimum in both, as the control arm.

Classes 1–4 are **structural** — properties of the scenario rather than mutations — so they are
selected in stage 1 and 2 rather than applied in stage 3.

| # | Class | Mutation, and which view | Range A (dev) | Range B (test) |
|---|---|---|---|---|
| 1 | `CLEAN_1_1` | Structural: one payment, one credit, fee only. Control arm. | — | — |
| 2 | `AGGREGATE_N_1` | Structural: N payments net into one credit. | N in 5–25 | N in 5–60 |
| 3 | `SPLIT_1_N` | Structural: one order's proceeds settled across two credits on consecutive settlement dates. | split 50/50 | split 20/80 to 50/50 |
| 4 | `MIXED_N_M` | Structural: many payments and many refunds across many credits. | N 5–20, M 2–4 | N 5–40, M 2–8 |
| 5 | `AMOUNT_TRANSPOSE` | Swap two adjacent digits of one member amount, **ledger only**. | rupee digits, delta <= 900 rupees | rupee or paise digits, any delta |
| 6 | `DATE_SHIFT_TZ` | Shift `occurred_at` by the 5h30m IST/UTC offset so the item crosses a window edge, **ledger only**. | 1 item | up to 3 items |
| 7 | `OFF_BY_ONE_DAY` | Move the bank `value_date` off the settlement date, **bank only**. | +1 business day | ±1 or ±2 business days |
| 8 | `PARTIAL_PAYMENT` | Render an order settled short of its invoiced amount, **ledger and settlement**. | 1–5% short | 1–20% short |
| 9 | `OVERPAYMENT` | Render an excess or advance receipt, **bank only**. | 1–5% over | 1–20% over |
| 10 | `DUPLICATE_CREDIT` | Emit a second credit of identical amount, **bank only**; only one has backing. | same date, same narration | ±1 day, near-identical narration |
| 11 | `MISSING_REFUND` | Drop a refund row from **ledger** while the bank net still reflects it. | 1 refund | up to 3 refunds |
| 12 | `NETTED_FEE` | Drop fee line(s) from **ledger and settlement**; fee still deducted in the bank net. | one instrument's fee line | every fee line |
| 13 | `WITHHOLDING_GAP` | Drop the withholding line from **ledger**. | 1 | 1, stackable with 12 or 14 |
| 14 | `GST_ON_FEE_OMITTED` | Drop the `gst = fee x rate` line from **ledger and settlement**. | 1 | 1, stackable |
| 15 | `ROUNDING_RESIDUE` | Re-render fee lines with the opposite rounding rule, **ledger only**, so the ledger no longer ties at paise. | <= 10 affected members | <= 40 affected members |
| 16 | `NARRATION_TRUNCATION` | Truncate counterparty text, **bank only**, no ellipsis marker. | exactly 35 chars (§5.4) | 30–35 chars |
| 17 | `NARRATION_NOISE` | Case changes, unicode homoglyphs, doubled whitespace, abbreviation variants, **bank and ledger**. | one transform | two or three stacked |
| 18 | `SIGN_REVERSAL` | Post a debit as a credit, **ledger only**. Ingest must accept it (D1.1). | 1 item | 1–2 items |
| 19 | `CHARGEBACK_REPRESENTMENT` | Structural-plus-render: money out, then back, across window boundaries. | lag 14–21 days | lag 21–40 days |
| 20 | `PRIOR_PERIOD_ADJUSTMENT` | Add an adjustment line correcting an earlier settlement, either sign. | 1 | up to 3, chained across settlements |
| 21 | `RESERVE_HOLD_RELEASE` | Hold in one window, release in a later one. | lag = profile lag | profile lag ± jitter |
| 22 | `BANK_CHARGE` | Separate rail-fee debit, **bank only**, easily mistaken for a shortfall. | 1, same date | 2–3, one on a different date |
| 23 | `AMBIGUOUS_BY_CONSTRUCTION` | See D4.7. | injected pair sums to the swapped subset exactly | plus a second construction where the two subsets differ in size |

Classes 24, 25 and 26 do not appear in this table, in `CorruptionClass`, or anywhere in the
corpus. Their detectors (F38, F44, F29) do not exist in Phase 1, and §8.3 is explicit that a
corruption class without a detector is a hole in your own results table.

**D4.7 · Class 23, `AMBIGUOUS_BY_CONSTRUCTION`.** This is the only way to prove the uniqueness
detector works (§8.3), so the construction is specified rather than left to a heuristic.

1. Take a credit with true member set `S*` and target `T`.
2. Choose a non-empty proper subset `A ⊂ S*` consisting of exactly two whole-rupee `PAYMENT`
   members, and let `V = Σ_{i∈A} r(a_i)`, in rupee units. Require `V >= 2`.
3. Construct `B`, a set of exactly two **new** `PAYMENT` ledger items with fresh ids, fresh
   `order_id`s, dates inside the credit's base window, the same `account_id` and currency, and
   whole-rupee amounts `b_1 = floor(V/2)` and `b_2 = V - b_1` rupees. Therefore
   `Σ_{j∈B} r(b_j) = V = Σ_{i∈A} r(a_i)` **exactly**, with no reliance on tolerance.
4. Add `B`'s rows to the rendered **ledger** view. Do not touch `truth.jsonl`: the true member
   set for this credit remains `S*`, and `S** = (S* \ A) ∪ B` is a second arithmetically valid
   explanation the solver must find.
5. Assert distinctness in the generator, three ways: `B ∩ S* = ∅` by id construction;
   `|S** Δ S*| = |A| + |B| = 4 >= 3`; and no member of `B` shares an `order_id` with a member of
   `A`, so the two subsets are not the same economic event wearing two ids.
6. The generator does **not** call the solver to confirm ambiguity — that would couple the
   answer key to the system under test. `tests/test_uniqueness.py` verifies that the solver
   reports `AMBIGUOUS` on every class-23 credit, and that no class-23 credit is ever cleared.
   That test is the actual proof, and it belongs on the system side of the boundary.

Because both subsets have equal rupee sums by construction, the ambiguity does not depend on
`ε` and cannot be tuned away — which is what makes the class a real probe rather than an
artefact of the tolerance.

**D4.8 · The held-out class.** §8.4 requires one class held out of dev entirely as a
generalisation probe. Criteria: it must not be structural (classes 1–4 are load-bearing for
everything), no other class's construction may depend on it, it must not be required to prove
any Phase 1 feature, and its delta structure must be one nothing tuned on dev has seen. Class 9
`OVERPAYMENT` satisfies all four: it is the only class where the bank credit **exceeds** the true
settlement rather than the ledger being incomplete, so no dev-tuned diagnosis rule has been
fitted to it. The choice is recorded in `docs/EVALUATION.md` at CP2, before the test split is
generated, and must not be revisited after CP9's evaluation. The honest expected result, per
§8.4, is that the system clears nothing incorrectly on it and routes everything to exceptions.

**D4.9 · Recording class application without leaking it.** Applied class ids go into the
`TruthRecord` written to `data/{split}/truth.jsonl`, which sits outside the `SourceRoot` the
loader can reach (D5, NN-6). No rendered view carries a column derived from the class, and
`tests/test_no_leakage.py::test_rendered_views_carry_no_class_labels` asserts no column
correlates one-to-one with an applied class. `eval/` reads the labels for the §9.3 table;
`src/` cannot.

### D5 · Candidate generation

Restated from §5.5: same `account_id` and currency; base window `[D-5, D-1]`; widened to
`[D-35, D-1]` only for `REFUND`, `CHARGEBACK`, `REPRESENTMENT`, `ADJUSTMENT`,
`RESERVE_RELEASE`; sort by `(occurred_at, id)`; `MAX_POOL = 400`; no truncation, ever (NN-11).

**Sub-window split strategy — Gap closed here.** §5.5 says to split by sub-window and attempt
each without saying how. Strategy `SUFFIX_GROWING_BY_DAY`: partition base-window items by day
and attempt `[D-1, D-1]`, then `[D-2, D-1]`, up to `[D-5, D-1]`, **always retaining every
widened-kind item** in every attempt, since dropping cross-window items is what makes
cross-window cases unsolvable in the first place. Attempts run in that fixed order and stop at
the first `UNIQUE`. Every attempt is marked `PoolScope.REDUCED`.

**And a reduced-pool `UNIQUE` does not auto-clear.** A solution found on a strict subset of the
pool was never shown to be unique over the full pool: a second explanation could use exactly the
items the split excluded. Auto-clear therefore requires `pool_scope == FULL`, and a reduced
`UNIQUE` is presented as a `BUDGET_EXCEEDED` exception with the proposed decomposition attached
as a suggestion for the human. See §0.3 for what this costs if the decision is wrong. Rejected
alternative: clearing on the reduced pool. That is the confidently-wrong outcome NN-11 exists to
prevent, arriving through a door opened to reduce it.

**The deterministic budget.** `MAX_POOL` on pool size, `MAX_AXIS_WIDTH_RUPEES` on
`POS - NEG + 1`, `MAX_ENUM_NODES` on backtracking work. All three are pure functions of the
instance, so `BUDGET_EXCEEDED` is reproducible and NN-9 survives. The wall-clock setting is a
backstop whose firing makes `report.py` refuse to publish the run; see §0.4.

### D6 · The rounding bridge

The search axis is rupee-granular and verification is paise-exact (§5.6, NN-12). This is the
subtlest thing in the phase, so it is worked rather than asserted.

**The rounding map.** `r(a) = (a + 50) // 100`, computed with integer floor division, so no float
touches it (NN-1). Because Python's `//` floors toward negative infinity, this is round-half
toward `+inf` uniformly across both signs: `r(150) = 2`, `r(-150) = -1`, `r(-151) = -2`.
Rejected alternatives: floor (`a // 100`) and truncation-toward-zero. Both have per-item error in
a unit-width interval rather than a half-width one, giving a bound twice as large, and truncation
is additionally sign-asymmetric, which interacts badly with signed amounts.

**The reachability argument.** Let `S*` be the true member set of a credit with target `T` paise.
Ground truth is exact at paise by construction in generator stage 2:

```
    Σ_{i ∈ S*} a_i  =  T                                                        (1)
```

Define the rational rounding error of each item and of the target:

```
    δ_i := r(a_i) − a_i/100 ,      δ_T := r(T) − T/100
```

Then `|δ_i| ≤ 1/2` and `|δ_T| ≤ 1/2`, and — this is the load-bearing observation —
`δ_i = 0` exactly whenever `a_i ≡ 0 (mod 100)`, because a whole-rupee amount is mapped without
error. Now:

```
    Σ_{i ∈ S*} r(a_i) − r(T)
      = Σ_{i ∈ S*} (a_i/100 + δ_i)  −  (T/100 + δ_T)
      = (1/100) · ( Σ_{i ∈ S*} a_i − T )  +  Σ_{i ∈ S*} δ_i  −  δ_T
      = 0  +  Σ_{i ∈ S*} δ_i  −  δ_T                                     by (1)
```

Let `m := |{ i ∈ S* : a_i mod 100 ≠ 0 }|`, the number of **sub-rupee** members. Taking absolute
values and using `δ_i = 0` for the other members:

```
    | Σ_{i ∈ S*} r(a_i) − r(T) |  ≤  Σ_{i ∈ S*} |δ_i| + |δ_T|  ≤  m/2 + 1/2  =  (m + 1) / 2
```

The left-hand side is an integer, so the bound tightens to `floor((m + 1) / 2)`. Therefore:

> **The true member set is reachable inside the search window if and only if
> `ε_R ≥ floor((m + 1) / 2)` rupee units.**

**As a function of member count.** In the worst case every member is sub-rupee, `m = n`, and the
accumulated error is `floor((n + 1) / 2)` — linear in member count. In the typical case the `δ_i`
are approximately independent and uniform on `[-1/2, 1/2]`, so `Var(Σδ) = m/12` and the
accumulated error grows as `≈ 0.29·√m` — which is exactly why F32's fitted form is
`ε(n) = ceil(k·√n)` rather than linear. Phase 1 uses the worst-case bound because it has no
fitted distribution yet; F32 replaces it with the measured one.

**The flat ε cannot cover the worst case at `MAX_POOL` member counts, and I am saying so rather
than widening it.** At `n = 400` all-sub-rupee, the bound demands `ε_R ≥ 200` rupees. A 200-rupee
window is unusable: the count of subsets summing into a window grows roughly linearly in its
width, so essentially every credit would return `AMBIGUOUS` and coverage would collapse. So the
flat `ε` is not set from the worst case over `MAX_POOL`; it is set from the worst case over the
**data model**, which is a quantity the generator controls.

**The lever is fee itemisation, which makes this a correctness decision rather than a rendering
one.** The Phase 1 profile emits fee and GST aggregated per `(settlement, instrument)` and
withholding, reserve and bank charge once per settlement, while payments, refunds, chargebacks
and adjustments are whole-rupee by construction. So

```
    m  ≤  2 × |instruments|  +  3  =  2 × 5 + 3  =  13        and       ε_R = floor(14 / 2) = 7
```

`ε_R = 7` rupee units is therefore **derived** from the itemisation model rather than chosen —
which is a better position than §6.2's F32 gate assumes Phase 1 will be in. `subrupee_member_max`
is a profile field and `tests/test_generator.py::test_subrupee_member_count_within_design_bound`
asserts it at CP1, before CP3 fixes `ε`. If the profile ever switches to `PER_PAYMENT` fee
itemisation, `m` grows with payment count, `ε_R = 7` stops covering large decompositions, and
those credits land in `NONE_FOUND` — see §0.2 for the blast radius.

**What each direction of error costs, and why neither costs correctness.** `ε` too small: the
true set falls outside the window, the credit returns `NONE_FOUND`, the near-miss delta is small,
and the classifier routes it to `ROUNDING_RESIDUE`. Lost coverage. `ε` too large: more reachable
totals fall in the window, more subsets are enumerated, and more credits return `AMBIGUOUS`. Also
lost coverage, plus enumeration cost. **Neither direction can produce a wrong clear**, because
NN-12 keeps the verifier at a zero paise residual re-derived from the rate table. That asymmetry
is the reason a bound that is approximately right is safe, and it is worth one sentence in the
README.

**One scope note the executor will need.** The argument above establishes reachability of the
true set on *faithfully rendered* data. Corruptions that deliberately perturb a member's rendered
amount — class 5 `AMOUNT_TRANSPOSE`, class 15 `ROUNDING_RESIDUE` — break identity (1) on the
rendered data on purpose. Those credits are *supposed* to fail verification and land in
exceptions; they are not evidence that the bridge is wrong.

### D7 · Flat tolerance ε for Phase 1

`ε_R = 7` rupee units, equivalently a documented accumulated residue of up to 700 paise, derived
in D6 from `subrupee_member_max = 13`. Labelled **provisional** in `config/solver.yaml` and in
the README, and superseded by F32 in Phase 3, which fits `ε(n) = ceil(k·√n)` paise from the
measured residual distribution of correctly decomposed dev credits and then opens a window of
`ceil(ε(n)/100)` rupees on the search axis.

Per NN-12, none of this touches the verifier. `ε` widens what the search *considers*; the
verifier demands a zero paise residual either way, because it re-derives each member's rounding
rather than tolerating it. A derived tolerance that leaked into the acceptance test would undo
§5.7 and turn §5.12's auto-clear condition into a threshold on top of a fudge factor.

### D8 · Solver module split

**What moves where.** From `solver.py`: the `NEG`/`POS` computation, the bounds guard, the
reachability loop, the snapshot list, `_bit`, and `_nearest_reachable` become the private
internals of `ReachabilityIndex` in `bitset_dp.py`. `_backtrack` and the
solution-count-to-uniqueness mapping become `enumerate_solutions` and `solve_search` in
`enumerate.py`. `Uniqueness` moves to `models.py` so the enum has one home. Regime A is new code
in `fastpath.py`. `solver/__init__.py` re-exports `solve_search`, `verify_declared`,
`ReachabilityIndex` and `SolveResult`, and nothing else.

**Where the NN-10 bounds guard lives so it cannot be bypassed.** Inside `ReachabilityIndex`.
The mask and the snapshot list are private attributes with no public accessor; the only bit tests
are `is_reachable` and `was_reachable_at`, and both range-check against `[NEG, POS]` before
shifting. A future caller cannot reach a raw mask to test a bit carelessly, because there is no
API that returns one. `tests/test_solver_properties.py::test_no_public_raw_bitmask` asserts it.

**Snapshot retention and the memory ceiling.** Full snapshots, one per prefix, exactly as the
reference does. Memory is `(n + 1) · axis_width / 8` bytes, since each `|=` produces a new
arbitrary-precision int of about `axis_width` bits and the list holds a reference to each. At
`MAX_POOL = 400` and `MAX_AXIS_WIDTH_RUPEES = 2,000,000` that is bounded at roughly 100 MB, which
is why the axis cap exists at all and why exceeding it returns `BUDGET_EXCEEDED` rather than
swapping. `ReachabilityIndex.memory_bytes()` reports it into the audit metrics channel so it is
observed rather than assumed. §12's documented fallback if it bites is to recompute forward
instead of snapshotting and accept the constant factor; do not invent a third option.

**The enumeration cap and the mapping to uniqueness.** Cap 2, per §5.6. Zero solutions →
`NONE_FOUND`. Exactly one → `UNIQUE`, eligible for verification. Two or more → `AMBIGUOUS`, and we
refuse. A deterministic cap hit → `BUDGET_EXCEEDED`.

**And the correction from §0.1.** The count is taken across **every** reachable total in
`[r(T) − ε, r(T) + ε]`, walked in ascending order, into one shared solution list with one shared
cap — not within a single "best" total as the reference does. Two subsets that both sum to `T`
exactly at paise can land on different rupee totals because they accumulate different rounding
residues (D6), so assessing uniqueness within one total can report `UNIQUE` for a credit that has
two genuine explanations. The empty subset is excluded, since a credit smaller than `ε·100` paise
would otherwise be "explained" by nothing at all.

**The near-miss search that feeds diagnosis.** `nearest_reachable(target)` searches outward from
the target by increasing distance `d = 1, 2, …`, testing `target − d` then `target + d`, and
returns the first reachable total, or `None` if the whole axis is empty of one. "Nearest" is
therefore defined by absolute rupee distance with ties broken toward the lower total, which is a
fixed rule and so deterministic. Its delta is the primary input to the D13 decision table, and
`SolveResult` also carries `margin_rupees` — the distance from the matched total to the nearest
*other* reachable total — which is an `ordering_score` term (D14) and is free to compute from the
same mask.

**The one internal retry, and why it is not a pipeline retry.** When the full pool is over cap,
`solve_search` runs at most `sub_window_split.max_attempts` internal attempts. This is a bounded
deterministic loop inside one stage; the pipeline still sees a single solver invocation, so the
DAG stays acyclic. §5.1 and NN-5 permit exactly one forward-branching edge — fail-or-ambiguous
into diagnosis — and it must remain the only one.

---
### D9 · Regime A fast path, and what makes it independent

§5.6 requires the fast path to re-derive every declared line rather than restate it. The test of
whether it does is simple: if it recomputes a line from the declared fee, it is verifying
nothing. So the order is fixed, and the declared amounts are treated as *claims to be checked*
rather than as inputs.

1. Read the declared composition from the settlement report view. Keep the declared amounts in a
   separate structure from the recomputed ones; they never feed a computation.
2. For each declared payment, look up the internal-ledger item by id. Assert the amount and the
   instrument match. A declared line with no ledger counterpart goes to `missing_item_ids`.
3. Recompute `fee_paise` per payment from `(instrument, amount_paise)` and `fees.yaml`, using
   `money.apply_bps`. **The declared fee is not read at this step.**
4. Recompute `gst_paise` from the **recomputed** fee and `tax_rates.gst_on_fee`. This ordering is
   what stops a wrong declared fee from propagating into a matching wrong GST, which is the
   specific way a naive fast path passes a corrupted report.
5. Recompute withholding from the applicable base and `tax_rates.withholding`.
6. Recompute the reserve hold as `apply_bps(selected_gross, reserve_bps)`.
7. Refunds, chargebacks, representments, adjustments and bank charges are not rate-derived, so
   they are verified by existence and amount against the internal ledger by id.
8. Sum every recomputed signed line and compare to `BankCredit.amount_paise`. A zero residual is
   required.
9. Any declared line differing from its recomputed counterpart is recorded in `line_deltas`,
   which is what gives `RATE_MISMATCH` a real detection rule rather than an aspirational one.

`tests/test_fastpath.py::test_fee_is_recomputed_not_copied` is the test that keeps this honest:
corrupting the declared fee must change `line_deltas` and leave `computed_total_paise` alone.

### D10 · The verifier

**Re-derivation order at paise.** Identical to D9 steps 3–8, applied to the searched member set
(Regime B) or the declared set (Regime A). Same functions, same rate tables, same rounding —
sharing the code is deliberate, because two implementations of the deduction stack would
eventually disagree and the disagreement would look like a data defect.

**Per-line rounding rule.** `money.round_half_up_div` on every derived line, applied once, at the
line level, never to a running total. Rounding a total instead of each line is how a spreadsheet
drifts, and reproducing that drift would be a defect rather than realism.

**The exact condition for accept.** All of: `residual_paise == 0`; `mismatched_line_ids` empty,
meaning every rate-derived member equals its independently recomputed value at paise; the member
set is non-empty; and every member id resolves to a real ledger item. Note what is *not* in that
list: uniqueness, pool scope, and the ordering score. Those are conditions on the **disposition**,
not on the arithmetic, and keeping them separate is what lets §9.6's ablations move one at a time.

**The disposition rule, stated once so it lives in one place.** `CLEARED` requires verifier
acceptance **and** `uniqueness == UNIQUE` **and** `pool_scope == FULL` **and**
`ordering_score >= threshold` (§5.12). `BUDGET_EXCEEDED` when the solver returned it or the pool
scope is reduced. `FLAGGED` otherwise. There is no fourth outcome and no silent pass, and
`tests/test_verify.py` asserts the three dispositions partition every credit.

**Sole write access, at the connection level and visible in code.** `db.TABLE_OWNERS` is a
literal mapping three owners to three disjoint table sets: `verify` owns the reconciliation
tables, `audit` owns the audit chain, `exceptions` owns the queue and its resolutions.
`_open_readwrite` is module-private and raises on an unknown owner; everything else in the system
receives a `mode=ro` URI connection on which SQLite itself rejects writes. §5.12 asks for
enforcement rather than convention, and "the verifier is the only writer" is precise about the
reconciliation ledger specifically — the audit log and the exception queue have their own owners,
which is worth stating rather than leaving as an apparent contradiction.

### D11 · Audit chain canonical serialisation

Pinned exactly, because two implementations of "canonical JSON" that differ by one space produce
a chain that fails to verify on another machine, and that failure is indistinguishable from
tampering.

```python
json.dumps(payload, sort_keys=True, separators=(",", ":"),
           ensure_ascii=False, allow_nan=False).encode("utf-8")
```

- **Key ordering:** `sort_keys=True`, byte-order on the UTF-8 key bytes.
- **Separators:** `(",", ":")`, no whitespace anywhere.
- **Unicode:** `ensure_ascii=False`, and every string value is NFC-normalised before
  serialisation. NFKC is the *narration* normalisation (§5.4) and is a different thing; using
  NFKC here would silently alter values.
- **Integers:** JSON integers. Money is `int` paise, so this is exact and no precision question
  arises.
- **Floats:** forbidden. `allow_nan=False` plus an explicit type check that raises on any float in
  the payload. `ordering_score` enters as its fixed six-decimal string (D1.3).
- **Datetimes:** `tz.iso_utc`, always `+00:00`, always six microsecond digits.
- **Payload contents:** input snapshot digest, solver regime, pool size, pool scope, alternates
  found, ordering-score string, verifier outcome, whether a model was called and with which cache
  key, `rate_config_digest`, and the final disposition (§5.8).
- **Metrics, hashed by nothing:** wall time, solve time, peak snapshot bytes, token counts. §5.8
  asks for wall time in the log; putting it in the hashed payload would make `make reproduce`
  fail for reasons unrelated to decision determinism, so it lives in a sibling `metrics` field
  that the chain does not cover and the report diff ignores. **Gap closed here.**
- **Chaining:** `entry_hash = sha256(canonical_json(payload) + b"\x00" + prev_hash.encode("ascii")).hexdigest()`,
  lowercase hex, `prev_hash` as its 64-character hex string rather than raw bytes. Genesis
  `prev_hash` is 64 `"0"` characters.
- **`make verify-audit`** walks from genesis, recomputes each hash, and reports the sequence
  number of the first break plus the current head hash.

### D12 · The semantic cascade

Restated from §5.9, with the tunables and the mechanisms made explicit.

| Tier | What resolves | Model? |
|---|---|---|
| 1 | Exact match of `narration_norm` against the entity registry | No |
| 2 | UTR or reference-token match | No |
| 3 | `rapidfuzz` similarity above `fuzzy_threshold` **and** a top-two margin above `fuzzy_margin` | No |
| 4 | Model selects from a closed shortlist of `shortlist_size` candidates | Yes |
| 5 | Abstention, or a response outside the shortlist, or a schema failure | Exception |

**Tunables and their dev-tuning procedure.** `fuzzy_threshold`, `fuzzy_margin` and
`shortlist_size`. Sweep `fuzzy_threshold` over an integer grid on dev, computing tier-3
resolution precision and coverage against dev truth at each point, and write the curve to
`artifacts/dev/tier3_threshold_curve.json`. Choose the threshold at the knee where precision
first falls below a **declared** entity-resolution error budget, recorded in
`docs/EVALUATION.md` alongside the number chosen — the same ethos as §9.5's derived autonomy
threshold, and for the same reason. The margin exists because a top-1 score above threshold with
a near-identical top-2 is not a resolution; it is a coin flip that should fall through to tier 4.

**The structured output schema, and the mechanism that makes NN-3 true rather than intended.**
The payload type is the mechanism. `EntityResolutionRequest` has three fields — two strings and a
tuple of `CandidateEntity`, itself two strings — and `extra="forbid"`. **There is no numeric
field at any nesting depth**, so an amount cannot be included even by a careless caller, and
`tests/test_no_amounts_to_model.py::test_request_types_have_no_numeric_fields` walks the model's
field tree to assert it. Belt and braces: `assert_no_amounts` scans the serialised payload for
money-shaped literals (`\d[\d,]*\.\d{2}` and `(₹|Rs\.?|INR)\s*\d`) and raises `AmountLeakError`.
The pattern is deliberately narrow — it must not fire on a UTR or an invoice number, both of
which are legitimate content and both of which are digit runs.

**The closed candidate set.** Built deterministically: the top `shortlist_size` registry entries
by `rapidfuzz` score against `counterparty_raw`, sorted by `(-score, entity_id)`. The response
validator rejects any `selected_id` outside that set, so the model cannot introduce an entity and
free text can never reach the ledger.

**Structured output.** The provider call requests a schema-validated object and the result is
parsed into `EntityResolutionResponse`; a validation failure is an exception, never a retry loop
that eventually gets lucky (§5.12). Effort is set low in `config/llm.yaml` — this is a
closed-set selection over two short strings, not a reasoning task — and `max_tokens` is small.

**The cache key.** `sha256(canonical_json({"prompt_version": int, "model_id": str, "request":
request.model_dump()}))`, stored at `data/cache/llm/{key}.json`. `prompt_version` is in the key so
that editing a prompt without bumping it cannot serve a stale answer. In `--offline` mode a miss
raises rather than calling out, which is what makes `make eval` reproducible and turns a provider
outage into a cache hit (§5.9, §12).

**The abstain path.** `selected_id: None` is a valid, non-failing response. It routes the item to
`ENTITY_UNRESOLVED`, which annihilates the ordering score (D14) and therefore guarantees the
credit cannot auto-clear. An abstention is a good outcome and is counted as tier 5, not as a
failure.

**Published as a cascade.** `tier_mix` is F6's owed number. The honest expected shape — tiers 1–3
carrying the overwhelming majority and the model a thin, hard slice — *is* the AI-judgment
answer (§5.9); it is not a disappointing result to be dressed up.

### D13 · Exception classification as a deterministic decision table

Eleven classes (§5.10), assigned by rule from the near-miss delta structure. The model writes
narrative only and never assigns the class.

**Which delta the rules read. Gap closed here** — §5.10 assumes a near-miss delta exists, which
is true only when the search found nothing. The unified rule: `delta` is
`nearest_delta_paise` when the solver returned `NONE_FOUND`, and `verifier_residual_paise` when
the solver returned a member set the verifier rejected. `ExceptionSignals` carries both, and the
classifier reads whichever is populated. If neither is (an `AMBIGUOUS` or `BUDGET_EXCEEDED`
outcome), only rules 1–4 can fire, and they are ordered first for exactly that reason.

Rules are evaluated in this order and **the first match wins**:

| # | Class | Rule |
|---|---|---|
| 1 | `BUDGET_EXCEEDED` | `uniqueness == BUDGET_EXCEEDED` or `pool_scope == REDUCED`. First, because we genuinely did not finish the search and no other diagnosis is honest. |
| 2 | `AMBIGUOUS_DECOMPOSITION` | `uniqueness == AMBIGUOUS`. |
| 3 | `ENTITY_UNRESOLVED` | `unresolved_entity_count > 0`. Before the delta rules, because an unresolved entity plausibly means the pool itself is wrong and a delta computed over a wrong pool should not be diagnosed. |
| 4 | `DUPLICATE_CREDIT` | Another credit in the batch shares `(account_id, amount_paise)` with `value_date` within one day, and at most one of the two has a `UNIQUE` decomposition. |
| 5 | `RATE_MISMATCH` | Regime A, `declared_line_deltas` non-empty, and the residual is fully explained by those deltas. |
| 6 | `SIGN_REVERSAL` | `delta == -2 * a_j` for exactly one pool member `a_j`. A debit posted as a credit moves the sum by twice its amount, which is an exact arithmetic signature rather than a heuristic. |
| 7 | `CROSS_WINDOW_UNRESOLVED` | Some ledger item for the same account **outside** the candidate window has an amount equal to `delta`. Before `MISSING_RECORD`, because the record is not missing — the window excluded it. |
| 8 | `MISSING_RECORD` | `abs(delta)` equals the amount of exactly one **in-pool** member, implicating a duplicated or absent record (§5.6). |
| 9 | `ROUNDING_RESIDUE` | `abs(delta) <= rounding_delta_ceiling_paise`. Before the percentage rules, and the percentage rules additionally require `abs(delta) > rounding_delta_ceiling_paise`, so the two can never overlap. |
| 10 | `SUSPECTED_WITHHOLDING` | `abs(delta) > ceiling`, `abs(delta) >= min_rate_delta_paise`, and `delta / pool_gross` within `rate_match_tolerance_bps` of a rate in `tax_rates.yaml`. |
| 11 | `UNITEMISED_FEE` | Same shape, against a per-instrument rate in `fees.yaml`, weighted by the pool's instrument mix. |
| — | fallback | `MISSING_RECORD` with `rule_matched = False`. By elimination, an unexplained delta with no rate-shaped and no member-shaped signature means information absent from the inputs. |

**Tie-break between 10 and 11**, the only pair that can both match: prefer the smaller relative
error between `delta / pool_gross` and the configured rate; if those are exactly equal, prefer
`SUSPECTED_WITHHOLDING`. Stated so it is not decided by dict ordering.

**The fallback is flagged, not hidden.** `Classification.rule_matched` is `False` when the
fallback fires, and the §9.3 per-class table reports the fallback fraction. A classifier whose
fallback carries most of the traffic is a classifier that is not working, and that should be
visible in our own results rather than discovered by a reviewer. There is no twelfth class:
§5.10's list is closed and the executor should not invent an `OTHER`.

**The narrative.** `narrate` sends the class, qualitative facts and **slot names** to the model
and substitutes pre-rendered figures into the returned prose (§0.5). A money-shaped literal in
the response rejects it and the deterministic template is used instead. So NN-3 holds for
narration, and the class — a closed-set classification with crisp arithmetic rules — stays
deterministic, exactly as §5.10 demands.

### D14 · `ordering_score`

Observable quantities only (NN-4). Six terms, each normalised to `[0, 1]` with higher meaning
safer, combined as an **unweighted geometric mean**:

```
score = ( s_slack · s_margin · s_pool · s_tier · s_xwin · s_size ) ** (1/6)
```

| Term | Definition | Why it should carry signal |
|---|---|---|
| `s_slack` | `1 − min(1, slack_rupees / (ε_R + 1))` where `slack = abs(matched_total − r(T))` | A decomposition that hit the target exactly on the rupee axis needed none of the tolerance window; one that needed all of it is closer to the edge of being a coincidence. |
| `s_margin` | `min(1, margin_rupees / (ε_R + 1))` | Distance from the matched total to the nearest *other* reachable total. A solution isolated on the axis is robustly unique; one adjacent to another reachable sum is one paise of noise away from ambiguity. |
| `s_pool` | `1 − min(1, pool_size / MAX_POOL)` | More candidates means more chances that some unrelated subset sums to the target coincidentally. |
| `s_tier` | `1.0` all members at tiers 1–2; `0.7` if tier 3 used; `0.4` if tier 4 used; `0.0` if any member is unresolved | The tier reached is observable and is not a confidence. |
| `s_xwin` | `1 − min(1, cross_window_members / max(1, member_count))` | §3.2 and §5.5 both name cross-window components as the documented hard case. |
| `s_size` | `1 − min(1, member_count / expected_max_members)` | Larger member sets accumulate more rounding residue (D6) and admit more coincidental subsets. |

**Geometric rather than arithmetic, on purpose.** A safety score should be conjunctive: one bad
term should not be compensated by five good ones. The most important consequence is that
`s_tier = 0` on an unresolved entity drives the score to exactly zero, so such a credit can never
auto-clear whatever the threshold is. That annihilation is a feature and
`tests/test_ordering_score.py::test_unresolved_entity_annihilates_the_score` asserts it.

**Weights are uniform, deliberately.** Fitting six weights on a dev corpus of a few hundred
credits would overfit, and the curve's *shape* is what §9.5 uses, not the score's calibration.
Recorded as a decision in `docs/DECISIONS.md` rather than left as an omission.

**The threshold is not set here.** It is read off the §9.5 risk-coverage curve at CP6 at a
declared error budget, and `config.load_solver_config` rejects a hand-set `autonomy.threshold`
that does not carry a `threshold_source` pointing at a curve artifact. A hand-picked threshold is
a guess wearing a suit.

### D15 · The four arms, plus the human reference

**D15.1 · A0 exact match.** For each credit, find ledger items in `[D-5, D-1]` on the same
account and currency whose `amount_paise` equals the credit's exactly. Predict that single item
if there is exactly one; otherwise predict nothing. No exception path and no budget path, so both
cells are `NA`. A0's value is diagnostic: its score tells the reviewer what fraction of the batch
is genuinely trivial, and therefore how much real work the other arms are doing (§9.1).

**D15.2 · A1 fuzzy 1:1, optimally assigned.** Build a cost matrix over eligible (credit, item)
pairs — same account, same currency, item inside `[D-5, D-1]`, `abs(amount_diff) <= amount_tol`:

```
cost = w_sim · (1 − rapidfuzz.normalized_similarity(credit.narration_norm, item.narration_norm)/100)
     + w_amt · min(1, abs(amount_diff) / amount_tol)
```

Ineligible pairs receive a large finite sentinel, the matrix is padded to square, and the
assignment is solved with `scipy.optimize.linear_sum_assignment` — **optimal, not greedy**, per
§9.1. Assignments on sentinel cells, or with similarity below `A1_SIM_THRESHOLD`, are dropped
afterwards. Each credit ends with at most one item, which is the point: this arm is what most
competitors' entire submission is equivalent to, and it structurally cannot express a net
aggregate.

**D15.3 · A2 rules-only.** Full deduction-stack arithmetic — the same recomputation code the
verifier uses, the same `tax_rates.yaml` and `fees.yaml` — plus largest-first greedy subset
selection over the **same** pool `candidates.build_pool` gives A3, including the asymmetric
cross-window widening. Greedy: sort by descending `abs(amount)`, take an item whenever it reduces
`abs(running_sum − target)`, stop when inside tolerance, clear on the first subset found. No exact
solver and no uniqueness check, because those two things are what A2 exists to measure. It
inherits the `MAX_POOL` budget path, which is why its budget-exceeded cell is a number and not a
dash.

**D15.4 · A3 full system.** Everything in §5. First measured at CP6, after all three baselines
exist (NN-13).

**D15.5 · A4 human.** F19 and F56, at CP5, per D18. Reported as time per credit and accuracy
rather than coverage, since a human clears everything they attempt (§9.1).

**The fairness sentence for the README**, to be used verbatim so that fairness is documented
rather than asserted:

> A1's similarity threshold and amount tolerance were swept on the dev split and fixed at the
> values that maximised A1's own exact-decomposition rate. A2 was given the same tax and fee
> configuration, the same asymmetric cross-window widening, and the same normalisation pipeline
> and candidate pools as A3; the only things it lacks are the exact solver and the uniqueness
> check, which are the two components it exists to measure. Both sweeps are recorded in
> `docs/EVALUATION.md`. No baseline parameter was chosen to make A3 look better.

### D16 · Metric implementations

All defined over sets of `(credit_id, item_id)` pairs or over dispositions, and computed as exact
`Fraction`s so that a published number is never a float artifact.

| Metric | Formula |
|---|---|
| assignment precision | `abs(pred ∩ truth) / abs(pred)`, over pair sets |
| assignment recall | `abs(pred ∩ truth) / abs(truth)` |
| exact decomposition rate | `abs({c : pred_members(c) == truth_members(c)}) / n_credits`; an unpredicted credit is not exact |
| auto-clear coverage | `n_cleared / n_credits` |
| auto-clear error rate | `n_cleared_wrong / n_cleared`, and **`NA` when `n_cleared == 0`** — never 0 |
| exception precision | `abs({c ∈ flagged : genuinely_required_human(c)}) / abs(flagged)` |
| residual distribution | median and p95 of `abs(residual_paise)` among non-cleared credits, plus the same as integer basis points of credit value |
| throughput | credits per minute and total wall clock, with the machine named |
| cost | total tokens, total paise, paise per credit, cache hit rate |

Every one of these is computed separately for Regime A and Regime B, and pooled (§9.2, §3.3).

**Dash versus zero is a data-structure distinction, not a formatting one.** `NA` is a sentinel
type; arithmetic on it raises rather than coercing. A0 and A1 have no exception path, so their
exception and budget cells hold `NA` and render `—`. An arm that clears nothing holds `NA` for
error rate, because zero errors out of zero clears is not a zero error rate.

**The two `report.py` assertions, in integer form.** Comparing floats here would be its own small
sloppiness, and the integer forms are exact:

1. `assert_dispositions_sum_to_one`: for any arm whose three disposition cells are all populated,
   `n_cleared + n_flagged + n_budget_exceeded == n_credits`. Arms with `NA` cells are skipped
   rather than coerced.
2. `assert_exact_bounded_by_coverage`: for any arm with **no** exception path,
   `n_exact <= n_cleared_correct` — the exact integer form of `exact <= coverage × (1 − error)`.
   A3 is exempt, because a credit A3 *flagged* can still carry a correct member set, which is
   precisely why §9.8 says A3 is not capped that way.

Both run before `render_report` writes anything, so an impossible table cannot be published. The
three §6.2 hour identities are additionally asserted in `tests/test_plan_arithmetic.py`, per
§9.8's aside about checking the plan's own arithmetic.

### D17 · Statistics

**Pooled proportion with a Wilson score interval**, `z = 1.959963984540054` for 95%. Wilson
because the most important number in the project — auto-clear error rate — lives near zero, where
the normal approximation misbehaves (§9.4).

**Per-seed figures as a min–max range beside it, never as an interval around it.** The mechanism
that prevents the §9.4 sloppiness is structural: `ProportionEstimate` carries `pooled`,
`wilson_lo`, `wilson_hi`, `per_seed`, `seed_min` and `seed_max` as separate fields, and there is
**no method or property that combines the Wilson bounds with the per-seed spread**.
`tests/test_stats.py::test_no_api_returns_pooled_plus_seed_spread` asserts that by inspection, so
producing the wrong artifact would require writing new code rather than misusing existing code.
Two sanity assertions run on every estimate: `wilson_lo <= pooled <= wilson_hi`, and
`seed_min <= pooled <= seed_max` (which holds because the pooled proportion is a weighted mean of
the per-seed proportions).

**The small-sample justification is computed, not quoted.** `wilson_at_n50_example()` computes the
interval at the brief's floor so the README's batch-size argument is reproduced by code rather
than copied out of §9.4. That matters because §9.4's stated interval is itself an illustration,
and NN-15 applies to it like everything else.

**Cohen's κ** is pairwise by construction, so with three raters we report all three pairwise
values and their mean, and say that is what we did. Fleiss' κ would be the joint statistic; §9.8
asks for Cohen's, so we report Cohen's and name the choice rather than silently substituting.

### D18 · F19 and F56 protocol

Both run at CP5 and neither can run later. Once you know the system's answers an honest human
baseline no longer exists, and that applies to briefing raters as much as to reconciling yourself
(§6.1, §6.2, §11 Day 5). F56 is in the NN-21 protected set.

**Which 20 credits, and how selected.** From the **dev** split — using test credits here would
spend part of the NN-16 budget on a human study and contaminate the split. Selection is
deterministic and stratified, recorded to `artifacts/human_study/selected_credits.json` **before
any rater sees anything**: sort dev credits by `(seed, account_id, value_date, credit_id)`, then
take a stratified sample that includes at least 2 class-23 credits, at least 2 class-4, at least 2
class-1, at least 1 Regime A, and spreads the remainder across the classes present, breaking ties
by the sort key. The selection script is committed, so the sample is reproducible and visibly not
cherry-picked.

**What raters see.** The three rendered source views for the credit's account over a ±40 day
window; `config/tax_rates.yaml` and `config/fees.yaml`; and a one-page primer on the deduction
stack drawn from §3.2. That is the same information the system gets, which is what makes the
comparison fair.

**What raters must not see.** `truth.jsonl`; any system output; any proof block; the corruption
class labels; the ordering score; the selection strategy; and each other's sheets. Raters work
independently and do not discuss cases until all sheets are sealed.

**Stopwatch protocol.** Credits are worked in the given order. Start the clock when the credit's
views are opened and stop it when the disposition is written. Breaks are recorded and excluded
from elapsed time. Elapsed time is recorded per credit, not as a single total, so per-credit
distribution is available and not just a mean.

**Recording sheet**, one row per credit, `artifacts/human_study/rater_{n}.csv`:

```
credit_id, disposition, member_ids, elapsed_seconds, confusion_note
```

**Disposition vocabulary**, deliberately three categories that map onto the system's three
terminal dispositions so κ is computed over a comparable scale:

| Rater says | Meaning | Maps to |
|---|---|---|
| `CLEARED` | "I can name the exact member set" | `CLEARED` |
| `FLAGGED` | "This needs more information or a judgment call" | `FLAGGED` |
| `GAVE_UP` | "I could not finish this in a reasonable time" | `BUDGET_EXCEEDED` |

**Scoring.** After all sheets are sealed, the scorer opens truth and computes per-rater
exact-decomposition rate over the 20, per-rater total and per-credit elapsed time, and the three
pairwise Cohen's κ on disposition plus their mean.

**The pre-registered question**, written into `docs/EVALUATION.md` with a timestamp at CP5,
before any system disposition for these credits exists:

> On the credits where the raters disagreed with each other — any pairwise disposition
> disagreement — did the system flag rather than clear?

Answered at CP6 and reported either way. Pre-registration is what makes a negative answer
publishable rather than embarrassing, and §9.10 names F56 one of the two rows worth more than all
the others.

**Also recorded, and not optional:** the places you personally got confused. §6.1 is right that
these are the most credible possible justification for the exception taxonomy, and they are
available for about ninety minutes of work exactly once.

### D19 · The ops console

FastAPI, Jinja server-rendered HTML, HTMX vendored as a static file. No frontend build, no
bundler, no npm. §5.13's four views, scoped to what CP7 can finish:

| Route | View | Contents |
|---|---|---|
| `GET /` | batch | The three buckets with counts and rupee totals, and the audit chain head hash |
| `GET /credit/{id}` | decomposition | The §5.7 proof block and the waterfall |
| `GET /exceptions` | queue | Diagnosis, candidate decompositions, refusal reason, suggested action |
| `POST /exceptions/{id}/resolve` | action | accept / correct / escalate; the only write in the console, and it writes to the exception-resolution table |
| `GET /audit` | audit | Replay a historical decomposition and report chain integrity |

The waterfall is server-rendered inline SVG: every coordinate and every label computed from
integer paise in `waterfall.py`, no client-side arithmetic and no chart library. §5.13 calls it
the highest-value-per-hour visual in the project, and it earns that by making the proof legible
in the four seconds a reviewer gives it. Streamlit is the documented fallback if CP7 is tight
(§7); the four views matter and the framework does not.

### D20 · The Q&A surface (F9)

The retrieval contract is what makes a hallucinated number architecturally impossible rather than
unlikely, so it is specified as a contract rather than a pipeline.

1. **Intent, from a closed set.** `classify_intent` matches rules first over a fixed `Intent`
   enum. The model may only choose among those ids — never generate SQL, never name a table.
   `UNRECOGNISED` is a valid answer and is not a failure.
2. **Retrieval returns typed rows.** One of a closed set of parameterised queries runs against
   the **reconciled** ledger over a read-only connection. The Q&A layer cannot trigger a
   re-solve, cannot write, and cannot see un-reconciled state (§5.11).
3. **The formatter renders every figure.** `render_slots` turns typed rows into a
   `{slot_name: rendered_string}` map using `money.format_rupees`. This is the only place a
   number in an answer is produced.
4. **The model composes connective prose only.** `compose` receives the question, the intent and
   the slot **names** with no values, and returns prose containing only those slots.
5. **Substitution is total, and the check is the same one used everywhere else.** Any slot the
   model invents, and any money-shaped literal in its output, rejects the response and falls back
   to `deterministic_answer`.

**The structural reason it cannot do otherwise:** the model never receives a figure, so it has
nothing to copy incorrectly; and its output is a template rather than an answer, so every numeral
in the final text was placed there by `render_slots` from a retrieved row. That is a claim of
impossibility rather than improbability, and it is true, which is why it is worth saying to the
panel. Citations come free: every slot carries the row ids it was rendered from, and the renderer
emits them.

---
## 3 · Traceability

One row per feature. F1–F18 are §6; F19–F22 are §6.1 Tier 1; F56 is §6.2 Group E and is the only
row here with a §9.10 entry, because §9.10's table begins at F31. Every one of F1–F22 and F56
appears exactly once, and nothing is left without a home.

| F | Delivered at | Artifact that proves it | The number it owes | Cited from |
|---|---|---|---|---|
| F1 · Two-regime reconciliation | CP3 (fast path), CP6 (reported) | `artifacts/dev/headline.md`, split by regime | Coverage, error, exact-decomposition **separately for Regime A and Regime B** | §9.2, §3.3 |
| F2 · Signed subset-sum solver | CP3 | `tests/test_solver_properties.py` green; `artifacts/bench_solver.md` | Median and worst solve time per credit **with the machine named**; assignment P/R | §5.6, §9.2 |
| F3 · Uniqueness guarantee | CP3, measured CP6 | `tests/test_uniqueness.py`; class-23 row of the per-class table; the uniqueness ablation | Class-23 refusal rate (coverage on that class must be 0, error 0); Δcoverage and Δerror with uniqueness disabled | §5.6, §9.6 |
| F4 · Calculator-checkable proofs | CP4 | `artifacts/proofs/*.txt`; `tests/test_proof.py::test_rendered_block_is_calculator_checkable` | Fraction of cleared credits whose rendered proof re-sums to the credit (must be 1.00); residual distribution among non-cleared | §5.7, §9.2 |
| F5 · Hash-chained audit trail | CP4 | `make verify-audit` exit 0; chain head in `artifacts/audit_head.txt` | Chain length and head hash; first-break sequence number on a tampered fixture | §5.8 |
| F6 · Tiered entity resolution | CP5 | `artifacts/dev/tier_mix.md` | Fraction of items resolved at each of tiers 1–5; count of model calls avoided by tiers 1–3 | §5.9, §9.7 |
| F7 · Diagnostic exception engine | CP5, measured CP6 | `artifacts/dev/exceptions.md` | Exception precision; distribution over the eleven classes; fallback fraction | §9.2, §5.10 |
| F8 · Near-miss delta diagnostics | CP3 (search), CP5 (rules) | `tests/test_classify.py`; the exceptions artifact | Fraction of `NONE_FOUND` credits given a rule-matched (non-fallback) class | §5.6, §5.10 |
| F9 · Settlement Q&A | CP7 | `tests/test_qa.py`; `artifacts/qa_examples.md` | Fraction of answer figures that are slot-substituted (must be 1.00); citations per answer | §5.11 |
| F10 · Four-arm harness | A0/A1 CP2, A2 CP4, A3 CP6 | `artifacts/dev/headline.md` | The whole §9.8 table, four arms plus A4, both regimes | §9.1, §9.8 |
| F11 · Per-class reporting | CP6 | `artifacts/dev/per_class.md` | Assignment P/R, exact, coverage, error and a note for each of classes 1–23, with n per class | §9.3 |
| F12 · Risk-coverage curve and derived threshold | CP6 | `artifacts/dev/curve_a3.json`, `curve_a2.json` | The declared error budget, the threshold read off the curve, and the coverage at it — for A3 **and** A2 | §9.5 |
| F13 · Ablation study | CP6 | `artifacts/dev/ablations.md` | Δcoverage and Δerror for each of the five ablations | §9.6 |
| F14 · Property-based tests | CP3 (solver), CP4 (end to end) | `tests/test_solver_properties.py`, `tests/test_arithmetic_invariant.py` | Count of generated examples; the invariant holds on all of them | §9 preamble, §6 F14 |
| F15 · Sourced, dated tax configuration | CP0 | `config/tax_rates.yaml`, `config/fees.yaml` | Count of rate entries carrying `source_url` and `as_of` (must equal the entry count); count marked `synthetic` | §3.2, §6 F15 |
| F16 · Byte-reproducible runs | CP6 (determinism), CP7 (command) | `make reproduce` exit 0 | Two runs byte-identical outside the timing channel; backstop-did-not-fire assertion | §5.6, §6 F16 |
| F17 · Waterfall visual | CP7 | Console `/credit/{id}`; `artifacts/waterfall_example.svg` | Renders for 100% of cleared credits with the residual line reading zero | §5.13, §6 F17 |
| F18 · Incident log to postmortem | CP0 (created), CP8 (populated) | `docs/INCIDENTS.md`; `tests/regressions/` | Real entry count and one regression test per entry | §13.2 |
| F19 · Human baseline arm | **CP5** | `artifacts/human_study/results.json` | 20 credits by hand: wall time, own exact-decomposition accuracy against truth, and the confusion notes | §6.1 |
| F20 · Reproducibility demonstration | CP7 | `make reproduce` | Exit 0 across two full runs; non-zero on an injected difference | §6.1 |
| F21 · Challenge harness | CP7 | `fixtures/challenges/*.json` | Three files run to a terminal disposition; the third is refused rather than solved | §6.1 |
| F22 · One-command evidence pack | CP7 | `artifacts/evidence.html`, committed | One self-contained file carrying headline table, per-class table, curve, ablations, audit head, environment fingerprint and test-eval count | §6.1 |
| F56 · Multi-rater human study | **CP5** | `artifacts/human_study/` | Per-rater time and accuracy; three pairwise Cohen's κ and their mean; the system's disposition on human-disagreement cases | §6.2 Group E, §9.10 |

Nothing in F1–F22 or F56 is unassigned. Two rows are worth flagging as unusual: F19 and F56 both
sit at CP5 rather than at the harness checkpoint where they would naturally live, because a human
baseline gathered after you know the machine's answers is not a baseline; and F17 is the one row
whose owed number is an assertion rather than a measurement, which is the honest description of
what a visual can owe.

---

## 4 · Test inventory

**Which of §10's named tests belong to Phase 1.** Getting this boundary right matters, because
creating a Phase 2 test file early produces either a skipped test or a false green.

| §10 test file | Phase | Note |
|---|---|---|
| `test_solver_properties.py` | **1** | CP3. Specified in full below. |
| `test_uniqueness.py` | **1** | CP3, against class 23. |
| `test_audit_chain.py` | **1** | CP4. |
| `test_no_leakage.py` | **1** | CP1, extended at CP2. |
| `regressions/` | **1** | CP8, one file per incident. |
| `test_disambiguation.py` | 2 | F31 CP-SAT. Do not create in Phase 1. |
| `test_conservation.py` | 2 | F33. |
| `test_pii_boundary.py` | 2 | F49. Distinct from CP5's amount boundary. |
| `test_injection.py` | 2 | F50. |
| `test_journal.py` | 2 | F40. |
| `test_feature_flags_off.py` | 2 | Written the moment Phase 2 starts, not before — there are no §6.2 features to disable yet. |
| `test_idempotency.py` | 2 / 4 | F25 and F47. CP8's `test_duplicate_webhook_is_idempotent` is a narrow precursor, not this file. |
| `test_determinism.py` | 4 | F34, worker-count determinism. Phase 1's reproducibility test is `test_reproducible_report.py`, named differently on purpose so the two never collide. |

**`tests/test_solver_properties.py` — the test that licenses every claim in §9.**

The oracle it compares against is exhaustive enumeration, and the definition it encodes is the
whole point:

```python
def brute_force_solutions(amounts: Sequence[int], target: int, tol: int) -> set[frozenset[int]]:
    """Every NON-EMPTY index subset whose signed sum lies within tol of target, by iterating all
    2**n masks. Note what this counts: subsets within tolerance of the target, NOT subsets
    summing to one particular reachable total. That distinction is the §0.1 defect."""
```

Property-based via Hypothesis, generated domain:
`amounts = lists(integers(-60, 60).filter(lambda x: x != 0), min_size=1, max_size=14)`,
`target = integers(-200, 200)`, `tol = integers(0, 5)`. Capped at 14 items so `2**n` enumeration
stays a genuine oracle rather than a second heuristic. Eleven properties, each stated in CP3's
test table; the two that carry the most weight are
`test_uniqueness_agrees_with_brute_force_under_tolerance` (the §0.1 correction) and
`test_claimed_match_verifies` (the F14 invariant the whole product rests on).

The three seeded loops from `test_solver.py` are carried over as regression cases against the new
module path — 800 signed instances at `tol=0`, 300 at `tol` in `0..3`, 500 invariant instances at
`tol=2` — with the tolerance loop **upgraded** to compare uniqueness rather than only
reachability, which is what it should have been doing. `bench_settlement_scale()` becomes
`tests/bench_solver.py`, is driven from real generated pools rather than synthetic ones, and
records the machine.

**Property-based tests in Phase 1**, and their generated domain:

| Test | Domain |
|---|---|
| `test_solver_properties.py` (11 properties) | Signed integer amount lists to length 14, integer targets, integer tolerance 0–5 |
| `tests/test_arithmetic_invariant.py::test_claimed_clear_verifies_at_paise` | Generated candidate pools and targets at paise, run through the real orchestrator |
| `tests/test_money.py::test_to_rupee_units_error_bounded_by_half` | Signed integers across several orders of magnitude |
| `tests/test_normalise.py::test_normalisation_is_idempotent` | Unicode text including homoglyphs, mixed case, doubled whitespace and rail prefixes |

**Everything else, by checkpoint.** CP0: `test_models`, `test_config`, `test_money`,
`test_no_floats`, `test_plan_arithmetic`. CP1: `test_no_leakage`, `test_generator`,
`test_normalise`, `test_ingest`. CP2: `test_corruption_classes`, `test_arms_baseline`,
`test_metrics` (partial). CP3: `test_solver_properties`, `test_uniqueness`, `test_candidates`,
`test_fastpath`. CP4: `test_verify`, `test_proof`, `test_audit_chain`, `test_least_privilege`,
`test_arithmetic_invariant`, `test_arms_rules`. CP5: `test_tiers`, `test_no_amounts_to_model`,
`test_classify`, `test_ordering_score`. CP6: `test_metrics` (complete), `test_stats`,
`test_report_assertions`, `test_curve`. CP7: `test_qa`, `test_console`, `test_challenge`,
`test_reproducible_report`. CP8: `test_razorpay_adapter`, `tests/regressions/*`. CP9:
`test_readme_numbers`.

---

## 5 · What Phase 1 deliberately does not build

**Second-wave items §6.1 defers rather than cuts** — ~26h, scheduled in §11, not in Phase 1:

| F | Waits for | Why |
|---|---|---|
| F23 cross-profile generalisation | Phase 3 | Needs three profiles and a full harness; the generator is parameterised at CP1 (D3) so it is cheap when it arrives. |
| F24 adversarial self-test | Phase 2 | Attacking your own system is worth more once the system is the tagged one a reviewer will see. |
| F25 idempotency and crash-resume | Phase 2 | CP8's duplicate-webhook test is the narrow precursor; the full property pair needs a stream layer. |
| F26 human-in-the-loop learning curve | Phase 3 | Needs accumulated exception resolutions, which do not exist until the console has been used. |
| F27 scale analysis | Phase 4 | Written *against* F57's measurements rather than as a pure argument. |
| F28 calibration note | Phase 4 | The good outcome is one paragraph saying we used only observable quantities, which is only worth writing once that is finally true. |
| F29 FX and multi-currency rounding | Phase 4 | Corruption class 26 depends on it, which is why §6.2 removed it from first-to-cut. |
| F30 cost governor | Phase 3 | Built before F51, since it is the first rung of the ladder F51 completes. |

**Third-wave items F31–F57**, all of §6.2 except F56, wait for Phases 2–4 in the build order §6.2
gives: F33 conservation, F49 PII boundary, F55 CI, F31 CP-SAT disambiguation, F40 journal export,
F37 exception clustering, F38 rate drift, F52 decision trace, F50 injection corpus, F54 eval-diff
(Phase 2); F32 derived tolerance, F51 degradation ladder, F39 leakage, F45 CAMT/MT940, F48
ingestion fuzzing, F35 incremental reconciliation, F41 reserve sub-ledger, F42 dispute lifecycle,
F57 latency profile (Phase 3); F53 provider swap, F36 alternate diff, F34 deterministic
parallelism, F47 live webhooks, F43 parameter recomputation, F44 multi-account, F46 bitemporal
(Phase 4). **F56 is the single exception and it runs in Phase 1, at CP5**, because a multi-rater
study conducted after you know the system's answers is not a study.

Three of those deserve a note here because a Phase 1 executor will be tempted by them. **F31** is
tempting the first time a class-23 credit is refused and the structural tie-break is obvious to a
human — but CP-SAT with a modelling bug can narrow a solution set incorrectly and manufacture a
confidently wrong unique answer, which is the exact failure this system exists to prevent, and
NN-18's subset assertion does not exist yet. **F33** is tempting because the conservation identity
is only about four hours — but it is the safety net under the *whole* of Phase 2 and it belongs at
the start of that phase, not bolted onto the end of this one. **F49** is tempting the moment you
notice CP5 sends `counterparty_raw` to a third party. Note it in the README limitations at CP9 and
leave it to Phase 2, where it is scheduled second.

**And the list that holds at any budget** (§6.2, restated because the calendar is no longer
enforcing it): no mobile app; no dashboard of charts nobody reads; no chat interface beyond F9; no
cash-flow forecasting or any other behavioural counterfactual; no invoice OCR; no second track's
product bolted on; no rewrite in a faster language; no custom frontend framework; no real bank or
accounting-system write path; and —

**No machine-learned matcher.** This is the one the executor will most want, and the argument
against it is the strongest single paragraph available for `docs/DECISIONS.md`. The exact solver
already returns the *complete* solution set with a uniqueness guarantee. A learned scorer could at
best approximate what we already compute exactly, while being slower to justify, impossible to
prove, and strictly less explainable. Writing that argument down is worth more than the model
would be, and it is the purest instance of the rubric's "where you chose not to use one" — a
sentence only available *because* the deterministic core is strong enough to make the model
unnecessary.

---

## 6 · Risk notes

**CP3 is the highest-risk checkpoint in the project (§12), and its trip-wire is quantitative.**
If median solve time exceeds **2 seconds per credit**, stop optimising and ship the
`BUDGET_EXCEEDED` path. An honest exception costs coverage; a hang costs the submission. Record
which you did in `PROGRESS.md`. The mitigations are all already in the design and none of them is
optional: rupee-granularity search, `MAX_POOL = 400`, the deterministic axis-width and
enumeration caps, and `BUDGET_EXCEEDED` as an honest disposition rather than a hang.

**The wrong-data-model risk, and the specific check that retires it.** §12 names this as the
failure mode that kills competitors: building 1:1 and discovering N:M late, after a week of
surrounding code has been written against the wrong shape. It is the one category of mistake that
does not get cheaper with a longer runway. Two checks retire it, in order. At **CP1**, generate
class 4 `MIXED_N_M` and *look at three cases* until the N:M shape is undeniable — many payments
and many refunds, spanning more than one credit. End-to-end is not available at CP1 because there
is no solver yet, and printing the cases is the cheap version of the same insurance. At **CP3**,
a class-4 credit must decompose end to end **before a line of CP5, CP6 or CP7 exists**. That
ordering is in the ladder and in CP3's definition-of-done command, and it is not negotiable for
scheduling convenience.

**Memory from DP snapshots.** `(n+1) · axis_width / 8` bytes, bounded by `MAX_POOL` and
`MAX_AXIS_WIDTH_RUPEES`, reported by `ReachabilityIndex.memory_bytes()` into the metrics channel.
§12's documented fallback if it bites is to recompute forward instead of snapshotting and accept
the constant factor. Do not invent a third option under time pressure.

**Model cost or rate limits during evaluation.** The prompt-hash cache makes runs 2..n nearly
free and turns an outage into a cache hit; `--offline` makes a miss a hard failure rather than a
nondeterministic call; the hard per-run token budget raises `TokenBudgetExceeded` loudly rather
than degrading silently. See `PLAN-QUESTIONS.md` Q2 for the part of this that is not mine to
decide.

**Ground-truth leakage.** Mechanically prevented by the `SourceRoot` path boundary plus
`tests/test_no_leakage.py`. Per NN-6, **re-run that test after any change to a loader** — including
a change that looks purely cosmetic, because the mechanism is a path boundary and path boundaries
are exactly what refactors move.

**Tuning on test.** The structural guard is at CP6: `eval.cli` refuses the test split without an
explicit gate flag *and* a log row in `docs/EVALUATION.md`. Phase 1 spends evaluation 1 of a
project-lifetime ceiling of 4, at CP9 and nowhere else. If you slip, disclose it in the README —
§12 is right that a disclosed slip is a blemish and an undisclosed one is a credibility hole.

**Risks this plan introduces that the spec's register does not have**, each traced to the §0 entry
that argues it:

| Risk | Mitigation | Where argued |
|---|---|---|
| Uniqueness assessed at one reachable total reports `UNIQUE` for a genuinely ambiguous credit | Enumerate across every hit total under one shared cap; the corrected brute-force oracle is written *first* and must fail against the reference | §0.1, D8 |
| `ε` derived from an itemisation model that later changes | `m` is written into every `TruthRecord` and asserted against `subrupee_member_max` at CP1, before `ε` is fixed at CP3 | §0.2, D6 |
| A reduced-pool `UNIQUE` auto-clears something never shown to be unique | `pool_scope` is on every `SolveResult` and auto-clear requires `FULL`; the reduced count is reported at CP6 | §0.3, D5 |
| A wall-clock budget makes dispositions machine-dependent and breaks NN-9 | The operative budget is deterministic; wall-clock is a backstop whose firing makes `report.py` refuse to publish | §0.4, D5 |
| An exception narrative or a Q&A answer carries a model-written number | Slot-name payloads, total substitution, and the money-pattern rejection on both directions of every model call | §0.5, D13, D20 |
| Sign validation makes corruption class 18 un-ingestible | Sign is a derived check; `test_sign_is_derived_not_enforced` asserts a wrong-signed item still constructs | §0.6, D1.1 |

**Fatigue in the verification window.** §12 lists this as a project risk rather than a lifestyle
note, and it is right: CP8 and CP9 are failure injection, honest self-assessment and final
verification — the tasks that degrade fastest under sleep debt and the ones where a mistake is
unrecoverable because there is no time left to catch it. A sharp four hours of failure injection
beats a foggy twelve.

---

## 7 · Self-check

Run against the constraints in the planner brief, line by line, with the result rather than a
claim of compliance.

| Check | Result |
|---|---|
| Every CP block has all eight fields, none a placeholder | **PASS.** CP0–CP9 each carry Goal, Owns files, Depends on, Signatures, Invariants, Tests, Definition of done, Notes. CP9's Signatures field states "None" with the reason, which is a decision rather than a placeholder. |
| Every definition of done is a command, not a description | **PASS.** All ten are shell commands. CP9's adds one manual step — `make demo` from a clean clone in a private window — which §11's Gate 1 requires and which cannot be automated from inside the repository. |
| Each of NN-1 … NN-21 that applies to Phase 1 is assigned to at least one CP with a named mechanism | **PASS, with two exclusions stated.** NN-1 CP0 (`test_no_floats` AST scan). NN-2 CP5 (`classify` has no client parameter). NN-3 CP5 (no numeric field on the request types, plus the egress scan). NN-4 CP5/CP6 (`ordering_score` signature; `test_curve_inputs_are_observable`). NN-5 CP4 (one orchestrator file; the sub-window retry is internal to one stage). NN-6 CP1/CP2 (`SourceRoot`, three assertions in `test_no_leakage`). NN-7 CP1 (truth hashed before and after corruption). NN-8 CP0 (`UnverifiedRateError`). NN-9 CP1/CP4/CP6/CP7 (seeded RNG, payload/metrics split, `make reproduce`). NN-10 CP3 (guard inside `ReachabilityIndex`, no public mask). NN-11 CP3 (`test_over_cap_pool_is_never_truncated`). NN-12 CP4 (`test_acceptance_never_widens_with_tolerance`; `ε` is not a parameter of `verify_decomposition`). NN-13 CP2/CP4/CP6 (ladder ordering; dev figures timestamped in `PROGRESS.md`). NN-14 CP9 (`test_readme_numbers`). NN-15 CP0/CP9 (`test_plan_arithmetic`, `test_no_spec_illustrative_figure_is_republished`). NN-16 CP2/CP6/CP9 (held-out class frozen before test generation; gate flag on `eval.cli`; one logged evaluation). NN-17 — **does not apply to Phase 1**, which contains no §6.2 feature except F56; it binds from Phase 2, and `test_feature_flags_off.py` is listed in §4 as Phase 2 for that reason. NN-18 — **does not apply**, F31 is Phase 2. NN-19 CP0 (file exists first), CP8 (populated contemporaneously). NN-20 CP9. NN-21 CP5 (F19/F20/F22/F56 named as protected in the cut notes; CP7 repeats it for F20 and F22). |
| D6's reachability argument is written out as an inequality, not asserted | **PASS.** D6 derives `Σ r(a_i) − r(T) = Σ δ_i − δ_T` from the paise identity, bounds it by `(m+1)/2`, tightens to `floor((m+1)/2)` because the left side is an integer, and states the reachability condition `ε_R ≥ floor((m+1)/2)`. Worst case as a function of member count is `floor((n+1)/2)`; the typical case is `≈ 0.29·√m`, which is where F32's fitted form comes from. |
| Corruption classes 24, 25, 26 appear nowhere | **PASS as a plan constraint.** They appear in four places and not one is a recipe: the `CorruptionClass` comment marking them forbidden, CP1's `test_forbidden_classes_absent`, D4's closing sentence, and §5's note that corruption class 26 is why F29 is no longer first-to-cut — a forward reference §6.1 and §8.3 both require. They are absent from the recipe table, from the enum members, and from every corpus. |
| F19 and F56 are both at CP5, with the reason stated | **PASS.** Both in CP5's owned files and its definition of done, with the hard stop in note 1 and the full protocol in D18. Reason stated in three places: an honest human baseline does not exist once you know the system's answers, and that applies to briefing raters as much as to reconciling yourself. |
| A0, A1, A2 are specified and scheduled before A3 is measured | **PASS.** A0 and A1 built and measured on dev at CP2; A2 at CP4; A3 first measured at CP6. Specified in D15.1–D15.3, with the verbatim README fairness sentence in D15.5. |
| No result figure appears anywhere | **PASS, verified rather than claimed.** Grepped this draft for `0.94`, `0.942`, `0.0008`, `200:9`, `47,200`, `2.04`, `0.71` and `65-70`. Each returns exactly one hit and every hit is inside this row — the list of patterns being grepped for. None appears anywhere else in the document. The bare `51` occurs only inside `151h`, which is §11's own phase total and an hour estimate, and inside `r(-151)` in D6's rounding example. §5.6's quoted benchmark is referred to without reproducing its numbers, and CP3 requires re-measurement on the executor's machine. The only numerals in this document are design parameters (`ε_R = 7`, `m ≤ 13`, `MAX_POOL = 400`), bounds, counts of things to build, and hour estimates. |
| Estimates sum to 146h, or the discrepancy is stated | **PASS.** `8 + 16×8 + 10 = 146`. F56's ~5h sits outside the ladder, which is exactly why §11 reads ~151h and the days read 146. |
| The traceability table covers F1–F22 and F56 with no gaps | **PASS.** 23 rows, one per feature, each with a checkpoint, an artifact, an owed number and a cited section. §9.10 is cited only for F56, since that table begins at F31. |

**Two things I did not do, deliberately.** I did not set the autonomy threshold — it is
`TBD-CP6-CURVE` in `config/solver.yaml`, and the loader rejects a hand-set value that does not
carry a `threshold_source` pointing at a curve artifact. And I did not introduce a dependency
beyond §7; `pyyaml`, `jinja2` and `uvicorn` are entailed by §7's own "config YAML" and "FastAPI +
server-rendered HTML with HTMX", and Phase 1 does not need `lxml`, `scikit-learn` or OR-Tools,
all of which belong to features in later phases.

**Open items are in `PLAN-QUESTIONS.md`**, three of them, none blocking the whole plan: the
withholding provision to model, the model provider and spend authorisation, and rater
availability for F56.
