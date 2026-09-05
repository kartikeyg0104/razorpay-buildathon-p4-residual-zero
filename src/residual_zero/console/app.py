"""Ops console. FastAPI + Jinja. One write: exception resolution."""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from html import escape
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from residual_zero.appconfig import enforce_import_time, load_config
from residual_zero import obs
from residual_zero.audit import verify_chain
from residual_zero.console.security import (
    AuthMiddleware,
    HttpsRedirectMiddleware,
    SecurityHeadersMiddleware,
    actor_of,
    install_error_handlers,
    principal_of,
)
from residual_zero.config import MerchantProfile, config_digest, load_fees, load_profile, load_solver_config, load_tax_rates
from residual_zero.money import _group_indian
from residual_zero.console.facts import credit_forensic, forensic_summary, honesty_line, t04_view, track04_snapshot
from residual_zero.console.ops import build_overlay, greedy_versus_declared
from residual_zero.solver.alt_diff import diff_sets
from residual_zero.console.waterfall import waterfall_svg
from residual_zero.db import open_readonly
from residual_zero.exceptions import open_exceptions
from residual_zero.tenancy import cache_key as _tenant_cache_key, current_tenant
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.exceptions.narrate import TEMPLATES as DIAGNOSIS
from residual_zero.models import ExceptionClass, PoolScope, ProofRecord, Regime, Uniqueness
from residual_zero.money import format_rupees
from residual_zero.proof import render_proof
from residual_zero.verify import verify_decomposition

TEMPLATES = Path(__file__).resolve().parent.joinpath("templates")
STATIC = Path(__file__).resolve().parent.joinpath("static")

env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))


def _fmt_count(value: object) -> str:
    """Indian-grouped integer for display. Non-numeric input passes through unchanged.

    The throughput card rendered a bare "1549481" next to a carefully grouped
    "1,44,25,758.19", which read as two different systems on one screen.
    """
    text = str(value or "").strip()
    if not text.lstrip("-").isdigit():
        return text or "\u2014"
    sign = "-" if text.startswith("-") else ""
    return sign + _group_indian(text.lstrip("-"))


def _fmt_duration_ns(value: object) -> str:
    """Nanoseconds as a unit a human reads. "160053542ns" -> "160 ms"."""
    text = str(value or "").strip()
    if not text.isdigit():
        return text or "\u2014"
    ns = int(text)
    if ns < 1_000:
        return f"{ns} ns"
    if ns < 1_000_000:
        return f"{ns // 1_000} \u00b5s"
    if ns < 1_000_000_000:
        return f"{ns // 1_000_000} ms"
    if ns < 60_000_000_000:
        # Integer arithmetic only (NN-1): whole seconds plus one tenth, no float division.
        seconds, rest = divmod(ns, 1_000_000_000)
        tenths = rest // 100_000_000
        return f"{seconds} s" if tenths == 0 else f"{seconds}.{tenths} s"
    minutes, rest = divmod(ns, 60_000_000_000)
    return f"{minutes} min {rest // 1_000_000_000} s"


env.filters["count"] = _fmt_count
env.filters["duration_ns"] = _fmt_duration_ns
app = FastAPI(title="Residual Zero")

# ---------------------------------------------------------------- deployment wiring
#
# Origins are configuration, not literals. In local mode this resolves to the same
# loopback origins the desk always allowed; in production it is the deployment's own HTTPS
# origin plus the extension ids that were built against it. A regex over
# `chrome-extension://[a-z]+` used to admit EVERY installed extension, which on a public
# deployment would let any extension in the user's browser read this organisation's
# financial JSON.
# Enforced here, not only in __main__: `uvicorn residual_zero.console.app:app` imports
# this module without ever running the entry point's checks, and a production process
# with no RZ_DATABASE_URL would otherwise serve the development SQLite ledger.
enforce_import_time()
_CONFIG = load_config()
_CORS_ORIGINS = list(_CONFIG.cors_origins())
if _CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        # Cookies are never sent cross-origin to this API: the extension authenticates with
        # a bearer token instead, which is why SameSite=Lax can stay on the session cookie.
        allow_credentials=False,
        max_age=600,
    )

# Middleware runs in reverse registration order, so the effective request order is:
#   HTTPS redirect -> security headers -> authentication -> route.
# Authentication is registered last so it is innermost of the three: a rejected request has
# already had its security headers attached.
app.add_middleware(AuthMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(HttpsRedirectMiddleware)
install_error_handlers(app)

if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def _default_db() -> Path:
    from residual_zero.storage.config import sqlite_default_path

    return sqlite_default_path()


DB = _default_db()
"""Legacy single-tenant ledger path. Still a module attribute so the CLI, the eval harness
and every test that points the desk at a copy keep working by rebinding it."""

DEFAULT_RENDERED = Path("data").joinpath("dev", "rendered")
"""The committed synthetic dev corpus. Read-only, public in the repository, and the dataset
of the demo organisation. It is never another tenant's data."""


# ---------------------------------------------------------------- per-organisation caches
#
# These four accessors are how every route, every finance tool and the MCP registry reach
# the desk's data — about a hundred call sites. Making THEM organisation-aware, rather than
# threading a tenant argument through all of them, is what let multi-tenancy land without
# editing financial code. The cache is keyed by the tenant, so one organisation's loaded
# corpus can never be served to another.
_SPLIT_CACHE: dict[str, object] = {}
_OVERLAY_CACHE: dict[str, object] = {}


def reset_caches() -> None:
    """Drop every per-organisation cache. Used by tests and after an ingest."""
    _SPLIT_CACHE.clear()
    _OVERLAY_CACHE.clear()


def _ledger_is_untouched(conn) -> bool:
    """True when this schema holds no overlay rows at all.

    Only meaningful for an organisation that reads a file corpus: its records live in the
    committed files, and its storage exists to hold what the desk writes *about* them —
    exceptions and human decisions. Nothing there yet means nothing has been recorded yet.

    Both backends need this. ``bootstrap_tenant`` creates the SQLite ledger the moment the
    organisation is created, so "the file is missing" was never the signal for a tenant
    either — it only ever caught the single-tenant default database.
    """
    from residual_zero.storage.errors import QUERY_ERRORS, rollback_quietly

    try:
        for table in ("audit_entry", "exception"):
            row = conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
            if row is not None:
                return False
    except QUERY_ERRORS:
        # A schema that cannot answer is not a schema with data in it.
        rollback_quietly(conn)
        return True
    return True


def _db():
    """Read-only connection to the current organisation's ledger, or ``None``.

    ``None`` means "this organisation has no ledger yet", which every caller already
    handles — a freshly created organisation is legitimately empty.

    On SQLite that state is a missing file. PostgreSQL has no equivalent: the schema is
    created up front by the migrations, so a brand-new organisation returned a perfectly
    good connection to empty tables, and every caller took the database branch and
    reported zero instead of falling back to its corpus. An organisation reading the
    committed corpus therefore showed 248 credits on SQLite and 0 on PostgreSQL, from the
    same records — which is exactly what the deployed desk did. The signal is restored for
    the file-corpus case, where an empty schema genuinely means "nothing recorded yet";
    the first exception or decision written brings the database branch back, the same way
    the SQLite file springs into existence.

    An organisation on ``sql`` is left alone: its records *are* the schema, so empty means
    empty and there is nothing to fall back to.
    """
    from residual_zero.storage.config import Backend, storage_config

    tenant = current_tenant()
    if storage_config().backend is Backend.SQLITE:
        path = tenant.sqlite_path if tenant is not None else DB
        if not path.is_file():
            return None
        conn = open_readonly(path)
    else:
        conn = open_readonly()
    if tenant is not None and tenant.dataset_kind == "files" and _ledger_is_untouched(conn):
        conn.close()
        return None
    return conn


@lru_cache(maxsize=1)
def _profile() -> MerchantProfile:
    """Merchant profile. Configuration shipped with the build, identical for every tenant."""
    return load_profile(Path("config").joinpath("profiles").joinpath("phase1.yaml"))


def _load_split():
    """Load this organisation's source records, from files or from its own schema.

    Both paths produce the same canonical objects, so nothing downstream — candidate
    generation, the solver, the verifier — can tell which one ran.
    """
    tenant = current_tenant()
    if tenant is None or tenant.dataset_kind == "files":
        rendered = (tenant.files_root() if tenant is not None else None) or DEFAULT_RENDERED
        if not rendered.is_dir():
            return None
        root = SourceRoot(rendered)
        items = load_ledger_items(root)
        credits = load_bank_credits(root)
        declared = load_settlement_report(root)
    else:
        from residual_zero.ingest.sql_source import (
            load_bank_credits_sql,
            load_ledger_items_sql,
            load_settlement_report_sql,
        )

        conn = _db()
        if conn is None:
            return None
        try:
            items = load_ledger_items_sql(conn)
            credits = load_bank_credits_sql(conn)
            declared = load_settlement_report_sql(conn)
        except Exception as exc:
            # An organisation created before the source tables existed, or one whose
            # ingest has not run. "No data yet" is the honest answer and every caller
            # already handles it; a 500 would read as a defect in the desk.
            obs.warn("split.source_unavailable", error=type(exc).__name__)
            return None
        finally:
            conn.close()
        if not credits and not items:
            return None
    by_credit: dict[str, list] = {}
    for row in declared:
        by_credit.setdefault(row.credit_id, []).append(row)
    ledger = {it.id: it for it in items}
    credits_by_id = {c.id: c for c in credits}
    return items, credits, by_credit, ledger, credits_by_id


def _split():
    key = _tenant_cache_key()
    if key not in _SPLIT_CACHE:
        _SPLIT_CACHE[key] = _load_split()
    return _SPLIT_CACHE[key]


def _short_class(name: str) -> str:
    return name.replace("_", " ").title().replace("Decomposition", "decomp")


def _class_counts(classes: list[str]) -> list[dict[str, object]]:
    counted = Counter(c for c in classes if c)
    return [
        {"name": name, "n": n, "short": _short_class(name)}
        for name, n in counted.most_common()
    ]


def _overlay():
    key = _tenant_cache_key()
    if key not in _OVERLAY_CACHE:
        _OVERLAY_CACHE[key] = _build_overlay_now()
    return _OVERLAY_CACHE[key]


def _build_overlay_now():
    split = _split()
    if split is None:
        return None
    _items, credits, by_credit, ledger, _by_id = split
    rates, fees = load_tax_rates(), load_fees()
    return build_overlay(credits, by_credit, ledger, rates, fees, _profile().reserve_bps)


def _honesty_now(n_human: int | None = None) -> str:
    overlay = _overlay()
    split = _split()
    n_posted = len(split[1]) if split is not None else 0
    n_gate = overlay.n_ok if overlay is not None else 0
    n_journal = overlay.n_journalable if overlay is not None else 0
    if n_human is None:
        n_human = n_posted - n_gate if n_posted >= n_gate else 0
    return honesty_line(n_posted, n_gate, n_journal, n_human)


def _render(template: str, **kw) -> HTMLResponse:
    if "honesty" not in kw:
        kw["honesty"] = _honesty_now(kw.get("n_human") if isinstance(kw.get("n_human"), int) else None)
    from residual_zero.console.clear_gate import THESIS

    kw.setdefault("thesis", THESIS)
    return HTMLResponse(env.get_template(template).render(**kw))


def _credit_lookup() -> dict:
    split = _split()
    if split is None:
        return {}
    return split[4]


def _enrich(credit_id: str, cls: str, audit: dict | None) -> dict[str, str]:
    credit = _credit_lookup().get(credit_id)
    amount = format_rupees(credit.amount_paise) if credit is not None else ""
    account = credit.account_id if credit is not None else ""
    value_date = credit.value_date.isoformat() if credit is not None else ""
    uniqueness = ""
    if audit:
        uniqueness = str(audit.get("uniqueness") or "")
        if not cls:
            cls = str(audit.get("exception_class") or "")
    gate = "REFUSED"
    if audit and audit.get("disposition") == "CLEARED":
        gate = "GATE_B"
    overlay = _overlay()
    if overlay is not None:
        found = overlay.by_id.get(credit_id)
        if found is not None and found.ok:
            gate = "GATE_A"
    utr = credit.utr or "" if credit is not None else ""
    narration = credit.narration_raw if credit is not None else ""
    return {
        "id": credit_id,
        "cls": cls,
        "amount": amount,
        "account": account,
        "value_date": value_date,
        "uniqueness": uniqueness,
        "gate": gate,
        "utr": utr,
        "narration": narration,
    }


def _load_work(conn) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    try:
        for cid, assignee, note, status in conn.execute(
            "SELECT bank_credit_id, assignee, note, status FROM exception_work"
        ):
            out[str(cid)] = {
                "assignee": str(assignee),
                "note": str(note),
                "status": str(status),
            }
    # QUERY_ERRORS, not sqlite3.OperationalError: the equivalent PostgreSQL error is a
    # different class, so a name-based except stopped degrading the moment Postgres
    # became a backend and a missing table became a 500. rollback_quietly clears the
    # aborted transaction Postgres leaves behind, so the next query on this connection
    # can still run.
    except QUERY_ERRORS:
        rollback_quietly(conn)
        return {}
    return out


def _load_audits(conn) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for (payload,) in conn.execute("SELECT payload FROM audit_entry ORDER BY seq"):
        data = json.loads(payload)
        cid = data.get("bank_credit_id")
        if cid:
            out[str(cid)] = data
    return out


def _neighbors(credit_id: str, ids: list[str]) -> tuple[str | None, str | None]:
    try:
        idx = ids.index(credit_id)
    except ValueError:
        return None, None
    prev_id = ids[idx - 1] if idx > 0 else None
    next_id = ids[idx + 1] if idx + 1 < len(ids) else None
    return prev_id, next_id


def _kind_rows(lines) -> list[dict[str, object]]:
    signed: dict[str, int] = {}
    mags: Counter[str] = Counter()
    for line in lines:
        signed[line.label] = signed.get(line.label, 0) + line.amount_paise
        mags[line.label] += abs(line.amount_paise)
    peak = max(mags.values()) if mags else 1
    return [
        {
            "label": label,
            "amount": format_rupees(signed[label]),
            "width_pct": (mags[label] * 100) // peak,
        }
        for label, _n in mags.most_common()
    ]


def _diagnosis(exc_class: str, residual: str, uniqueness: str) -> str:
    if not exc_class:
        return ""
    try:
        template = DIAGNOSIS[ExceptionClass(exc_class)]
    except ValueError:
        return exc_class
    filled = template
    for key, value in {
        "DELTA": residual or "—",
        "GROSS": "pool gross",
        "PCT": "configured rate",
        "ALTERNATES": uniqueness or "—",
        "DUPLICATES": "—",
    }.items():
        filled = filled.replace("{" + key + "}", value)
    return filled


@app.get("/", response_class=HTMLResponse)
def batch():
    conn = _db()
    raw_rows: list[tuple[str, str]] = []
    n_credits = 0
    n_flagged = 0
    n_cleared = 0
    n_zero = 0
    n_gate_a = 0
    flagged_paise = 0
    # None means "there is no chain to verify", which is not the same claim as
    # "the chain verified". Defaulting to True made a corpus organisation — one
    # with no ledger at all — render "audit intact", asserting a verification that
    # never ran. On a desk whose whole premise is deterministic proof, that is the
    # one thing the badge must not do.
    chain_ok: bool | None = None
    head = ""
    audits: dict[str, dict] = {}
    if conn is not None:
        try:
            n_credits = conn.execute("SELECT COUNT(*) FROM audit_entry").fetchone()[0]
            n_flagged = conn.execute("SELECT COUNT(*) FROM exception").fetchone()[0]
            # An empty chain verifies vacuously. Reporting that as "intact" is a claim
            # about evidence that does not exist, so say nothing instead.
            if n_credits:
                chain_ok, _broken, head = verify_chain(conn)
            raw_rows = list(
                conn.execute(
                    "SELECT bank_credit_id, exception_class FROM exception ORDER BY bank_credit_id"
                )
            )
            audits = _load_audits(conn)
        finally:
            conn.close()
    elif (split := _split()) is not None:
        _items, credits, _by, _ledger, _by_id = split
        n_credits = len(credits)
        raw_rows = [(c.id, "") for c in credits]

    lookup = _credit_lookup()
    rows = []
    for cid, cls in raw_rows:
        rows.append(_enrich(cid, cls, audits.get(cid)))
        credit = lookup.get(cid)
        if credit is not None:
            flagged_paise += credit.amount_paise
        payload = audits.get(cid) or {}
        if payload.get("disposition") == "CLEARED":
            n_cleared += 1
        if payload.get("residual_paise") == 0:
            n_zero += 1
    overlay = _overlay()
    if overlay is not None:
        n_gate_a = overlay.n_ok
        n_zero = overlay.n_residual_zero
    gate_rank = {"REFUSED": 0, "GATE_A": 1, "GATE_B": 2}
    rows.sort(key=lambda r: (gate_rank.get(str(r.get("gate") or ""), 9), r["id"]))
    n_human = sum(1 for r in rows if r.get("gate") == "REFUSED")
    human_paise = 0
    for r in rows:
        if r.get("gate") != "REFUSED":
            continue
        credit = lookup.get(r["id"])
        if credit is not None:
            human_paise += credit.amount_paise
    gate_counts = _class_counts([r["gate"] for r in rows if r.get("gate")])
    # Three different provenances land on this page and a bare 0 cannot tell them apart.
    #   * the committed evaluation run  — the same for every organisation
    #   * this organisation's records   — its posted credits, read through the overlay
    #   * this organisation's own run   — search, uniqueness, audit chain
    # A deployed organisation has the first two and not the third, because the pipeline
    # writes a SQLite ledger and has no PostgreSQL output. Rendering that as
    # "search completed 0/0" and "ambiguous 0" claims a search ran and found nothing.
    has_records = bool(rows)
    search_recorded = bool(audits)
    # The run that produced those results, when one was recorded. Read from the same
    # connection the results came from, and never invented: an organisation that has not
    # reconciled has no row and the page keeps saying "not run".
    recorded_run = None
    if search_recorded:
        from residual_zero.audit import latest_completed_run
        from residual_zero.storage.errors import QUERY_ERRORS, rollback_quietly

        probe = _db()
        if probe is not None:
            try:
                recorded_run = latest_completed_run(probe)
            except QUERY_ERRORS:
                rollback_quietly(probe)
            finally:
                probe.close()
    uniq = Counter(str(payload.get("uniqueness") or "") for payload in audits.values())
    snap = track04_snapshot()
    from residual_zero.qa.finance_templates import batch_insight_text
    from residual_zero.qa.finance_tools import get_reconciliation_statistics
    from residual_zero.qa.evidence_ops import root_cause

    try:
        insight = batch_insight_text(get_reconciliation_statistics())
    except Exception:
        insight = ""
    try:
        root_text = str(root_cause().get("text") or "")
    except Exception:
        root_text = ""

    return _render(
        "batch.html",
        active="batch",
        n_credits=n_credits,
        n_flagged=n_flagged,
        n_cleared=n_cleared,
        n_zero=n_zero,
        n_gate_a=n_gate_a,
        n_human=n_human,
        n_mismatch=overlay.n_mismatch if overlay is not None else 0,
        n_journalable=overlay.n_journalable if overlay is not None else 0,
        human_rupees=format_rupees(human_paise) if human_paise else "",
        flagged_rupees=format_rupees(flagged_paise) if flagged_paise else "",
        chain_ok=chain_ok,
        head=head or "",
        rows=rows,
        class_counts=_class_counts([r["cls"] for r in rows]),
        gate_counts=gate_counts,
        t04=snap,
        t04_dev=t04_view("dev"),
        t04_test=t04_view("test"),
        n_unique=uniq.get("UNIQUE", 0),
        n_ambiguous=uniq.get("AMBIGUOUS", 0),
        n_none_found=uniq.get("NONE_FOUND", 0),
        n_budget_search=uniq.get("BUDGET_EXCEEDED", 0),
        has_records=has_records,
        search_recorded=search_recorded,
        recorded_run=recorded_run,
        forensic=forensic_summary(),
        ai_insight=insight,
        ai_root_cause=root_text,
    )


@app.get("/credit/{credit_id}", response_class=HTMLResponse)
def credit_view(credit_id: str):
    from residual_zero.console.mixed_desk import is_mixed_credit, mixed_credit_context

    if is_mixed_credit(credit_id):
        ctx = mixed_credit_context(credit_id)
        if ctx is not None:
            return _render("credit.html", **ctx)
    rec = None
    exc_class = ""
    audit = None
    ids: list[str] = []
    resolution = ""
    work: dict[str, str] = {}
    conn = _db()
    if conn is not None:
        try:
            rec = conn.execute(
                "SELECT bank_credit_id, claimed_total_paise, residual_paise, disposition "
                "FROM reconciliation WHERE bank_credit_id = ?",
                (credit_id,),
            ).fetchone()
            exc = conn.execute(
                "SELECT exception_class FROM exception WHERE bank_credit_id = ?",
                (credit_id,),
            ).fetchone()
            exc_class = exc[0] if exc else ""
            payload_row = conn.execute(
                "SELECT payload FROM audit_entry "
                "WHERE json_extract(payload, '$.bank_credit_id') = ? "
                "ORDER BY seq DESC LIMIT 1",
                (credit_id,),
            ).fetchone()
            if payload_row:
                audit = json.loads(payload_row[0])
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT bank_credit_id FROM exception ORDER BY bank_credit_id"
                )
            ]
            try:
                resolved = conn.execute(
                    "SELECT resolution FROM exception_resolution WHERE bank_credit_id = ?",
                    (credit_id,),
                ).fetchone()
                resolution = str(resolved[0]) if resolved else ""
            except QUERY_ERRORS:
                rollback_quietly(conn)
                resolution = ""
            work_rows = _load_work(conn)
            work = work_rows.get(credit_id, {})
        finally:
            conn.close()

    split = _split()
    waterfall = ""
    proof_text = ""
    uniqueness = ""
    residual = ""
    regime = ""
    amount = format_rupees(rec[1]) if rec else ""
    account = ""
    value_date = ""
    narration = ""
    utr = ""
    currency = "INR"
    n_members = 0
    kind_rows: list[dict[str, object]] = []
    identity_ok = False
    identity_lines = ""
    posted_sum = ""
    gate_a_ok = False
    gate_a_residual = ""
    gate_a_deltas = 0
    posted_mismatch = False
    greedy_cmp: dict[str, object] | None = None
    if audit:
        uniqueness = str(audit.get("uniqueness") or "")
        regime = str(audit.get("regime") or "")
        if audit.get("residual_paise") is not None:
            residual = format_rupees(int(audit["residual_paise"]))
        if not exc_class:
            exc_class = str(audit.get("exception_class") or "")
    if split is not None:
        _items, credits, by_credit, ledger, credits_by_id = split
        if not ids:
            ids = [c.id for c in credits]
        credit = credits_by_id.get(credit_id)
        if credit is not None:
            amount = format_rupees(credit.amount_paise)
            account = credit.account_id
            value_date = credit.value_date.isoformat()
            narration = credit.narration_raw
            utr = credit.utr or ""
            currency = credit.currency
            rates, fees = load_tax_rates(), load_fees()
            reserve_bps = _profile().reserve_bps
            declared = by_credit.get(credit.id, ())
            uniq_enum = Uniqueness.AMBIGUOUS
            if uniqueness:
                try:
                    uniq_enum = Uniqueness(uniqueness)
                except ValueError:
                    uniq_enum = Uniqueness.AMBIGUOUS
            if declared:
                member_ids = tuple(r.item_id for r in declared if r.item_id in ledger)
                n_members = len(member_ids)
                outcome = verify_decomposition(
                    credit, member_ids, ledger, Regime.A_DECLARED, rates, fees, reserve_bps=reserve_bps
                )
                proof = ProofRecord(
                    bank_credit_id=credit.id,
                    lines=outcome.derived_lines,
                    computed_total_paise=credit.amount_paise - outcome.residual_paise,
                    residual_paise=outcome.residual_paise,
                    regime=Regime.A_DECLARED,
                    uniqueness=uniq_enum,
                    alternate_count=0,
                    pool_size=0,
                    pool_scope=PoolScope.FULL,
                    rate_config_digest=config_digest(rates, fees),
                )
                proof_text = render_proof(proof, credit)
                waterfall = waterfall_svg(proof, credit)
                residual = format_rupees(outcome.residual_paise)
                regime = Regime.A_DECLARED.value
                kind_rows = _kind_rows(outcome.derived_lines)
                identity_lines = format_rupees(credit.amount_paise - outcome.residual_paise)
                identity_ok = True
                posted_sum = format_rupees(sum(line.amount_paise for line in outcome.derived_lines))
                overlay = _overlay()
                if overlay is not None:
                    found = overlay.by_id.get(credit.id)
                    if found is not None:
                        gate_a_ok = found.ok
                        gate_a_residual = format_rupees(found.residual_paise)
                        gate_a_deltas = found.n_deltas
                        posted_mismatch = found.ok and credit.id not in overlay.journalable
                hit = greedy_versus_declared(
                    credit, _items, load_solver_config(), member_ids,
                )
                rival = diff_sets(member_ids, hit.member_ids)
                greedy_cmp = {
                    "would_clear": hit.would_clear,
                    "same": hit.same_as_declared,
                    "n": len(hit.member_ids),
                    "only_declared": list(rival.only_a[:12]),
                    "only_greedy": list(rival.only_b[:12]),
                    "shared": len(rival.shared),
                    "symdiff": rival.symmetric_difference_size,
                    "more_declared": max(0, len(rival.only_a) - 12),
                    "more_greedy": max(0, len(rival.only_b) - 12),
                }
            else:
                empty = ProofRecord(
                    bank_credit_id=credit.id,
                    lines=(),
                    computed_total_paise=0,
                    residual_paise=credit.amount_paise,
                    regime=Regime.B_SEARCHED,
                    uniqueness=uniq_enum,
                    alternate_count=0,
                    pool_size=0,
                    pool_scope=PoolScope.FULL,
                    rate_config_digest=config_digest(rates, fees),
                )
                waterfall = waterfall_svg(empty, credit)
                proof_text = (
                    f"PROOF  {credit.id}\n"
                    f"regime      B_SEARCHED\n"
                    f"uniqueness  {uniqueness or uniq_enum.value}\n"
                    f"credit      {format_rupees(credit.amount_paise)}\n"
                    "no declared member set — search did not auto-clear\n"
                )
                residual = format_rupees(credit.amount_paise) if not residual else residual
                regime = Regime.B_SEARCHED.value

    prev_id, next_id = _neighbors(credit_id, ids)
    four_way = None
    residual_paise = None
    causal = ()
    sla_age = None
    sla_bucket = ""
    if split is not None and credit_id in split[4]:
        from residual_zero.console.close_ops import (
            causal_chain,
            corpus_as_of,
            four_way_identity,
            sla_age_days,
            sla_bucket_name,
        )

        credit_obj = split[4][credit_id]
        declared_rows = split[2].get(credit_id, ())
        overlay_now = _overlay()
        residual_paise = None
        if overlay_now is not None:
            found = overlay_now.by_id.get(credit_id)
            if found is not None:
                residual_paise = found.residual_paise
        four_way = four_way_identity(credit_obj, declared_rows, split[3], residual_paise)
        causal = causal_chain(declared_rows)
        as_of = corpus_as_of(split[1])
        if as_of is not None:
            sla_age = sla_age_days(credit_obj.value_date, as_of)
            sla_bucket = sla_bucket_name(sla_age)
    mcp_credit: dict | None = None
    if split is not None and credit_id in split[4]:
        from residual_zero.mcp.registry import credit_preview

        mcp_credit = credit_preview(credit_id, set(split[3].keys()))
    from residual_zero.qa.evidence_ops import evidence_level, next_best_action

    try:
        level_blob = evidence_level(credit_id)
        action_blob = next_best_action(credit_id)
    except Exception:
        level_blob = {"level": 0, "label": "NO_EVIDENCE", "potentially_recoverable": False}
        action_blob = {"action": "Leave flagged. Overlay does not write CLEARED.", "writes_cleared": False}
    from residual_zero.console.clear_gate import auto_clear_decision
    from residual_zero.console.ops_pack import dispute_draft, playbook_for, three_way, utr_siblings

    playbook = playbook_for(exc_class)
    tw = None
    draft = ""
    siblings = {"utr": "", "n": 0, "ids": [], "writes_cleared": False}
    if split is not None and credit_id in split[4]:
        tw = three_way(split[4][credit_id], split[2].get(credit_id, ()), split[3])
        draft = dispute_draft(
            split[4][credit_id],
            uniqueness,
            residual or format_rupees(split[4][credit_id].amount_paise),
            playbook,
        )
        siblings = utr_siblings(split[1], credit_id)
    return _render(
        "credit.html",
        active="credit",
        credit_id=credit_id,
        row=rec,
        amount=amount,
        account=account,
        value_date=value_date,
        narration=narration,
        utr=utr,
        currency=currency,
        n_members=n_members,
        kind_rows=kind_rows,
        exception_class=exc_class,
        uniqueness=uniqueness,
        residual=residual,
        regime=regime,
        waterfall=waterfall,
        proof_text=proof_text,
        matched_rule=(audit or {}).get("matched_rule") or "",
        disposition=(audit or {}).get("disposition") or "",
        prev_id=prev_id,
        next_id=next_id,
        gates=list((audit or {}).get("trace_gates") or []),
        diagnosis=_diagnosis(exc_class, residual, uniqueness),
        identity_ok=identity_ok,
        identity_lines=identity_lines,
        posted_sum=posted_sum,
        gate_a_ok=gate_a_ok,
        gate_a_residual=gate_a_residual,
        gate_a_deltas=gate_a_deltas,
        posted_mismatch=posted_mismatch,
        greedy=greedy_cmp,
        mcp=mcp_credit,
        resolution=resolution,
        auto_cleared=((audit or {}).get("disposition") == "CLEARED"),
        why=credit_forensic(credit_id),
        evidence_level=level_blob,
        next_action=action_blob,
        four_way=four_way,
        causal=causal,
        sla_age=sla_age,
        sla_bucket=sla_bucket,
        three_way=tw,
        dispute_draft=draft,
        playbook=playbook,
        work=work,
        utr_siblings=siblings,
        clear_decision=auto_clear_decision(
            residual_paise=residual_paise,
            uniqueness=uniqueness or "AMBIGUOUS",
            pool_scope=str((audit or {}).get("pool_scope") or "FULL"),
            ordering_score=str((audit or {}).get("ordering_score") or "") or None,
            disposition=str((audit or {}).get("disposition") or "FLAGGED"),
        ),
        proof=_official_proof(credit_id),
        architecture=True,
    )


def _official_proof(credit_id: str) -> dict:
    from residual_zero.console.proof_explorer import official_proof

    return official_proof(credit_id)


@app.get("/exceptions", response_class=HTMLResponse)
def exceptions():
    conn = _db()
    raw_rows: list[tuple[str, str]] = []
    audits: dict[str, dict] = {}
    resolutions: dict[str, str] = {}
    works: dict[str, dict[str, str]] = {}
    if conn is not None:
        try:
            raw_rows = list(
                conn.execute(
                    "SELECT bank_credit_id, exception_class FROM exception ORDER BY bank_credit_id"
                )
            )
            audits = _load_audits(conn)
            try:
                resolutions = {
                    str(cid): str(res)
                    for cid, res in conn.execute(
                        "SELECT bank_credit_id, resolution FROM exception_resolution"
                    )
                }
            except QUERY_ERRORS:
                rollback_quietly(conn)
                resolutions = {}
            works = _load_work(conn)
        finally:
            conn.close()
    from residual_zero.console.ops_pack import playbook_for

    rows = [_enrich(cid, cls, audits.get(cid)) for cid, cls in raw_rows]
    for row in rows:
        row["resolution"] = resolutions.get(row["id"], "")
        row["playbook"] = playbook_for(row["cls"])
        found_work = works.get(row["id"], {})
        row["assignee"] = found_work.get("assignee", "")
        row["note"] = found_work.get("note", "")
        row["work_status"] = found_work.get("status", "open")
    human_rows = [r for r in rows if r.get("gate") == "REFUSED"]
    proven_rows = [r for r in rows if r.get("gate") == "GATE_A"]
    from residual_zero.console.close_ops import corpus_as_of
    from residual_zero.console.ops_pack import exposure_queue

    split = _split()
    exposure = {"n": 0, "rows": [], "note": "", "writes_cleared": False}
    if split is not None:
        exposure = exposure_queue(split[1], _overlay(), corpus_as_of(split[1]), limit=5)
    # Presentation only: the playbook is per-class guidance, so it is shown once as a
    # legend instead of being repeated on every queue card.
    from residual_zero.console.ops_pack import PLAYBOOKS

    present = []
    for cls in dict.fromkeys(str(r.get("cls") or "") for r in human_rows):
        text = PLAYBOOKS.get(cls)
        if cls and text:
            present.append((cls, text))
    return _render(
        "exceptions.html",
        active="exceptions",
        rows=rows,
        human_rows=human_rows,
        proven_rows=proven_rows,
        class_counts=_class_counts([r["cls"] for r in human_rows]),
        n_human=len(human_rows),
        n_gate_a=len(proven_rows),
        exposure=exposure,
        playbooks=present,
    )


def _exceptions_conn():
    """Write connection for the exception queue, scoped to the current organisation."""
    from residual_zero.storage.config import Backend, storage_config

    tenant = current_tenant()
    if storage_config().backend is Backend.SQLITE:
        return open_exceptions(tenant.sqlite_path if tenant is not None else DB)
    return open_exceptions(None)


def _known_exception(credit_id: str) -> bool:
    """True when the id names a row in the exception queue this overlay is allowed to annotate."""
    conn = _db()
    if conn is None:
        return False
    try:
        row = conn.execute(
            "SELECT 1 FROM exception WHERE bank_credit_id = ?", (credit_id,)
        ).fetchone()
    finally:
        conn.close()
    return row is not None


# "Loopback" was never an authorisation boundary: any page the operator visits can make
# their browser POST here. CORS does not stop that — it only withholds the *response*, so a
# cross-site write still lands (confirmed 2026-09). A form content-type keeps the request
# "simple", so there is no preflight to fail, and the two resolution fields are query
# params. Origin enforcement is the fix that matches the threat.
#
# The allowlist is now configuration (`RZ_PUBLIC_ORIGIN` / `RZ_ALLOWED_ORIGINS`) rather than
# two hardcoded loopback URLs, because behind a real domain the hardcoded pair would refuse
# the deployment's own console. In local mode the resolved set is exactly the old pair, so
# the existing regression tests still describe the behaviour they were written for.


def _write_origins() -> frozenset[str]:
    """Origins allowed to make a cookie-authenticated write, for this deployment."""
    return load_config().write_origins()


# Kept as a module attribute for the regression test that asserts the allowlist is narrow.
WRITE_ORIGINS = _write_origins()


def _foreign_origin(request: Request) -> HTMLResponse | None:
    """403 for a write from an origin this deployment does not own.

    In local single-tenant mode a missing Origin still means a non-browser client (curl,
    the CLI, the test suite) and is allowed through. Under `RZ_AUTH_MODE=required` that
    inference is withdrawn for cookie writes and a bearer token is required instead — see
    `console.security.origin_allowed`, which the auth middleware applies to every write
    before the route body runs.
    """
    from residual_zero.console.security import origin_allowed

    config = load_config()
    origin = request.headers.get("origin")
    if origin_allowed(origin, config, principal_of(request)):
        return None
    return HTMLResponse(
        f"<p>refused: {escape(origin or '(no origin)')} may not write to this desk</p>",
        status_code=403,
    )


@app.post("/exceptions/{credit_id}/resolve", response_class=HTMLResponse)
def resolve_exception(request: Request, credit_id: str, resolution: str = "escalate"):
    refused = _foreign_origin(request)
    if refused is not None:
        return refused
    from residual_zero.console.ops_pack import normalise_resolution

    try:
        resolution = normalise_resolution(resolution)
    except ValueError as exc:
        return HTMLResponse(f"<p>{escape(str(exc))}</p>", status_code=400)
    if not _known_exception(credit_id):
        return HTMLResponse(
            f"<p>unknown exception {escape(credit_id)}</p>", status_code=404
        )
    from residual_zero.exceptions import record_resolution

    conn = _exceptions_conn()
    try:
        record_resolution(conn, credit_id, resolution, actor_of(request))
    finally:
        conn.close()
    obs.event(
        "review.resolution", credit_id=credit_id, resolution=resolution,
        actor=actor_of(request), writes_cleared=False,
    )
    return HTMLResponse(f"<p>resolved {escape(credit_id)} as {escape(resolution)}</p>")


@app.post("/exceptions/{credit_id}/work", response_class=HTMLResponse)
def save_exception_work(
    request: Request, credit_id: str, assignee: str = "", note: str = "", status: str = "open",
):
    refused = _foreign_origin(request)
    if refused is not None:
        return refused
    from residual_zero.console.ops_pack import normalise_work_status

    try:
        status = normalise_work_status(status)
    except ValueError as exc:
        return HTMLResponse(f"<p>{escape(str(exc))}</p>", status_code=400)
    if not _known_exception(credit_id):
        return HTMLResponse(
            f"<p>unknown exception {escape(credit_id)}</p>", status_code=404
        )
    assignee, note = assignee.strip(), note.strip()
    from residual_zero.exceptions import record_work

    conn = _exceptions_conn()
    try:
        record_work(conn, credit_id, assignee, note, status, actor_of(request))
    finally:
        conn.close()
    obs.event(
        "review.work", credit_id=credit_id, status=status,
        actor=actor_of(request), writes_cleared=False,
    )
    return HTMLResponse(
        f"<p>work {escape(credit_id)} · {escape(status)} · "
        f"assignee {escape(assignee) or '—'} (does not write CLEARED)</p>"
    )


@app.get("/audit", response_class=HTMLResponse)
def audit():
    conn = _db()
    ok, broken, head, n = True, None, "", 0
    chain: list[str] = []
    recent: list[dict[str, object]] = []
    uniq_counts: Counter[str] = Counter()
    if conn is not None:
        try:
            ok, broken, head = verify_chain(conn)
            entries = list(conn.execute("SELECT seq, payload FROM audit_entry ORDER BY seq"))
            n = len(entries)
            for seq, payload in entries:
                data = json.loads(payload)
                u = str(data.get("uniqueness") or "")
                chain.append(u)
                if u:
                    uniq_counts[u] += 1
            for seq, payload in reversed(entries[-12:]):
                data = json.loads(payload)
                residual_paise = int(data.get("residual_paise") or 0)
                recent.append(
                    {
                        "seq": seq,
                        "credit_id": data.get("bank_credit_id") or "",
                        "uniqueness": data.get("uniqueness") or "",
                        "disposition": data.get("disposition") or "",
                        "residual": format_rupees(residual_paise),
                    }
                )
        finally:
            conn.close()
    uniq_mix = " · ".join(f"{name} {count}" for name, count in uniq_counts.most_common())
    return _render(
        "audit.html",
        active="audit",
        ok=ok,
        broken=broken,
        head=head or "",
        n=n,
        chain=chain,
        recent=recent,
        uniq_mix=uniq_mix,
    )


@app.get("/explorer", response_class=HTMLResponse)
def explorer(kind: str = "MISSING_SETTLEMENT"):
    """AI reconciliation explorer. Read-only structured queries. Never writes CLEARED."""
    from residual_zero.qa.evidence_ops import explorer_query, potentially_recoverable, root_cause

    wanted = (kind or "").strip() or "MISSING_SETTLEMENT"
    try:
        result = explorer_query(wanted, 40)
    except Exception:
        result = {"kind": wanted, "n": 0, "rows": [], "writes_cleared": False}
    try:
        recoverable = potentially_recoverable(20)
    except Exception:
        recoverable = {"n": 0, "rows": [], "writes_cleared": False}
    try:
        root = root_cause()
    except Exception:
        root = {"text": "", "proposals": [], "writes_cleared": False}
    return _render(
        "explorer.html",
        active="explorer",
        kind=wanted,
        result=result,
        recoverable=recoverable,
        root=root,
    )


# ---------------------------------------------------------------- deployment probes
#
# `/api/health` reports credit counts, gate totals and provider state, so it stays behind
# authentication. A load balancer needs something it can call without a credential, and
# that something must not describe anybody's finances — hence two probes that report only
# whether this process can serve.


@app.get("/healthz")
def healthz():
    """Liveness. No financial data, no organisation, no configuration."""
    return JSONResponse({"ok": True, "service": "residual-zero"})


@app.get("/readyz")
def readyz():
    """Readiness: is the configuration valid and is the database reachable?

    Reports the *names* of misconfigured variables, never their values, so a failing
    deployment is diagnosable from the probe without the probe becoming a disclosure.
    """
    from residual_zero.appconfig import config_errors, load_config

    config = load_config()
    problems = list(config_errors(config))
    database_ok = True
    try:
        conn = _db()
        if conn is not None:
            conn.close()
    except Exception as exc:
        database_ok = False
        obs.error("readyz.database_unreachable", exc)
        problems.append("database is not reachable")
    ready = not problems
    return JSONResponse(
        {
            "ok": ready,
            "ready": ready,
            "env": config.env.value,
            "auth_mode": config.auth_mode.value,
            "database_ok": database_ok,
            "problems": problems,
            "writes_cleared": False,
        },
        status_code=200 if ready else 503,
    )


from residual_zero.console.auth_routes import mount_auth
from residual_zero.console.extra import mount
from residual_zero.storage.errors import QUERY_ERRORS, rollback_quietly

mount(app)
mount_auth(app)
