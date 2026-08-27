"""Ops console. FastAPI + Jinja. One write: exception resolution."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from residual_zero.audit import verify_chain
from residual_zero.db import open_readonly
from residual_zero.exceptions import open_exceptions
from residual_zero.money import format_rupees

TEMPLATES = Path(__file__).resolve().parent.joinpath("templates")
STATIC = Path(__file__).resolve().parent.joinpath("static")

env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
app = FastAPI()
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

DB = Path("artifacts/dev/cp5/ledger.sqlite")


def _db():
    return open_readonly(DB)


@app.get("/", response_class=HTMLResponse)
def batch():
    conn = _db()
    try:
        n = conn.execute("SELECT COUNT(*) FROM reconciliation").fetchone()[0]
        flagged = conn.execute("SELECT COUNT(*) FROM exception").fetchone()[0]
        ok, _broken, head = verify_chain(conn)
        html = env.get_template("batch.html").render(
            n_credits=n, n_flagged=flagged, chain_ok=ok, head=head or "",
        )
        return HTMLResponse(html)
    finally:
        conn.close()


@app.get("/credit/{credit_id}", response_class=HTMLResponse)
def credit_view(credit_id: str):
    conn = _db()
    try:
        row = conn.execute(
            "SELECT bank_credit_id, claimed_total_paise, residual_paise, disposition FROM reconciliation WHERE bank_credit_id = ?",
            (credit_id,),
        ).fetchone()
        html = env.get_template("credit.html").render(
            credit_id=credit_id,
            row=row,
            amount=format_rupees(row[1]) if row else "",
        )
        return HTMLResponse(html)
    finally:
        conn.close()


@app.get("/exceptions", response_class=HTMLResponse)
def exceptions():
    conn = _db()
    try:
        rows = conn.execute("SELECT bank_credit_id, exception_class FROM exception ORDER BY bank_credit_id").fetchall()
        html = env.get_template("exceptions.html").render(rows=rows)
        return HTMLResponse(html)
    finally:
        conn.close()


@app.post("/exceptions/{credit_id}/resolve", response_class=HTMLResponse)
def resolve_exception(credit_id: str, resolution: str = "escalate"):
    conn = open_exceptions(DB)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO exception_resolution (bank_credit_id, resolution) VALUES (?, ?)",
            (credit_id, resolution),
        )
        conn.commit()
    finally:
        conn.close()
    return HTMLResponse(f"<p>resolved {credit_id} as {resolution}</p>")


@app.get("/audit", response_class=HTMLResponse)
def audit():
    conn = _db()
    try:
        ok, broken, head = verify_chain(conn)
        n = conn.execute("SELECT COUNT(*) FROM audit_entry").fetchone()[0]
        html = env.get_template("audit.html").render(ok=ok, broken=broken, head=head or "", n=n)
        return HTMLResponse(html)
    finally:
        conn.close()
