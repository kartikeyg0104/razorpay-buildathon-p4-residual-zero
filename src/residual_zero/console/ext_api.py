"""JSON surface for the browser extension. Read-only. Never writes CLEARED."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from residual_zero.ingest.razorpay import parse_recon_combined
from residual_zero.ingest.mcp_settlements import (
    ALLOWED_TOOLS,
    REFUSED_TOOLS,
    load_adapter_flags,
    match_recon_to_ledger,
)
from residual_zero.mcp.protocol import handle_rpc
from residual_zero.mcp.registry import DESK_TOOLS, call_tool, list_tools
from residual_zero.money import format_rupees

DEMO_CREDIT = "crd_001_acc_01_2025-01-09"


def preview_recon(payload: dict, ledger_ids: set[str] | None = None) -> dict:
    """Parse recon JSON. Never writes."""
    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")
    parsed = parse_recon_combined(payload)
    rows = [
        {
            "settlement": r.settlement_id,
            "item": r.item_id,
            "kind": r.kind.value,
            "amount": format_rupees(r.amount_paise),
            "type": r.type_raw,
        }
        for r in parsed
    ]
    result = {"ok": True, "n": len(rows), "rows": rows, "written": False, "cleared": 0}
    return match_recon_to_ledger(result, ledger_ids)


def extension_dir() -> Path:
    repo = Path(__file__).resolve().parents[3]
    located = repo.joinpath("extension")
    if located.is_dir():
        return located
    cwd = Path("extension")
    if cwd.is_dir():
        return cwd
    raise FileNotFoundError("extension/")


def pack_extension_zip() -> bytes:
    """Zip the unpacked folder. Chrome still needs the unzipped directory."""
    root = extension_dir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name == ".DS_Store":
                continue
            arc = Path("residual-zero-extension").joinpath(path.relative_to(root))
            archive.write(path, arc.as_posix())
    return buf.getvalue()


def mount_ext(app: FastAPI) -> None:
    from residual_zero.console.app import (
        _credit_lookup,
        _db,
        _enrich,
        _honesty_now,
        _load_audits,
        _overlay,
        _profile,
        _render,
        _split,
    )

    def _cleared_count(conn) -> int:
        if conn is None:
            return 0
        row = conn.execute(
            "SELECT COUNT(*) FROM reconciliation WHERE disposition = 'CLEARED'"
        ).fetchone()
        return int(row[0]) if row else 0

    def _rows() -> list[dict[str, str]]:
        conn = _db()
        payload: list[dict[str, str]] = []
        if conn is not None:
            try:
                raw = list(
                    conn.execute(
                        "SELECT bank_credit_id, exception_class FROM exception ORDER BY bank_credit_id"
                    )
                )
                audits = _load_audits(conn)
            finally:
                conn.close()
            for cid, cls in raw:
                row = _enrich(cid, cls, audits.get(cid))
                payload.append(
                    {
                        "id": row["id"],
                        "cls": row["cls"],
                        "amount": row["amount"],
                        "account": row["account"],
                        "date": row["value_date"],
                        "uniqueness": row["uniqueness"],
                        "gate": row["gate"],
                        "utr": row.get("utr") or "",
                        "narration": row.get("narration") or "",
                        "href": "/credit/" + row["id"],
                    }
                )
            return payload
        lookup = _credit_lookup()
        for cid, credit in lookup.items():
            payload.append(
                {
                    "id": cid,
                    "cls": "",
                    "amount": format_rupees(credit.amount_paise),
                    "account": credit.account_id,
                    "date": credit.value_date.isoformat(),
                    "uniqueness": "",
                    "gate": "REFUSED",
                    "utr": credit.utr or "",
                    "narration": credit.narration_raw,
                    "href": "/credit/" + cid,
                }
            )
        return payload

    @app.get("/api/desk")
    def api_desk():
        overlay = _overlay()
        split = _split()
        n_posted = len(split[1]) if split is not None else 0
        n_gate = overlay.n_ok if overlay is not None else 0
        n_journal = overlay.n_journalable if overlay is not None else 0
        n_mismatch = overlay.n_mismatch if overlay is not None else 0
        conn = _db()
        n_cleared = 0
        try:
            n_cleared = _cleared_count(conn)
        finally:
            if conn is not None:
                conn.close()
        n_human = n_posted - n_gate if n_posted >= n_gate else 0
        return JSONResponse(
            {
                "ok": True,
                "cleared": n_cleared,
                "gate_a": n_gate,
                "journalable": n_journal,
                "mismatch": n_mismatch,
                "human": n_human,
                "posted": n_posted,
                "demo_credit": DEMO_CREDIT,
                "honesty": _honesty_now(n_human),
                "writes_cleared": False,
            }
        )

    @app.get("/api/credit/{credit_id}")
    def api_credit(credit_id: str):
        overlay = _overlay()
        lookup = _credit_lookup()
        credit = lookup.get(credit_id)
        gate = overlay.by_id.get(credit_id) if overlay is not None else None
        row = None
        exc = None
        conn = _db()
        if conn is not None:
            try:
                audits = _load_audits(conn)
                exc = conn.execute(
                    "SELECT exception_class FROM exception WHERE bank_credit_id = ?",
                    (credit_id,),
                ).fetchone()
                row = _enrich(credit_id, exc[0] if exc else "", audits.get(credit_id))
            finally:
                conn.close()
        found = credit is not None or gate is not None or exc is not None
        journalable = overlay is not None and credit_id in overlay.journalable
        posted_mismatch = bool(gate is not None and gate.ok and not journalable)
        return JSONResponse(
            {
                "ok": found,
                "id": credit_id,
                "amount": row["amount"] if row else (format_rupees(credit.amount_paise) if credit else ""),
                "account": row["account"] if row else (credit.account_id if credit else ""),
                "date": row["value_date"] if row else (credit.value_date.isoformat() if credit else ""),
                "uniqueness": row["uniqueness"] if row else "",
                "gate": row["gate"] if row else "REFUSED",
                "cls": row["cls"] if row else "",
                "gate_a_ok": bool(gate is not None and gate.ok),
                "residual_paise": gate.residual_paise if gate is not None else None,
                "journalable": journalable,
                "posted_mismatch": posted_mismatch,
                "href": "/credit/" + credit_id,
                "writes_cleared": False,
            }
        )

    @app.get("/api/lookup")
    def api_lookup(q: str = ""):
        needle = (q or "").strip().casefold()
        hits = _rows()
        if needle:
            ranked: list[dict[str, str]] = []
            rest: list[dict[str, str]] = []
            for row in hits:
                blob = " ".join(
                    (
                        row["id"],
                        row["account"],
                        row["cls"],
                        row["gate"],
                        row.get("utr") or "",
                        row.get("narration") or "",
                    )
                ).casefold()
                if row["id"].casefold() == needle or row["id"].casefold().startswith(needle):
                    ranked.append(row)
                elif needle in blob:
                    rest.append(row)
            hits = ranked + rest
        return JSONResponse({"ok": True, "n": len(hits), "rows": hits[:40]})

    def _ask(request: Request, question: str, credit_id: str) -> dict:
        """Run the controller and record the investigation. The answer is unchanged by both.

        The recording is deliberately after the fact and cannot alter the payload: an AI
        surface over financial data has to be reconstructable, and that is all this adds.
        """
        import time

        from residual_zero.console.security import principal_of
        from residual_zero.qa.controller import answer as controller_answer
        from residual_zero.qa.investigation_log import record

        started = time.monotonic_ns()
        result = controller_answer(question, credit_id)
        principal = principal_of(request)
        record(
            result,
            question=question,
            credit_id=credit_id,
            user_id=principal.user_id if principal is not None else "",
            duration_ms=(time.monotonic_ns() - started) // 1_000_000,
        )
        return result

    @app.get("/api/ask")
    def api_ask(request: Request, q: str = "", question: str = "", credit_id: str = ""):
        return JSONResponse(_ask(request, question or q, credit_id))

    @app.post("/api/ask")
    async def api_ask_post(request: Request):
        try:
            payload = json.loads((await request.body()).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("body must be a JSON object")
            return JSONResponse(
                _ask(
                    request,
                    str(payload.get("question") or payload.get("q") or ""),
                    str(payload.get("credit_id") or ""),
                )
            )
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return JSONResponse({"ok": False, "error": str(exc), "writes_cleared": False}, status_code=400)

    @app.get("/api/finance/evidence")
    def api_finance_evidence(credit_id: str = "", transaction_id: str = ""):
        from residual_zero.qa.finance_tools import get_transaction_evidence

        return JSONResponse(get_transaction_evidence(credit_id or transaction_id))

    @app.get("/api/finance/proof")
    def api_finance_proof(credit_id: str = "", transaction_id: str = ""):
        from residual_zero.console.proof_explorer import proof_explorer

        return JSONResponse(proof_explorer(credit_id or transaction_id))

    @app.post("/api/finance/tool")
    async def api_finance_tool(request: Request):
        from residual_zero.qa.finance_tools import call_finance_tool

        try:
            payload = json.loads((await request.body()).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("body must be a JSON object")
            return JSONResponse(
                call_finance_tool(
                    str(payload.get("name") or payload.get("tool") or ""),
                    payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
                )
            )
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return JSONResponse({"ok": False, "error": str(exc), "writes_cleared": False}, status_code=400)

    @app.get("/api/whatif")
    def api_whatif(credit_id: str = DEMO_CREDIT, reserve_bps: int = -1):
        """Read-only JSON mirror of the /whatif page.

        Calls the same authoritative `controller.whatif.recompute` the HTML route calls.
        Parameter substitution over an already-known declared member set only — it never
        invents a member set and never writes. The extension needs JSON because the HTML
        route returns a rendered page.
        """
        from residual_zero.config import load_fees, load_tax_rates
        from residual_zero.controller.whatif import recompute

        profile = _profile()
        used = profile.reserve_bps if reserve_bps < 0 else int(reserve_bps)
        split = _split()
        note = (
            "Parameter substitution on a known member set. Not a rail counterfactual. "
            "Overlay does not write CLEARED."
        )
        if split is None:
            return JSONResponse(
                {"ok": False, "error": "split_unavailable", "note": note, "writes_cleared": False}
            )
        _items, _credits, by_credit, ledger, credits_by_id = split
        credit = credits_by_id.get(credit_id)
        if credit is None:
            return JSONResponse(
                {"ok": False, "error": "unknown_credit", "credit_id": credit_id,
                 "note": note, "writes_cleared": False}
            )
        declared = by_credit.get(credit_id, ())
        if not declared:
            return JSONResponse(
                {"ok": False, "error": "no_declared_member_set", "credit_id": credit_id,
                 "note": "What-if does not invent a member set.", "writes_cleared": False}
            )
        member_ids = tuple(r.item_id for r in declared if r.item_id in ledger)
        rates, fees = load_tax_rates(), load_fees()
        base = recompute(credit, member_ids, ledger, rates, fees, profile.reserve_bps)
        alt = recompute(credit, member_ids, ledger, rates, fees, used)
        return JSONResponse({
            "ok": True,
            "credit_id": credit_id,
            "members": len(member_ids),
            "presets": [0, 300, 500, 700],
            "baseline": {
                "ok": base.ok, "bps": profile.reserve_bps,
                "residual": format_rupees(base.residual_paise),
                "residual_paise": base.residual_paise, "deltas": len(base.line_deltas),
            },
            "scenario": {
                "ok": alt.ok, "bps": used,
                "residual": format_rupees(alt.residual_paise),
                "residual_paise": alt.residual_paise, "deltas": len(alt.line_deltas),
                "same": base.residual_paise == alt.residual_paise and base.ok == alt.ok,
            },
            "note": note,
            "writes_cleared": False,
        })

    @app.get("/api/journal")
    def api_journal():
        """Read-only JSON mirror of the /journal page totals.

        Same authoritative `journal` helpers the HTML route uses. Debits and credits are
        integer paise from the engine; the extension only renders them.
        """
        from residual_zero.journal import build_journal, control_residual, load_chart, trial_balance

        split = _split()
        if split is None:
            return JSONResponse(
                {"ok": False, "error": "ledger_unavailable", "writes_cleared": False}
            )
        # Opened after the early exit, so the "no ledger" answer cannot leak a connection.
        conn = _db()
        if conn is None:
            return JSONResponse(
                {"ok": False, "error": "ledger_unavailable", "writes_cleared": False}
            )
        overlay = _overlay()
        try:
            _items, credits, _by_credit, ledger, _by_id = split
            # Same member source the /journal page uses: the ops overlay when it has
            # journalable sets, otherwise the cleared decompositions in the ledger.
            if overlay is not None and overlay.journalable:
                members = overlay.journalable
            else:
                members = _cleared_members(conn)
            lines = build_journal(credits, ledger, members, chart := load_chart())
            debits, credits_total = trial_balance(lines)
            residual = control_residual(lines, credits, chart.bank_control.code)
        except ValueError as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc), "writes_cleared": False}
            )
        finally:
            conn.close()
        return JSONResponse({
            "ok": True,
            "n_lines": len(lines),
            "debits_paise": debits,
            "credits_paise": credits_total,
            "debits": format_rupees(debits),
            "credits": format_rupees(credits_total),
            "balanced": debits == credits_total,
            "control_residual_paise": residual,
            "control_residual": format_rupees(residual),
            "csv_href": "/journal.csv",
            "note": "Debits equal credits at paise. Uncleared credits post to suspense 2300.",
            "writes_cleared": False,
        })

    def _ledger_ids() -> set[str]:
        split = _split()
        if split is None:
            return set()
        return set(split[3].keys())

    @app.post("/api/recon")
    async def api_recon(request: Request):
        try:
            payload = json.loads((await request.body()).decode("utf-8"))
            return JSONResponse(preview_recon(payload, _ledger_ids()))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc), "written": False, "n": 0, "rows": []},
                status_code=400,
            )

    @app.get("/api/mcp/tools")
    def api_mcp_tools():
        enabled, _key_id, _secret = load_adapter_flags()
        return JSONResponse(
            {
                "ok": True,
                "enabled": enabled,
                "source": "live" if enabled else "fixture",
                "allowed": sorted(ALLOWED_TOOLS | DESK_TOOLS),
                "refused": sorted(REFUSED_TOOLS),
                "stdio": "python -m residual_zero.mcp",
                "tools": list_tools(),
                "written": False,
            }
        )

    @app.post("/api/mcp/tool")
    async def api_mcp_tool(request: Request):
        try:
            payload = json.loads((await request.body()).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("body must be a JSON object")
            result = call_tool(
                str(payload.get("tool") or ""),
                payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
                ids=_ledger_ids(),
            )
            return JSONResponse(result)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc), "written": False, "n": 0, "rows": [], "settlements": []},
                status_code=400,
            )

    @app.get("/mcp")
    def mcp_discover():
        enabled, _key_id, _secret = load_adapter_flags()
        return JSONResponse(
            {
                "ok": True,
                "protocol": "mcp",
                "stdio": "python -m residual_zero.mcp",
                "source": "live" if enabled else "fixture",
                "tools": list_tools(),
                "refused": sorted(REFUSED_TOOLS),
                "written": False,
            }
        )

    @app.post("/mcp")
    async def mcp_rpc(request: Request):
        try:
            payload = json.loads((await request.body()).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("body must be a JSON object")
            reply = handle_rpc(payload)
            if reply is None:
                return JSONResponse({"ok": True})
            return JSONResponse(reply)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}},
                status_code=400,
            )

    @app.get("/extension")
    def extension_page():
        return _render("extension.html", active="extension")

    @app.get("/extension.zip")
    def extension_zip():
        data = pack_extension_zip()
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="residual-zero-extension.zip"',
            },
        )
