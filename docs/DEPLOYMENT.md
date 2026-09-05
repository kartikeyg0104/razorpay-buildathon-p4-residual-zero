# Deployment

How Residual Zero goes from a loopback desk to a public HTTPS deployment, and what changes
when it does.

Two things do **not** change: the deterministic reconciliation engine, and the numbers it
produces. The engine, the solver, the verifier, the rate tables and the committed dev
corpus are untouched by everything below. `tests/deployment/test_corpus_migration.py`
asserts that reading the corpus out of PostgreSQL gives the same residual, the same gate
decision and the same member set for every credit as reading it out of the CSVs.

---

## 1. Architecture

```
Browser ──HTTPS──┐
                 ├──▶ Residual Zero console (FastAPI, one process)
Chrome extension ┘        │
  Authorization:          ├──▶ deterministic engine (Python, integer paise)
  Bearer rz_pat_…         │        └──▶ authoritative result
                          │
                          ├──▶ PostgreSQL
                          │      rz_shared    identity: users, orgs, sessions, tokens
                          │      org_<id>     that organisation's financial rows
                          │
                          └──▶ NVIDIA NIM  (server-side only; explains, never decides)
```

One process. No queue, no worker, no cache tier: reconciliation is synchronous and
deterministic, and a broker would be infrastructure without a job.

**Where financial authority lives.** In the engine, and nowhere else. Authentication
decides *which organisation's records you may read*. It never decides what the numbers are,
and no role can authorise `CLEARED` — that requires `UNIQUE` + a zero-paise residual + a
`FULL` pool + a derived threshold, checked by the solver and the verifier, and restated as a
CHECK constraint in the production schema.

---

## 2. Two modes

| | `RZ_ENV=local` (default) | `RZ_ENV=production` |
|---|---|---|
| Authentication | off | required |
| Tenancy | single | one organisation per user |
| Database | SQLite file | PostgreSQL |
| Cookies | plain | `Secure`, `HttpOnly`, `SameSite=Lax` |
| HSTS | not sent | sent |
| Origin check on writes | loopback allowlist | `RZ_PUBLIC_ORIGIN` |

Local mode is the historical behaviour, unchanged, which is what keeps `make demo`,
`make eval`, the CLI and the test suite working exactly as before.

`RZ_ENV=production` **refuses to start** without `RZ_AUTH_MODE=required`, a 32+ character
`RZ_SESSION_SECRET`, an `https://` `RZ_PUBLIC_ORIGIN` and a PostgreSQL `RZ_DATABASE_URL`.
The dangerous failure for a public finance console is not a crash — it is booting happily
with authentication off — so that combination is not reachable.

---

## 3. Data isolation

Isolation is **structural**, not a `WHERE` clause. Each organisation gets its own storage
namespace, and its connections cannot name anything outside it:

* **PostgreSQL** — one schema per organisation. The connection sets `search_path` to that
  schema alone, with no `public` fallback. A query that forgot an `org_id` filter resolves
  inside the caller's own schema or fails to resolve at all.
* **SQLite** — one database file per organisation under `RZ_TENANT_ROOT`.

The organisation is bound by the authentication middleware, before any route body runs, and
travels in a `ContextVar` (`residual_zero.tenancy`). Roughly a hundred call sites read the
desk's data through four accessors — `_split`, `_overlay`, `_credit_lookup`, `_db` — so
making *those* organisation-aware is what let multi-tenancy land without editing financial
code.

Identity is the one schema a tenant connection can never reach, because a login happens
before the organisation is known. It holds no financial value.

---

## 4. Authentication

**Browsers** get a session cookie: opaque random token, stored only as a SHA-256 digest, so
a database dump does not hand anybody a live session. `HttpOnly`, `SameSite=Lax`, `Secure`
whenever the public origin is HTTPS.

**The extension, the CLI and MCP** use a personal access token — `Authorization: Bearer
rz_pat_…` — that the user mints for themselves at `/tokens`. Two reasons it is not a cookie:
a cookie would have to be sent cross-origin from an extension page, which means relaxing
`SameSite` for everybody; and a bearer token is not a CSRF vector, so the origin check on
writes can stay strict. It also means **no secret is bundled into the shipped extension**.

Passwords are scrypt-hashed (n=2¹⁵) with a per-user salt. Roles are `viewer` (read),
`analyst` (+ record human review, export) and `owner` (+ administer). There is no `clear`
permission, for any role.

CSRF: a **cookie** write must carry an `Origin` this deployment owns. A **bearer** write
needs no origin. In local mode a missing `Origin` is still read as "a non-browser client",
which is fair on loopback; under `RZ_AUTH_MODE=required` that inference is withdrawn.

---

## 5. Deploy

### 5.1 Provision PostgreSQL

Any managed Postgres works. The connection string must include `sslmode=require`.

```bash
export RZ_DATABASE_URL='postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require'
```

### 5.2 Apply the schema

```bash
pip install -e ".[postgres]"
python scripts/migrate.py --shared          # identity tables in rz_shared
python scripts/migrate.py --status          # what is pending, nothing applied
```

Migrations are numbered SQL files under `migrations/`, idempotent, and recorded with the
checksum of the file that produced them. Editing a file that has already been applied is a
hard error — add a new numbered file instead.

### 5.3 Create the first organisation and owner

```bash
# The demo organisation, reading the committed synthetic corpus so the desk shows numbers:
python scripts/bootstrap_admin.py --email you@example.com --org demo --dataset files

# Or an organisation that will hold its own ingested rows:
python scripts/bootstrap_admin.py --email you@example.com --org acme
```

The password is prompted for, or read from `RZ_ADMIN_PASSWORD`. It is never a command-line
argument, because an argument is visible in the process table and in shell history.

### 5.4 Load a corpus into an organisation (optional)

```bash
python scripts/migrate_corpus.py --org acme --source data/dev/rendered
```

Reports row counts and signed paise totals from the source and from the database side by
side, and **exits non-zero unless every pair matches**. A migration that changed a financial
aggregate is a failed migration.

### 5.5 Configure and run

```bash
export RZ_ENV=production
export RZ_AUTH_MODE=required
export RZ_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export RZ_PUBLIC_ORIGIN=https://residual-zero.example.com
export RZ_TRUST_PROXY=1
export RZ_HOST=0.0.0.0
export AI_PROVIDER=nvidia
export NVIDIA_API_KEY=nvapi-…        # server-side only

python -m residual_zero.console
```

Or with Docker:

```bash
docker build -t residual-zero .
docker run -p 8765:8765 --env-file .env residual-zero
```

`docker-compose.yml` brings up app + PostgreSQL locally for rehearsing the deployment.

### 5.6 Verify

```bash
curl https://…/healthz    # liveness; no credential, no financial data
curl https://…/readyz     # configuration valid + database reachable
```

`/readyz` names any misconfigured variable and never prints its value. `/api/health`
reports credit counts and provider state, so it stays behind authentication — that is why
`/healthz` exists.

---

## 6. The Chrome extension

The extension is read-only, holds no secret, and consumes authoritative backend results. It
does not duplicate the engine and it does not solve a feature by opening the web app —
every navigation lands on the extension's own panel page.

1. Deploy the backend and sign in.
2. Visit `/tokens`, create a token, copy it.
3. Load `extension/` unpacked in Chrome (or download `/extension.zip`).
4. Open the extension's options page, enter the desk URL and paste the token.

A deployed desk URL must be `https://`. Host access is requested at that point via
`optional_host_permissions`, so no production domain is baked into the shipped package and
the install does not ask for broad access up front.

---

## 7. Environment variables

See `.env.example` for the full annotated list. The ones a production deployment must set:

| Variable | Purpose |
|---|---|
| `RZ_ENV=production` | Turns on the startup checks below |
| `RZ_AUTH_MODE=required` | Authentication and per-organisation isolation |
| `RZ_SESSION_SECRET` | 32+ chars; session entropy |
| `RZ_PUBLIC_ORIGIN` | `https://…`; CORS, cookie scope, write-origin allowlist, HTTPS redirect |
| `RZ_DATABASE_URL` | `postgresql://…?sslmode=require` |
| `RZ_TRUST_PROXY=1` | Read `X-Forwarded-Proto/For` from the TLS terminator |
| `RZ_HOST=0.0.0.0` | Required inside a container |
| `NVIDIA_API_KEY` | Server-side only. Never reaches a browser or the extension |

Optional: `RZ_ALLOWED_ORIGINS`, `RZ_EXTENSION_IDS`, `RZ_ALLOW_SIGNUP`,
`RZ_SESSION_TTL_HOURS`, `RZ_LOG_LEVEL`, `RZ_SHARED_SCHEMA`, `RZ_PORT`/`PORT`.

---

## 7a. Running the tests without dirtying the tree

```bash
pytest -q                 # unit + integration; leaves the working tree clean
RZ_E2E=1 pytest -q        # adds Playwright browser certification
RZ_TEST_POSTGRES_URL=postgresql://... pytest -q tests/deployment   # storage against real PG
```

Neither suite writes into a committed artifact. Two knobs exist for the cases where you
*do* want the published files refreshed:

| Variable | Effect |
|---|---|
| `RZ_REFRESH_DEMO_SHOTS=1` | E2E writes its screenshots to `artifacts/demo/` (the committed documentation set) instead of the gitignored `artifacts/e2e/shots/`. Refreshing documentation should be a deliberate act, not a side effect of testing. |
| `RZ_DB=<path>` | Points the desk at a specific SQLite ledger. The E2E harness sets this to a disposable copy so the suite never writes `artifacts/dev/ledger.sqlite`. |

Regenerate the published evaluation artifacts explicitly with `make eval` /
`python -m eval.ai_recovery`, never as a side effect of `pytest`.

## 7a-bis. Running on Render's free plan

The blueprint targets `plan: free`, which needs no payment details. Measured against the
free plan's hard 512 MiB limit, on the production image:

| | memory |
|---|---|
| After boot | 71 MiB (14%) |
| After all 19 surfaces | 97 MiB (19%) |
| After 5x close-pack + journal builds | 100 MiB (20%) |
| After an AI investigation + 5 solver-backed proof pages | **104 MiB (20%)** |

Zero OOM kills, zero restarts. `ortools`, `scipy`, `pandas`, `numpy` and `lxml` are
declared dependencies but are never mapped into the serving process - only `psycopg` is -
so the console's working set is far smaller than the dependency list suggests.

**What the free plan costs you.** A free instance sleeps after roughly 15 minutes with no
inbound request and cold-starts in about a minute. Nothing is lost when it sleeps: all
durable state is in Neon, and `/app/var` holds only the AI investigation log and
per-organisation SQLite files that are never created on the PostgreSQL backend. For a
judged demo, either open the URL a minute before showing it, or point any uptime pinger at
`/healthz` (it opens no database connection, so pinging it is close to free).

**If Render rejects the free plan in `ohio`,** change `region` to `oregon` - the only other
edit needed. Expect roughly 60-70 ms per connection to Neon's `us-east-2` instead of
single-digit milliseconds; with six connections per credit page that is under a second, not
the 24 s measured from 12,000 km away. Prefer `ohio` if it is offered.

## 7a-ter. Railway (the platform this is deployed on)

Live: **https://residual-zero-production.up.railway.app**

Railway builds the `Dockerfile` — the same image rehearsed locally — and probes `/healthz`.

### Service settings

Railway's **Config as Code is deprecated**: `railway.json` / `railway.toml` are silently
ignored, and the API rejects `railwayConfigFile` outright, pointing at Infrastructure as
Code (`.railway/railway.ts`) instead. This repo carried a `railway.json` declaring
`builder: DOCKERFILE`; the live service reported `builder: RAILPACK`,
`railwayConfigFile: null` the entire time, and two tests asserting that file's contents
passed while none of it was in effect. The file is gone. Settings now live on the service
instance:

| setting | value |
|---|---|
| `dockerfilePath` | `Dockerfile` |
| `healthcheckPath` | `/healthz` |
| `healthcheckTimeout` | `300` |
| `restartPolicyType` | `ON_FAILURE` (max 3) |

`Builder` has no `DOCKERFILE` member — setting `dockerfilePath` is what selects a
Dockerfile build.

### RZ_HOST on Railway

Set it to `::` or `0.0.0.0`, or leave it unset and take the image default. Two spellings
that look right and are not:

- **`[::]`** — RFC 3986 bracket notation for a URL, which is what Railway's own docs show.
  `getaddrinfo` does not accept brackets, so uvicorn failed with a bare
  `[Errno -2] Name or service not known` *after* logging "Application startup complete".
  The entrypoint now strips the brackets and probes a real bind before uvicorn starts.
- **a hostname** (`*.railway.internal`, the public domain) — `RZ_HOST` is the address the
  process binds, not the address people reach it on. The public URL belongs in
  `RZ_PUBLIC_ORIGIN`.

`::` also needs care for a second reason: `asyncio` sets `IPV6_V6ONLY` on every `AF_INET6`
socket it binds, so a wildcard IPv6 bind serves IPv6 *only* and answers IPv4 with
ECONNREFUSED. Railway's health probe connects over IPv4. The symptom is silent — clean
startup, "Uvicorn running on http://[::]:8080", and not one request line in the log while
the deploy is killed on healthcheck timeout. The entrypoint binds the wildcard itself and
clears the option; a healthy probe shows up as `::ffff:100.64.0.2 - "GET /healthz" 200`,
an IPv4-mapped address.

### Seeding the demo organisation

A self-service signup at `/signup` deliberately starts **empty** — another tenant's records
are never a starting point — so the desk renders with `n_credits: 0`. The organisation that
shows numbers reads the committed synthetic corpus and must be created explicitly. Run it
inside the service, where `RZ_DATABASE_URL` is already present:

```bash
railway link                     # select this project / environment / service
RZ_ADMIN_PASSWORD='…' railway run \
  python scripts/bootstrap_admin.py --email you@example.com --org demo --dataset files
```

`--dataset files` is what makes the deployed demo show numbers immediately. Any
organisation holding real books stays on `sql` and ingests its own rows.

For an organisation that already exists — a self-service signup, say — use:

```bash
python scripts/set_org_dataset.py --org <slug> --dataset files
```

It is idempotent, so it is safe as a Railway **pre-deploy command**, which is how the
deployed demo was seeded: the command runs inside the service container, where
`RZ_DATABASE_URL` is already present, so the credential never has to leave the platform.
Clear the pre-deploy command afterwards — it names one organisation, and a deploy would
fail if that organisation were ever removed.

What a corpus organisation shows, and what it does not: the desk reports 248 credits with
per-credit proofs computed on request, and the headline scores come from the committed
evaluation artifacts. Its ledger is still empty, so "search completed" reads 0/248 and the
audit badge reads **audit not started** rather than *intact* — there is no chain to verify
until something is recorded. That is deliberate. The pipeline (`residual_zero.cli run`)
writes a SQLite ledger and has no PostgreSQL output, so a deployed organisation cannot yet
be given a recorded run.

---

## 7a-quater. Recording a reconciliation run

The per-credit results were always written to whichever backend the environment
configures — `init_db`, `open_audit`, `open_verify` and `open_exceptions` all go through
the storage engine, so a run inside `use_tenant` persists uniqueness, residual and
disposition into an organisation's PostgreSQL schema with its hash chain. What was missing
was the *run*: the record that a deterministic execution happened, over which dataset,
under which configuration, and whether it finished. Without it nobody can tell "searched
and found nothing" from "never searched".

```bash
# local, single-tenant, unchanged: writes the SQLite ledger under --out, records no run
python -m residual_zero.cli run --split dev

# one organisation, into whichever database the environment configures
RZ_DATABASE_URL=postgresql://... python -m residual_zero.cli run --org demo
```

`reconciliation_run` (migration `0002_run.sql`) holds run identity, the dataset and config
digests, status, counts and timings. It is owned by the **audit** writer, so the three
declared table owners stay three and the run row commits on the same connection as the
chain. `audit_entry.run_id` links entries to their run; it is nullable and sits outside the
hashed payload, so linking cannot change `entry_hash` and rows written before runs existed
remain valid results with no run row.

**Identity is a digest of organisation + dataset + configuration, never a timestamp.** The
same run twice must collide so the second can be refused; a clock would make every
execution unique by construction. Re-running a run that already *covers its dataset*
returns it and writes nothing — coverage is the test, not status, because a run that
stopped short still has credits nobody has computed.

### Run accounting: four numbers, not one

| column | question |
|---|---|
| `n_credits` | how many credits the run was asked to cover — the denominator |
| `n_computed` | how many *this invocation* computed. Invocation-local, and smaller than coverage whenever idempotency skipped work already done |
| `n_reused` | how many were already persisted and correctly skipped rather than recomputed |
| `n_persisted` | how many credits carry a persisted result for this run — **coverage** |

`n_persisted` is a `COUNT(DISTINCT …)` over `audit_entry`, never a tally accumulated in
Python: a counter and the rows it describes can disagree, and when they do the rows are
the ones that are true. This is not hypothetical — the first live run reported 231 while
248 credits carried results, because an interrupted attempt had persisted 17 of them and
the retry correctly skipped rather than duplicated them. The number was right about what
it measured and wrong about what its name implied.

**A run is COMPLETED only when `n_persisted = n_credits`**, restated as a CHECK constraint
so the database refuses to store a completion claim that is not true. A run that finished
its loop without covering the dataset is `PARTIAL`: its results are genuine, it is not a
failure, and a retry computes exactly the credits that are missing. Readers treat
`COMPLETED` and `PARTIAL` alike for *results* and never conflate them for *completeness*.

**A run is not recorded until persistence succeeds.** Production refuses to record a run
without PostgreSQL rather than write a local file and call it success, and the check runs
before the identity store is opened — otherwise the refusal creates the very local database
it is refusing to create. A failed run deletes its own entries and stays visible as
`FAILED`; readers exclude any run that never reached `COMPLETED`, because a partial run is
not a smaller run.

### Transaction pooling

Neon's pooled endpoint is PgBouncer in transaction mode, where **session state does not
survive between transactions**. `SET search_path` and `SET default_transaction_read_only`
were both session-level, and both leaked: the audit writes landed in the right schema while
the exception writes on an identically built connection raised `UndefinedTable`, and later
a writer inherited a reader's read-only marker. Neither failed cleanly.

Every transaction now re-establishes its own scope (`SET LOCAL search_path`, and
`SET TRANSACTION READ ONLY` for readers — `SET LOCAL default_transaction_read_only` sets
the default for *subsequent* transactions and leaves the current one writable). Startup
options are not an alternative: pgbouncer refuses the connection with "unsupported startup
parameter in options: search_path". Set `RZ_TEST_PGBOUNCER_URL` to run the pooled suite.

---

## 7b. Region co-location is a performance requirement, not a preference

Put the web service in the **same region as the database**. Residual Zero opens a
connection per read path rather than holding a pool, so latency is dominated by connection
setup, and connection setup is dominated by distance.

Measured on the production image, byte-identical code, six connections per credit page:

| | one fresh connection | login | `/api/desk` | credit page |
|---|---|---|---|---|
| Same host (~0 ms RTT) | 2.1 ms | 70 ms | 116 ms | **94 ms** |
| Across ~12,000 km | 2550 ms | 16.8 s | 11.5 s | **24.0 s** |

Neon's endpoint here is `us-east-2`, so the Render service is pinned to `ohio` in
`render.yaml`. If you move the database, move the service with it.

If a future workload needs more headroom than co-location gives, the next lever is
connection reuse (a pool), not a bigger timeout - and not a smaller AI budget.

## 8. Observability

One JSON object per line on stderr. Every value passes a scrubber that removes anything
credential-shaped — bearer tokens, API keys, password fields, connection-string passwords —
on the way out, so a caller who logs a whole request context by accident still cannot print
a secret. Events cover authentication, authorisation, CSRF refusals, provider failures,
database failures, unhandled requests and AI investigations.

Amounts, narrations and counterparty strings stay out of the logs. A credit *id* is logged,
because diagnosing "why did this credit fail" needs one and the id is not the money.

---

## 9. Operational notes

* **Backups.** `pg_dump` covers everything; the app holds no state outside PostgreSQL apart
  from the read-only committed corpus in the image.
* **Recreating production.** `scripts/migrate.py --shared`, then `bootstrap_admin.py`, then
  optionally `migrate_corpus.py`. No manual SQL, no hand-editing.
* **Rotating the AI key.** Change `NVIDIA_API_KEY` and restart. A missing or invalid key
  degrades to deterministic templates; it does not fail a request.
* **Adding a migration.** Add a new numbered file. Never edit an applied one.
* **Scaling.** One process serves the whole corpus. Before adding replicas, note that the
  audit chain's append takes a transaction-scoped advisory lock on PostgreSQL, so
  concurrent writers are safe but serialised at that point.
