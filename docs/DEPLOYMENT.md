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
