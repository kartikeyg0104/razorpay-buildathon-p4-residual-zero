"""Phase 2–4 controller surfaces on the ops console. Read-only except inherited resolve."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from residual_zero.audit import verify_chain
from residual_zero.bitemporal import as_of_view, load_payloads, replay_prefix, views_equal
from residual_zero.books import check_books, check_books_from_cleared, format_identity
from residual_zero.challenge import inspect_challenge
from residual_zero.cluster import compression_ratio
from residual_zero.config import load_fees, load_tax_rates
from residual_zero.console.close_ops import build_close_pack, pack_as_json
from residual_zero.console.ops import fixture_rival_sets
from residual_zero.console.ops_pack import (
    amount_twin_rows,
    batch_certificate,
    cash_bridge,
    close_bundle_zip,
    close_markdown,
    duplicate_utr_rows,
    exceptions_csv,
    exposure_queue,
    four_way_gaps,
    prometheus_text,
    standup_markdown,
    tax_radar,
)
from residual_zero.controller.disputes import track as track_disputes
from residual_zero.controller.leakage import sweep as sweep_leakage
from residual_zero.controller.reserve import subledger as reserve_subledger
from residual_zero.controller.whatif import recompute
from residual_zero.ingest.mcp_settlements import match_recon_to_ledger
from residual_zero.ingest.razorpay import parse_recon_combined
from residual_zero.journal import build_journal, control_residual, load_chart, render_csv, render_tally_xml, trial_balance
from residual_zero.money import format_rupees
from residual_zero.qa.controller import answer as controller_answer
from residual_zero.rates import regress, triples_from_members
from residual_zero.runtime.degrade import Rung, policy_for
from residual_zero.solver.alt_diff import render_diff


def _md_data_rows(path: Path, header: str) -> list[list[str]]:
    if not path.is_file():
        return []
    rows: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            continue
        if set(cells[0]) <= set("-:"):
            continue
        if cells[0] == header:
            continue
        rows.append(cells)
    return rows


def _arm_cell(rows: list[list[str]], arm: str, index: int) -> str:
    """One cell of one arm row from a committed headline table, or "—".

    Same discipline as :mod:`residual_zero.console.facts`: a missing or unparseable card
    renders an em dash rather than a literal, so the console can never show an
    official-looking number that no run produced.
    """
    for row in rows:
        if row and row[0].casefold() == arm and len(row) > index:
            return row[index]
    return "—"


def mount(app: FastAPI) -> None:
    from residual_zero.console.app import _db, _overlay, _profile, _render, _split

    def _format_reports(reports) -> list[dict[str, object]]:
        out = []
        for report in reports:
            out.append(
                {
                    "account": report.account_id,
                    "period": f"{report.period_start.isoformat()} → {report.period_end.isoformat()}",
                    "holds": report.identity_holds,
                    "credits": format_rupees(report.credits_paise),
                    "cleared": format_rupees(report.cleared_members_paise),
                    "unreconciled": format_rupees(report.unreconciled_credits_paise),
                    "n_credits": report.n_credits,
                    "n_cleared": report.n_cleared,
                    "double": len(report.double_claimed_item_ids),
                    "line": format_identity(report),
                }
            )
        return out

    def _cleared_members(conn) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        if conn is None:
            return {}
        rows = conn.execute(
            "SELECT r.bank_credit_id, m.item_id "
            "FROM reconciliation r "
            "JOIN decomposition_member m ON m.bank_credit_id = r.bank_credit_id "
            "WHERE r.disposition = 'CLEARED' "
            "ORDER BY r.bank_credit_id, m.item_id"
        )
        for cid, item_id in rows:
            grouped.setdefault(str(cid), []).append(str(item_id))
        return {cid: tuple(ids) for cid, ids in grouped.items()}

    def _as_of_day() -> date:
        split = _split()
        if split is None:
            return date(2025, 3, 5)
        credits = split[1]
        return max(c.value_date for c in credits)

    def _credit_token(question: str, credit_id: str) -> str:
        if credit_id.startswith("crd_"):
            return credit_id
        for token in question.split():
            cleaned = token.strip(".,:;?!")
            if cleaned.startswith("crd_"):
                return cleaned
        return credit_id

    @app.get("/ask", response_class=HTMLResponse)
    def ask(question: str = "", credit_id: str = ""):
        from residual_zero.qa.train import trained

        cid = _credit_token(question, credit_id)
        model = trained()
        intent_name = ""
        answer = ""
        citations: tuple[str, ...] = ()
        fit_score = 0
        n_docs = model.n_docs
        n_labels = model.n_labels
        n_train = model.n_train
        n_credits = model.n_credits
        holdout = f"{model.n_holdout_ok}/{model.n_holdout}"
        doc_title = ""
        source = ""
        provider_on = False
        provider_used = False
        provider_model_id = ""
        provider = "fitted"
        provider_error = ""
        mode = "idle"
        decision = ""
        recommended = ""
        evidence_refs: list = []
        checks: list = []
        tools_called: list = []
        investigation_steps: list = []
        llm_used = False
        if question.strip():
            got = controller_answer(question, cid)
            intent_name = str(got.get("intent") or "")
            answer = str(got.get("answer") or "")
            citations = tuple(got.get("citations") or ())
            fit_score = int(got.get("fit_score") or 0)
            n_docs = int(got.get("n_docs") or n_docs)
            n_labels = int(got.get("n_labels") or n_labels)
            n_train = int(got.get("n_train") or n_train)
            n_credits = int(got.get("n_credits") or n_credits)
            holdout = str(got.get("holdout") or holdout)
            doc_title = str(got.get("doc_title") or "")
            source = str(got.get("source") or "")
            provider_on = bool(got.get("provider_live"))
            provider_used = bool(got.get("provider_used"))
            provider_model_id = str(got.get("provider_model") or "")
            provider = str(got.get("provider") or "fitted")
            provider_error = str(got.get("provider_error") or "")
            mode = str(got.get("mode") or "fitted")
            decision = str(got.get("decision") or "")
            recommended = str(got.get("recommended_action") or "")
            evidence_refs = list(got.get("evidence_refs") or [])
            checks = list(got.get("checks") or [])
            tools_called = list(got.get("tools_called") or [])
            investigation_steps = list(got.get("investigation_steps") or [])
            llm_used = bool(got.get("llm_used") or got.get("provider_used"))
        else:
            from residual_zero.semantic.provider import provider_model, live_enabled

            provider_on = live_enabled()
            provider_model_id = provider_model() if provider_on else ""
            mode = "idle"
            decision = ""
            recommended = ""
            evidence_refs = []
            checks = []
            tools_called = []
            llm_used = False
        from residual_zero.qa.evidence_ops import copilot_prompts

        copilot_chips = copilot_prompts()
        from residual_zero.semantic.provider import desk_ai_status

        ai_status = desk_ai_status()
        return _render(
            "ask.html",
            active="ask",
            question=question,
            credit_id=cid,
            intent=intent_name,
            answer=answer,
            citations=citations,
            fit_score=fit_score,
            n_docs=n_docs,
            n_labels=n_labels,
            n_train=n_train,
            n_credits=n_credits,
            holdout=holdout,
            doc_title=doc_title,
            source=source,
            provider_on=provider_on,
            provider_used=provider_used,
            provider_model=provider_model_id,
            provider=provider,
            provider_error=provider_error,
            mode=mode,
            decision=decision,
            recommended=recommended,
            evidence_refs=evidence_refs,
            checks=checks,
            tools_called=tools_called,
            investigation_steps=investigation_steps,
            copilot=copilot_chips,
            llm_used=llm_used,
            provider_status=ai_status,
        )

    @app.get("/books", response_class=HTMLResponse)
    def books():
        split = _split()
        reports = []
        ops_reports = []
        identities = []
        ops_hold = False
        n_gate_a = 0
        conn = _db()
        if conn is not None and split is not None:
            try:
                _items, credits, _by, ledger, _ids = split
                search = check_books(conn, credits, ledger)
                reports = _format_reports(search)
                identities = [r.identity_holds for r in search]
                overlay = _overlay()
                if overlay is not None:
                    n_gate_a = overlay.n_ok
                    ops = check_books_from_cleared(credits, ledger, overlay.journalable)
                    ops_reports = _format_reports(ops)
                    ops_hold = bool(ops) and all(r.identity_holds for r in ops)
            finally:
                conn.close()
        return _render(
            "books.html",
            active="books",
            reports=reports,
            ops_reports=ops_reports,
            all_hold=bool(identities) and all(identities),
            ops_hold=ops_hold,
            n_gate_a=n_gate_a,
        )

    @app.get("/journal", response_class=HTMLResponse)
    def journal(gate: str = "ops"):
        split = _split()
        lines_out = []
        debit = credit = residual = 0
        n = 0
        used_ops = False
        n_ops = 0
        n_gate_a = 0
        n_mismatch = 0
        journal_error = ""
        conn = _db()
        if split is not None:
            try:
                _items, credits, _by, ledger, _ids = split
                overlay = _overlay()
                n_ops = overlay.n_journalable if overlay is not None else 0
                n_gate_a = overlay.n_ok if overlay is not None else 0
                n_mismatch = overlay.n_mismatch if overlay is not None else 0
                if gate == "ops" and overlay is not None and overlay.journalable:
                    cleared = overlay.journalable
                    used_ops = True
                else:
                    cleared = _cleared_members(conn)
                chart = load_chart()
                try:
                    built = build_journal(credits, ledger, cleared, chart)
                except ValueError as exc:
                    journal_error = str(exc)
                    cleared = _cleared_members(conn)
                    used_ops = False
                    built = build_journal(credits, ledger, cleared, chart)
                debit, credit = trial_balance(built)
                residual = control_residual(built, credits, chart.bank_control.code)
                n = len(built)
                for line in built[:80]:
                    lines_out.append(
                        {
                            "date": line.date.isoformat(),
                            "code": line.account_code,
                            "name": line.account_name,
                            "debit": format_rupees(line.debit_paise) if line.debit_paise else "",
                            "credit": format_rupees(line.credit_paise) if line.credit_paise else "",
                            "narration": line.narration,
                            "ref": line.reference,
                        }
                    )
            finally:
                if conn is not None:
                    conn.close()
        return _render(
            "journal.html",
            active="journal",
            n=n,
            debit=format_rupees(debit),
            credit=format_rupees(credit),
            residual=format_rupees(residual),
            balanced=debit == credit,
            control_ok=residual == 0,
            lines=lines_out,
            used_ops=used_ops,
            n_ops=n_ops,
            n_gate_a=n_gate_a,
            n_mismatch=n_mismatch,
            journal_error=journal_error,
        )

    @app.get("/journal.csv")
    def journal_csv():
        split = _split()
        if split is None:
            return PlainTextResponse("no split\n", status_code=404)
        # The connection is opened AFTER the early exit. It used to be opened before, so an
        # organisation with no ledger leaked one connection per request on the 404 path —
        # harmless against a SQLite file, and a pool exhaustion against PostgreSQL.
        conn = _db()
        try:
            _items, credits, _by, ledger, _ids = split
            overlay = _overlay()
            if overlay is not None and overlay.journalable:
                cleared = overlay.journalable
            else:
                cleared = _cleared_members(conn)
            built = build_journal(credits, ledger, cleared, load_chart())
            return PlainTextResponse(render_csv(built), media_type="text/csv")
        finally:
            if conn is not None:
                conn.close()

    @app.get("/journal.tally")
    def journal_tally():
        split = _split()
        if split is None:
            return PlainTextResponse("no split\n", status_code=404)
        # The connection is opened AFTER the early exit. It used to be opened before, so an
        # organisation with no ledger leaked one connection per request on the 404 path —
        # harmless against a SQLite file, and a pool exhaustion against PostgreSQL.
        conn = _db()
        try:
            _items, credits, _by, ledger, _ids = split
            overlay = _overlay()
            if overlay is not None and overlay.journalable:
                cleared = overlay.journalable
            else:
                cleared = _cleared_members(conn)
            built = build_journal(credits, ledger, cleared, load_chart())
            return Response(content=render_tally_xml(built), media_type="application/xml")
        finally:
            if conn is not None:
                conn.close()

    def _assemble_close():
        split = _split()
        overlay = _overlay()
        conn = _db()
        if split is None:
            if conn is not None:
                conn.close()
            return build_close_pack((), {}, {}, overlay)
        _items, credits, by_credit, ledger, _ids = split
        books_hold = False
        journal_balanced = False
        control_ok = False
        chain_ok = False
        n_auto = 0
        audits: dict[str, dict] = {}
        try:
            if overlay is not None and overlay.journalable:
                reports = check_books_from_cleared(credits, ledger, overlay.journalable)
                books_hold = bool(reports) and all(r.identity_holds for r in reports)
                try:
                    built = build_journal(credits, ledger, overlay.journalable, load_chart())
                except ValueError:
                    built = ()
                if built:
                    debit, credit_sum = trial_balance(built)
                    journal_balanced = debit == credit_sum
                    control_ok = control_residual(built, credits, load_chart().bank_control.code) == 0
            if conn is not None:
                chain_ok, _broken, _head = verify_chain(conn)
                from residual_zero.console.app import _load_audits

                audits = _load_audits(conn)
                n_auto = sum(1 for row in audits.values() if row.get("disposition") == "CLEARED")
            return build_close_pack(
                credits,
                ledger,
                by_credit,
                overlay,
                audits,
                books_hold=books_hold,
                journal_balanced=journal_balanced,
                control_ok=control_ok,
                chain_ok=chain_ok,
                n_auto_cleared=n_auto,
            )
        finally:
            if conn is not None:
                conn.close()

    def _ops_surfaces(pack):
        if pack.writes_cleared:
            raise RuntimeError("close pack cannot write CLEARED")
        split = _split()
        overlay = _overlay()
        rates, fees = load_tax_rates(), load_fees()
        credits = split[1] if split is not None else ()
        ledger = split[3] if split is not None else {}
        n_credits = len(credits)
        bridge = cash_bridge(credits, ledger, overlay)
        radar = tax_radar(ledger, rates, fees)
        conn = _db()
        audit_head = ""
        chain_ok = False
        n_unique = 0
        n_ambiguous = 0
        n_none = 0
        n_auto = 0
        try:
            if conn is not None:
                chain_ok, _broken, audit_head = verify_chain(conn)
                from residual_zero.console.app import _load_audits

                audits = _load_audits(conn)
                n_unique = sum(1 for row in audits.values() if row.get("uniqueness") == "UNIQUE")
                n_ambiguous = sum(1 for row in audits.values() if row.get("uniqueness") == "AMBIGUOUS")
                n_none = sum(1 for row in audits.values() if row.get("uniqueness") == "NONE_FOUND")
                n_auto = sum(1 for row in audits.values() if row.get("disposition") == "CLEARED")
        finally:
            if conn is not None:
                conn.close()
        cert = batch_certificate(
            audit_head=audit_head or "",
            n_credits=n_credits,
            n_gate_a=overlay.n_ok if overlay is not None else 0,
            n_journalable=overlay.n_journalable if overlay is not None else 0,
            n_unique=n_unique,
            n_ambiguous=n_ambiguous,
            n_none_found=n_none,
            n_auto_cleared=n_auto,
            chain_ok=chain_ok,
        )
        return bridge, radar, cert

    def _level3(pack):
        from residual_zero.console.close_ops import corpus_as_of

        split = _split()
        overlay = _overlay()
        if split is None:
            credits, by_credit, ledger = (), {}, {}
        else:
            _items, credits, by_credit, ledger, _ids = split
        as_of = corpus_as_of(credits)
        return {
            "exposure": exposure_queue(credits, overlay, as_of),
            "dupes": duplicate_utr_rows(credits),
            "twins": amount_twin_rows(credits),
            "gaps": four_way_gaps(credits, by_credit, ledger, overlay),
        }

    def _queue_rows():
        from residual_zero.console.app import _db as db_now, _enrich, _load_audits

        conn = db_now()
        raw = []
        audits: dict = {}
        try:
            if conn is not None:
                raw = list(
                    conn.execute(
                        "SELECT bank_credit_id, exception_class FROM exception ORDER BY bank_credit_id"
                    )
                )
                audits = _load_audits(conn)
        finally:
            if conn is not None:
                conn.close()
        return [_enrich(cid, cls, audits.get(cid)) for cid, cls in raw]

    def _run_recorded() -> bool:
        """Whether this organisation has a recorded search/audit run of its own.

        The certificate's counts come from that run. Without one they are all zero and
        ``chain_ok`` is False, which the page rendered as "broken" — an alarm about
        evidence that does not exist. The certificate object is left exactly as it is;
        only what the page *says* about an absent run changes.
        """
        from residual_zero.console.app import _db
        from residual_zero.storage.errors import QUERY_ERRORS, rollback_quietly

        conn = _db()
        if conn is None:
            return False
        try:
            return conn.execute("SELECT 1 FROM audit_entry LIMIT 1").fetchone() is not None
        except QUERY_ERRORS:
            rollback_quietly(conn)
            return False
        finally:
            conn.close()

    @app.get("/close", response_class=HTMLResponse)
    def close_desk():
        pack = _assemble_close()
        bridge, radar, cert = _ops_surfaces(pack)
        extra = _level3(pack)
        return _render(
            "close.html",
            active="close",
            pack=pack,
            sla=pack.sla,
            autonomy=pack.autonomy,
            checklist=pack.checklist,
            bank_uncovered=pack.bank_uncovered,
            ledger_orphans=pack.ledger_orphans,
            tax_mismatch=pack.tax_mismatch,
            bridge=bridge,
            radar=radar,
            cert=cert,
            run_recorded=_run_recorded(),
            exposure=extra["exposure"],
            dupes=extra["dupes"],
            twins=extra["twins"],
            gaps=extra["gaps"],
            standup=standup_markdown(
                pack, bridge, radar, cert, extra["exposure"], extra["dupes"], extra["gaps"]
            ),
        )

    @app.get("/api/close")
    def api_close():
        pack = _assemble_close()
        _bridge, _radar, cert = _ops_surfaces(pack)
        payload = pack_as_json(pack)
        payload["certificate_sha256"] = cert["sha256"]
        payload["plugged"] = False
        return JSONResponse(payload)

    @app.get("/close.md")
    def close_markdown_route():
        pack = _assemble_close()
        bridge, radar, cert = _ops_surfaces(pack)
        return PlainTextResponse(close_markdown(pack, bridge, radar, cert), media_type="text/markdown")

    @app.get("/certificate")
    def certificate():
        pack = _assemble_close()
        _bridge, _radar, cert = _ops_surfaces(pack)
        return JSONResponse(cert)

    @app.get("/metrics")
    def metrics():
        pack = _assemble_close()
        overlay = _overlay()
        split = _split()
        n_credits = len(split[1]) if split is not None else 0
        n_gate = overlay.n_ok if overlay is not None else 0
        _bridge, _radar, cert = _ops_surfaces(pack)
        return PlainTextResponse(
            prometheus_text(
                n_credits=n_credits,
                n_gate_a=n_gate,
                n_human=pack.n_human,
                n_auto_cleared=int(cert.get("n_auto_cleared") or 0),
            ),
            media_type="text/plain; version=0.0.4",
        )

    @app.get("/exceptions.csv")
    def exceptions_csv_route():
        return Response(
            content=exceptions_csv(_queue_rows()),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="exceptions.csv"'},
        )

    @app.get("/health")
    def _recorded_run() -> dict | None:
        """The organisation's latest COMPLETED run, or None.

        Read-only, and it never invents a run: an organisation that has not reconciled has
        no row here and the desk keeps saying so.
        """
        from residual_zero.audit import latest_completed_run
        from residual_zero.console.app import _db
        from residual_zero.storage.errors import QUERY_ERRORS, rollback_quietly

        conn = _db()
        if conn is None:
            return None
        try:
            return latest_completed_run(conn)
        except QUERY_ERRORS:
            rollback_quietly(conn)
            return None
        finally:
            conn.close()

    @app.get("/api/run")
    def api_run():
        """The recorded deterministic run, straight from the database.

        Exists so persistence is checkable from outside the process: if this returns a
        run after a restart, the run is in the database and not in somebody's memory.
        """
        run = _recorded_run()
        return JSONResponse(
            {
                "ok": True,
                "recorded": run is not None,
                # Coverage, promoted out of the run body so a reader cannot miss it.
                "complete": bool(run and run.get("complete")),
                "n_credits": (run or {}).get("n_credits", 0),
                "n_persisted": (run or {}).get("n_persisted", 0),
                "run": run,
                "writes_cleared": False,
                "note": (
                    "n_persisted is coverage: distinct credits carrying a persisted "
                    "result, counted from the rows. n_computed is what this invocation "
                    "computed and is smaller whenever idempotency skipped work already "
                    "done. A run records that the deterministic engine executed; it is "
                    "not a clearance and it does not authorise one."
                ),
            }
        )

    @app.get("/api/health")
    def health():
        from residual_zero.semantic.provider import desk_ai_status, provider_model, live_enabled

        pack = _assemble_close()
        overlay = _overlay()
        split = _split()
        n_credits = len(split[1]) if split is not None else 0
        ai = desk_ai_status()
        run = _recorded_run()
        return JSONResponse(
            {
                "ok": True,
                "product": "Residual Zero",
                "writes_cleared": False,
                "auto_clear": 0,
                "n_credits": n_credits,
                "n_gate_a": overlay.n_ok if overlay is not None else 0,
                "n_journalable": overlay.n_journalable if overlay is not None else 0,
                "n_human": pack.n_human,
                "run_recorded": run is not None,
                "run_id": (run or {}).get("run_id", ""),
                "run_status": (run or {}).get("status", ""),
                "run_complete": bool(run and run.get("complete")),
                "run_n_credits": (run or {}).get("n_credits", 0),
                "run_n_persisted": (run or {}).get("n_persisted", 0),
                "run_n_computed": (run or {}).get("n_computed", 0),
                "run_n_reused": (run or {}).get("n_reused", 0),
                "chain": any(item["name"] == "audit chain intact" and item["ok"] for item in pack.checklist),
                # NVIDIA NIM is the only backend. Each fact appears exactly once: this
                # literal used to repeat `provider_model`, `LIVE_PROVIDER`,
                # `provider_key_present` and `provider_error`, so the earlier spelling of
                # each was dead code that read as a deliberate second field.
                "provider": ai["provider"],
                "provider_endpoint": ai["endpoint"],
                "provider_model": provider_model() if live_enabled() else "",
                "provider_key_present": ai["key_present"],
                "provider_error": ai["error"],
                "provider_live": live_enabled(),
                "LIVE_PROVIDER": ai["LIVE_PROVIDER"],
                "LIVE_LLM_TOOL_LOOP": ai["LIVE_LLM_TOOL_LOOP"],
                "DETERMINISTIC_CONTROLLER": ai["DETERMINISTIC_CONTROLLER"],
                "note": ai["note"],
            }
        )

    @app.get("/api/ops")
    def api_ops():
        pack = _assemble_close()
        bridge, radar, cert = _ops_surfaces(pack)
        extra = _level3(pack)
        return JSONResponse(
            {
                "ok": True,
                "writes_cleared": False,
                "plugged": False,
                "as_of": pack.as_of,
                "bridge": bridge,
                "radar": radar,
                "certificate": cert,
                "n_bank_uncovered": pack.n_bank_uncovered,
                "n_ledger_orphans": pack.n_ledger_orphans,
                "n_tax_mismatch": pack.n_tax_mismatch,
                "n_human": pack.n_human,
                "exposure": extra["exposure"],
                "duplicate_utr": extra["dupes"],
                "amount_twins": extra["twins"],
                "four_way_gaps": extra["gaps"],
            }
        )

    @app.get("/standup.md")
    def standup_md():
        pack = _assemble_close()
        bridge, radar, cert = _ops_surfaces(pack)
        extra = _level3(pack)
        return PlainTextResponse(
            standup_markdown(pack, bridge, radar, cert, extra["exposure"], extra["dupes"], extra["gaps"]),
            media_type="text/markdown",
        )

    @app.get("/close.zip")
    def close_zip():
        pack = _assemble_close()
        bridge, radar, cert = _ops_surfaces(pack)
        extra = _level3(pack)
        data = close_bundle_zip(
            close_md=close_markdown(pack, bridge, radar, cert),
            standup_md=standup_markdown(
                pack, bridge, radar, cert, extra["exposure"], extra["dupes"], extra["gaps"]
            ),
            cert=cert,
            exceptions_csv_text=exceptions_csv(_queue_rows()),
        )
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="residual-zero-close.zip"'},
        )

    @app.get("/clusters", response_class=HTMLResponse)
    def clusters():
        path = Path("artifacts").joinpath("dev", "clusters.json")
        rows = []
        n_exc = n_clu = 0
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            for cluster in payload:
                ids = list(cluster.get("ids") or [])
                n_clu += 1
                n_exc += int(cluster.get("size") or len(ids))
                rows.append(
                    {
                        "signature": cluster.get("signature") or "",
                        "size": cluster.get("size") or len(ids),
                        "ids": ids[:8],
                        "more": max(0, len(ids) - 8),
                    }
                )
        pair = compression_ratio(n_exc, n_clu)
        return _render(
            "clusters.html",
            active="clusters",
            rows=rows,
            n_exc=pair[0],
            n_clu=pair[1],
            ratio=f"{pair[0]}/{pair[1]}" if pair[1] else f"{pair[0]}/0",
        )

    @app.get("/whatif", response_class=HTMLResponse)
    def whatif(
        credit_id: str = "crd_001_acc_01_2025-01-09",
        reserve_bps: int = Query(default=-1),
    ):
        profile = _profile()
        used = profile.reserve_bps if reserve_bps < 0 else reserve_bps
        split = _split()
        baseline = None
        scenario = None
        note = "Restricted to parameter substitution on a known member set. Not a rail counterfactual."
        if split is not None:
            _items, _credits, by_credit, ledger, credits_by_id = split
            credit = credits_by_id.get(credit_id)
            declared = by_credit.get(credit_id, ()) if credit is not None else ()
            if credit is not None and declared:
                member_ids = tuple(r.item_id for r in declared if r.item_id in ledger)
                rates, fees = load_tax_rates(), load_fees()
                base = recompute(credit, member_ids, ledger, rates, fees, profile.reserve_bps)
                alt = recompute(credit, member_ids, ledger, rates, fees, used)
                baseline = {
                    "ok": base.ok,
                    "residual": format_rupees(base.residual_paise),
                    "bps": profile.reserve_bps,
                    "deltas": len(base.line_deltas),
                }
                scenario = {
                    "ok": alt.ok,
                    "residual": format_rupees(alt.residual_paise),
                    "bps": used,
                    "deltas": len(alt.line_deltas),
                    "same": base.residual_paise == alt.residual_paise and base.ok == alt.ok,
                }
            elif credit is None:
                note = f"Unknown credit {credit_id}."
            else:
                note = "No declared member set — what-if does not invent one."
        presets = (0, 300, 500, 700)
        return _render(
            "whatif.html",
            active="whatif",
            credit_id=credit_id,
            used=used,
            baseline=baseline,
            scenario=scenario,
            note=note,
            presets=presets,
            no_monte_carlo=True,
        )

    @app.get("/controller", response_class=HTMLResponse)
    def controller():
        split = _split()
        profile = _profile()
        as_of = _as_of_day()
        leak_rows = []
        leak_total = ""
        leak_kinds: list[dict[str, object]] = []
        reserve = None
        disputes = None
        drift_rows: list[dict[str, object]] = []
        drift_n = 0
        drift_alerts = 0
        n_gate_a = 0
        if split is not None:
            items, credits, _by, ledger, by_id = split
            leak = sweep_leakage(
                items, credits, as_of=as_of, reserve_lag_days=profile.reserve_release_lag_days
            )
            leak_total = format_rupees(leak.rupees_identified_paise)
            leak_kinds = [
                {"kind": k, "amount": format_rupees(v)}
                for k, v in sorted(leak.by_kind_paise.items())
            ]
            for ev in leak.evidence[:40]:
                leak_rows.append(
                    {
                        "kind": ev.kind,
                        "subject": ev.subject_id,
                        "amount": format_rupees(ev.paise),
                        "note": ev.note,
                    }
                )
            res = reserve_subledger(items, as_of=as_of, lag_days=profile.reserve_release_lag_days)
            reserve = {
                "outstanding": format_rupees(res.outstanding_paise),
                "overdue": res.overdue_count,
                "holds": len(res.holds),
                "identity": res.identity_holds,
            }
            disp = track_disputes(items, as_of=as_of)
            disputes = {
                "n": disp.n_disputes,
                "reconstructed": disp.reconstructed_end_to_end,
                "open7": disp.open_inside_7_days,
            }
            overlay = _overlay()
            if overlay is not None:
                n_gate_a = overlay.n_ok
                points = []
                for cid, mids in overlay.journalable.items():
                    credit = by_id.get(cid)
                    if credit is None:
                        continue
                    members = [ledger[m] for m in mids if m in ledger]
                    points.extend(triples_from_members(members, credit.value_date))
                fitted = regress(points, load_fees())
                drift_n = len(fitted)
                drift_alerts = sum(1 for p in fitted if p.alert)
                for point in fitted[:24]:
                    drift_rows.append(
                        {
                            "instrument": point.instrument.value,
                            "week": point.iso_week,
                            "n": point.n_payments,
                            "effective": point.effective_bps,
                            "contracted": point.contracted_bps,
                            "alert": point.alert,
                        }
                    )
        rungs = []
        for rung in (Rung.NORMAL, Rung.NO_MODEL, Rung.NO_SEARCH, Rung.READ_ONLY, Rung.HALTED):
            pol = policy_for(rung)
            rungs.append(
                {
                    "name": rung.value,
                    "model": pol.allow_model,
                    "search": pol.allow_search,
                    "writes": pol.allow_writes,
                    "process": pol.process_credits,
                    "coverage": "0/239",
                }
            )
        return _render(
            "controller.html",
            active="controller",
            as_of=as_of.isoformat(),
            leak_total=leak_total,
            leak_kinds=leak_kinds,
            leak_rows=leak_rows,
            reserve=reserve,
            disputes=disputes,
            rungs=rungs,
            drift_rows=drift_rows,
            drift_n=drift_n,
            drift_alerts=drift_alerts,
            n_gate_a=n_gate_a,
        )

    @app.get("/asof", response_class=HTMLResponse)
    def asof(seq: int = Query(default=-1)):
        conn = _db()
        equal = True
        counts: Counter[str] = Counter()
        max_seq = 0
        used = 0
        sample = []
        if conn is not None:
            try:
                payloads = load_payloads(conn)
                if payloads:
                    max_seq = payloads[-1][0]
                    used = max_seq if seq < 0 or seq > max_seq else seq
                    sql_view = as_of_view(conn, used)
                    replay = replay_prefix(payloads, used)
                    equal = views_equal(sql_view, replay)
                    counts = Counter(sql_view.values())
                    sample = sorted(sql_view.items())[:24]
            finally:
                conn.close()
        return _render(
            "asof.html",
            active="asof",
            seq=used,
            max_seq=max_seq,
            equal=equal,
            counts=[{"name": k, "n": v} for k, v in counts.most_common()],
            sample=sample,
        )

    @app.get("/evidence", response_class=HTMLResponse)
    def evidence():
        arms = _md_data_rows(Path("artifacts").joinpath("dev", "headline.md"), "arm")
        classes = _md_data_rows(Path("artifacts").joinpath("dev", "per_class.md"), "class")
        providers = _md_data_rows(Path("artifacts").joinpath("p4", "providers.md"), "backend")
        weak = [row for row in classes if len(row) > 2 and row[2].startswith("0/")]
        overlay = _overlay()
        from residual_zero.console.facts import t04_view

        return _render(
            "evidence.html",
            active="evidence",
            arms=arms,
            classes=classes,
            providers=providers,
            weak=weak,
            n_gate_a=overlay.n_ok if overlay is not None else 0,
            n_journalable=overlay.n_journalable if overlay is not None else 0,
            n_mismatch=overlay.n_mismatch if overlay is not None else 0,
            t04_dev=t04_view("dev"),
            t04_test=t04_view("test"),
            a0_exact=_arm_cell(arms, "a0", 2),
            a2_cleared=_arm_cell(arms, "a2", 5),
            a3_assignment_r=_arm_cell(arms, "a3", 4),
        )

    @app.get("/demo", response_class=HTMLResponse)
    def demo():
        overlay = _overlay()
        from residual_zero.console.facts import t04_view

        return _render(
            "demo.html",
            active="demo",
            n_gate_a=overlay.n_ok if overlay is not None else 0,
            n_journalable=overlay.n_journalable if overlay is not None else 0,
            n_mismatch=overlay.n_mismatch if overlay is not None else 0,
            t04_dev=t04_view("dev"),
            t04_test=t04_view("test"),
        )

    @app.get("/proof/{credit_id}", response_class=HTMLResponse)
    def proof_page(credit_id: str):
        from residual_zero.console.proof_explorer import proof_explorer

        blob = proof_explorer(credit_id)
        return _render(
            "proof.html",
            active="proof",
            credit_id=credit_id,
            proof=blob,
            architecture=True,
        )

    @app.get("/mixed", response_class=HTMLResponse)
    def mixed_desk():
        from residual_zero.console.mixed_desk import mixed_counts, mixed_rows

        return _render(
            "mixed.html",
            active="mixed",
            rows=mixed_rows(),
            counts=mixed_counts(),
        )

    @app.get("/challenge", response_class=HTMLResponse)
    def challenge_page(run: str = ""):
        root = Path("fixtures").joinpath("challenges")
        names = (
            "solvable_aggregate.json",
            "ambiguous_refused.json",
            "unsolvable_missing_record.json",
        )
        results = []
        if run == "all":
            for name in names:
                report = inspect_challenge(root.joinpath(name))
                results.append(
                    {
                        "file": name,
                        "credit_id": report.credit_id,
                        "amount": format_rupees(report.amount_paise),
                        "disposition": report.disposition.value,
                        "uniqueness": report.uniqueness.value,
                        "cls": report.exception_class or "—",
                        "pool": report.pool_size,
                        "comment": report.comment,
                    }
                )
        return _render(
            "challenge.html",
            active="challenge",
            results=results,
            ran=bool(results),
        )

    @app.get("/safety", response_class=HTMLResponse)
    def safety():
        injections = ""
        path = Path("artifacts").joinpath("injections.md")
        if path.is_file():
            injections = path.read_text(encoding="utf-8")
        return _render(
            "safety.html",
            active="safety",
            injections=injections,
        )

    @app.get("/alts", response_class=HTMLResponse)
    def alts():
        set_a, set_b, diff = fixture_rival_sets()
        live = Path("artifacts").joinpath("p4", "alt_diff.md")
        live_md = live.read_text(encoding="utf-8") if live.is_file() else ""
        return _render(
            "alts.html",
            active="alts",
            set_a=set_a,
            set_b=set_b,
            only_a=diff.only_a,
            only_b=diff.only_b,
            shared=len(diff.shared),
            symdiff=diff.symmetric_difference_size,
            rendered=render_diff(diff),
            live_md=live_md,
        )

    @app.get("/human", response_class=HTMLResponse)
    def human():
        root = Path("artifacts").joinpath("human_study")
        selected = []
        protocol = ""
        results = {}
        sheets = []
        path = root.joinpath("selected_credits.json")
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            selected = list(payload.get("credit_ids") or [])
        proto = root.joinpath("protocol.md")
        if proto.is_file():
            protocol = proto.read_text(encoding="utf-8")
        res_path = root.joinpath("results.json")
        if res_path.is_file():
            results = json.loads(res_path.read_text(encoding="utf-8"))
        for n in (1, 2, 3):
            csv_path = root.joinpath(f"rater_{n}.csv")
            filled = 0
            total = 0
            if csv_path.is_file():
                lines = csv_path.read_text(encoding="utf-8").splitlines()[1:]
                for line in lines:
                    if not line.strip():
                        continue
                    total += 1
                    parts = line.split(",", 2)
                    if len(parts) > 1 and parts[1].strip():
                        filled += 1
            sheets.append({"n": n, "filled": filled, "total": total})
        return _render(
            "human.html",
            active="human",
            selected=selected,
            protocol=protocol,
            f56=results.get("f56") if isinstance(results, dict) else None,
            f19=results.get("f19") if isinstance(results, dict) else None,
            question=results.get("pre_registered_question") if isinstance(results, dict) else "",
            sheets=sheets,
        )

    def _ledger_ids() -> set[str]:
        split = _split()
        if split is None:
            return set()
        return set(split[3].keys())

    def _recon_rows(parsed) -> list[dict[str, object]]:
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
        matched = match_recon_to_ledger({"rows": rows, "n": len(rows)}, _ledger_ids())
        return list(matched["rows"])

    def _recon_page(rows, error, enabled):
        hits = sum(1 for row in rows if row.get("in_ledger"))
        return _render(
            "recon.html",
            active="recon",
            rows=rows,
            error=error,
            enabled=enabled,
            n=len(rows),
            ledger_hits=hits,
            ledger_misses=max(0, len(rows) - hits),
        )

    def _razorpay_enabled() -> bool:
        path = Path("config").joinpath("razorpay.yaml")
        if not path.is_file():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("enabled:"):
                return line.split(":", 1)[1].strip() == "true"
        return False

    @app.get("/recon", response_class=HTMLResponse)
    def recon_get():
        sample = Path("fixtures").joinpath("recon", "combined_sample.json")
        rows = []
        error = ""
        if sample.is_file():
            try:
                payload = json.loads(sample.read_text(encoding="utf-8"))
                parsed = parse_recon_combined(payload)
                rows = _recon_rows(parsed)
            except (ValueError, json.JSONDecodeError) as exc:
                error = str(exc)
        return _recon_page(rows, error, _razorpay_enabled())

    @app.post("/recon", response_class=HTMLResponse)
    async def recon_post(request: Request):
        """Preview a Razorpay recon payload. Parses and renders; never writes.

        A malformed body answers 400. It used to answer 200 with the error rendered into
        the page, which meant a client — or a monitor — could not distinguish a parsed
        payload from a rejected one by status code.
        """
        error = ""
        rows = []
        status = 200
        try:
            payload = json.loads((await request.body()).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("body must be a JSON object")
            parsed = parse_recon_combined(payload)
            rows = _recon_rows(parsed)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            error = str(exc)
            status = 400
        page = _recon_page(rows, error, _razorpay_enabled())
        return HTMLResponse(page.body, status_code=status) if status != 200 else page

    @app.get("/api/t04")
    def api_t04():
        from residual_zero.console.facts import t04_fields, track04_snapshot
        from residual_zero.qa.finance_tools import get_batch_summary

        snap = track04_snapshot()
        stats = get_batch_summary()
        return JSONResponse(
            {
                "ok": True,
                "writes_cleared": False,
                "source": "artifacts/dev/t04.md + artifacts/test/t04.md",
                "dev": t04_fields("dev"),
                "test": t04_fields("test"),
                "scored": snap.scored,
                "residual_zero": snap.residual_zero,
                "settlement_linked": snap.settlement_linked,
                "unreconciled": snap.unreconciled,
                "stats": {
                    "n_scored": stats.get("scored"),
                    "residual_zero": stats.get("residual_zero"),
                    "ambiguous": stats.get("ambiguous"),
                    "none_found": stats.get("none_found"),
                    "unique": stats.get("unique"),
                    "auto_clear": stats.get("auto_clear"),
                    "false_clears": stats.get("false_clears"),
                    "search_coverage": stats.get("search_coverage"),
                },
                "note": "Official cards. /api/health n_credits is posted overlay size, not scored n.",
            }
        )

    @app.get("/api/credits")
    def api_credits():
        from residual_zero.console.app import _credit_lookup, _enrich, _load_audits

        conn = _db()
        payload = []
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
                        "href": "/credit/" + row["id"],
                    }
                )
        else:
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
                        "href": "/credit/" + cid,
                    }
                )
        return JSONResponse(payload)

    from residual_zero.console.ext_api import mount_ext

    mount_ext(app)
