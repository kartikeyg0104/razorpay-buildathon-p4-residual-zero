"""AI finance controller: intent → tools → evidence → template → optional LLM explain."""

from __future__ import annotations

import time
from typing import Any, Callable

from residual_zero.qa.finance_audit import record_audit
from residual_zero.qa.finance_intents import FinanceIntent, classify_finance_intent, extract_credit_id
from residual_zero.qa.finance_templates import (
    ambiguity_text,
    batch_summary_text,
    briefing_text,
    comparison_text,
    exception_text,
    insufficient_text,
    not_found_text,
    performance_text,
    product_policy_note,
    refuse_clear_text,
    review_assistant_text,
    transaction_explanation_text,
    unreconciled_text,
)
from residual_zero.qa.agent_loop import run_agent
from residual_zero.qa.finance_tools import call_finance_tool
from residual_zero.qa.finance_validate import validate_answer
from residual_zero.semantic.provider import (
    ai_provider,
    explain_evidence,
    provider_model,
    live_enabled,
    request_budget,
)

PostJson = Callable[[str, str, bytes], dict[str, Any]]


def _investigation_text(inv: dict[str, Any]) -> str:
    cand = (inv.get("extraction") or {}).get("candidate") or {}
    recon = inv.get("recon") or {}
    parts = ["AI EVIDENCE DISCOVERY (candidate only, not a match)"]
    for key in ("source", "settlement_id", "reference", "invoice_id", "member_id", "payment_type", "date"):
        if cand.get(key):
            parts.append(f"{key}={cand[key]}")
    parts.append(f"verified_fields={inv.get('verified_field_count')}")
    parts.append(f"deterministic_status={recon.get('status')}")
    if recon.get("residual_display") is not None:
        parts.append(f"residual={recon.get('residual_display')}")
    if recon.get("status") == "NOT_RECONCILED":
        parts.append(
            f"AI identified candidate evidence, but deterministic reconciliation produced a residual of "
            f"{recon.get('residual_display')}. No reconciliation was established."
        )
    else:
        parts.append("Lookup must succeed and residual must be 0 before this is a reconciliation.")
    parts.append("Overlay does not write CLEARED.")
    return "\n".join(parts)


def _tool(log: list[dict[str, Any]], name: str, **arguments: Any) -> dict[str, Any]:
    started = time.monotonic_ns()
    out = call_finance_tool(name, arguments)
    elapsed = time.monotonic_ns() - started
    log.append(
        {
            "tool": name,
            "inputs": {k: v for k, v in arguments.items() if v is not None},
            "ok": out.get("found", True) is not False and out.get("error") not in {"not_found", "unknown_tool"},
            "latency_ns": elapsed,
            "output": out,
        }
    )
    return out


def _sections(intent: FinanceIntent, text: str, evidence: dict[str, Any]) -> dict[str, str]:
    recon = evidence.get("reconciliation") if isinstance(evidence.get("reconciliation"), dict) else {}
    stats = evidence.get("stats") if isinstance(evidence.get("stats"), dict) else {}
    decision = str(recon.get("status") or "")
    recommended = "Leave flagged. Overlay does not write CLEARED."
    if recon.get("uniqueness") == "AMBIGUOUS":
        recommended = "Human review of settlement/member metadata. Do not auto-select a subset."
    elif recon.get("uniqueness") == "NONE_FOUND":
        recommended = "Inspect missing ledger or settlement rows. Do not invent members."
    if intent in {FinanceIntent.BATCH_SUMMARY, FinanceIntent.PERFORMANCE_ANALYSIS, FinanceIntent.COMPARISON}:
        recommended = "Keep uniqueness refuse-all. Do not treat residual-zero as CLEARED."
        decision = "NO_AUTO_CLEAR"
    if intent == FinanceIntent.REFUSE_CLEAR:
        decision = "REFUSED"
        recommended = "Human review only. The AI finance controller cannot clear."
    return {
        "summary": text.split("\n", 1)[0][:240],
        "decision": decision,
        "recommended_action": recommended,
        "headline": (
            f"{stats.get('scored')} scored · residual-zero {stats.get('residual_zero')} · "
            f"auto-clear {stats.get('auto_clear')}"
            if stats
            else ""
        ),
    }


def finance_ask(
    question: str,
    credit_id: str = "",
    post_json: PostJson | None = None,
) -> dict[str, Any]:
    """Investigate using tools. LLM may explain; fallback templates always work.

    Every provider call made while answering shares one deadline (AI_TOTAL_BUDGET_S).
    AI_TIMEOUT_S caps a single call, but one answer can make up to four in series, so
    without a shared budget the request had no upper bound. When the budget runs out the
    remaining calls are skipped and the deterministic templates stand — the same fallback
    a provider failure takes, and the templates are the authoritative content either way.
    """
    with request_budget():
        return _finance_ask(question, credit_id, post_json)


def _finance_ask(
    question: str,
    credit_id: str = "",
    post_json: PostJson | None = None,
) -> dict[str, Any]:
    started = time.monotonic_ns()
    q = question.strip()
    intent = classify_finance_intent(q) if q else FinanceIntent.UNKNOWN
    cid = extract_credit_id(q, credit_id)
    tools: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}
    agent_steps: list[dict[str, Any]] = []
    text = insufficient_text()
    found = True

    if not q:
        text = "Ask about the reconciliation batch. The AI finance controller only reads structured tools."
        intent = FinanceIntent.UNKNOWN
    elif intent == FinanceIntent.REFUSE_CLEAR:
        evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
        if cid:
            evidence["reconciliation"] = _tool(tools, "get_reconciliation", transaction_id=cid)
        text = refuse_clear_text()
    elif intent == FinanceIntent.PRODUCT_POLICY:
        evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
        text = (
            performance_text(evidence["stats"], q) + " " + product_policy_note()
        )
    elif intent in {FinanceIntent.BATCH_SUMMARY}:
        evidence["stats"] = _tool(tools, "get_batch_summary")
        text = batch_summary_text(evidence["stats"])
    elif intent == FinanceIntent.CLOSE_BRIEFING:
        evidence["exposure"] = _tool(tools, "get_exposure_queue", limit=5)
        evidence["dupes"] = _tool(tools, "get_duplicate_utrs")
        text = briefing_text(evidence["exposure"], evidence["dupes"])
    elif intent == FinanceIntent.UNRECONCILED_ANALYSIS:
        evidence["unreconciled"] = _tool(tools, "get_unreconciled_amount")
        evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
        text = unreconciled_text(evidence["unreconciled"])
    elif intent == FinanceIntent.PERFORMANCE_ANALYSIS:
        evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
        text = performance_text(evidence["stats"], q)
    elif intent == FinanceIntent.COMPARISON:
        evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
        evidence["verified"] = _tool(tools, "get_verified_transactions", limit=5)
        evidence["ambiguous"] = _tool(tools, "get_ambiguous_transactions", limit=5)
        text = comparison_text(evidence["stats"])
    elif intent == FinanceIntent.EXCEPTION_ANALYSIS:
        if "missing ledger" in q.casefold() or "missing record" in q.casefold():
            evidence["exceptions"] = _tool(tools, "get_unmatched_transactions", limit=10)
            evidence["top"] = _tool(tools, "get_top_exceptions", limit=10)
            text = exception_text(evidence["top"], q)
        elif "missing refund" in q.casefold() or "tax mismatch" in q.casefold():
            evidence["top"] = _tool(tools, "get_top_exceptions", limit=10)
            if cid:
                evidence["tax"] = _tool(tools, "get_tax_breakdown", transaction_id=cid)
            text = exception_text(evidence["top"], q)
        elif "settlement report is missing" in q.casefold():
            evidence["top"] = _tool(tools, "get_top_exceptions", limit=10)
            text = exception_text(evidence["top"], q)
        else:
            wanted = None
            if "ambiguous" in q.casefold():
                wanted = "AMBIGUOUS"
            evidence["exceptions"] = _tool(tools, "get_exceptions", exception_type=wanted)
            evidence["top"] = _tool(tools, "get_top_exceptions", limit=10)
            evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
            text = exception_text(evidence["top"], q)
    elif intent == FinanceIntent.AMBIGUITY_ANALYSIS:
        if cid:
            agent = run_agent(q, cid, intent, post_json=post_json)
            tools.extend(agent["tools"])
            evidence.update(agent["evidence"])
            agent_steps = list(agent["steps"])
            txn = evidence.get("transaction") or evidence.get("get_transaction") or {}
            recon = evidence.get("reconciliation") or evidence.get("get_reconciliation") or {}
            if txn.get("found") is False and recon.get("found") is False:
                found = False
                text = not_found_text(cid)
            else:
                evidence["stats"] = evidence.get("stats") or {}
                text = ambiguity_text(evidence["stats"], evidence)
                proof = evidence.get("get_proof_explorer") or evidence.get("compare_solutions") or {}
                if proof.get("thesis"):
                    text += "\n" + str(proof["thesis"])
                text += " The controller will not pick a winner. Overlay does not write CLEARED."
        else:
            evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
            evidence["ambiguous"] = _tool(tools, "get_exceptions", exception_type="AMBIGUOUS")
            text = ambiguity_text(evidence["stats"], evidence)
    elif intent == FinanceIntent.SETTLEMENT_ANALYSIS:
        evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
        evidence["top"] = _tool(tools, "get_top_exceptions", limit=10)
        if cid:
            evidence["settlement"] = _tool(tools, "get_settlement_details", settlement_id=cid)
        text = exception_text(evidence["top"], q)
    elif intent == FinanceIntent.TAX_ANALYSIS:
        if cid:
            evidence["tax"] = _tool(tools, "get_tax_breakdown", transaction_id=cid)
            evidence["pack"] = _tool(tools, "get_transaction_evidence", transaction_id=cid)
            text = transaction_explanation_text(evidence["pack"])
        else:
            evidence["top"] = _tool(tools, "get_top_exceptions", limit=10)
            text = exception_text(evidence["top"], q)
    elif intent == FinanceIntent.AUDIT_ANALYSIS:
        if not cid:
            text = insufficient_text()
        else:
            evidence["audit"] = _tool(tools, "get_audit_trail", transaction_id=cid)
            evidence["pack"] = _tool(tools, "get_transaction_evidence", transaction_id=cid)
            if not evidence["pack"].get("found"):
                found = False
                text = not_found_text(cid)
            else:
                text = transaction_explanation_text(evidence["pack"])
    elif intent == FinanceIntent.EXTRACT_REFERENCE:
        if not cid:
            text = insufficient_text()
        else:
            agent = run_agent(q, cid, intent, post_json=post_json)
            tools.extend(agent["tools"])
            evidence.update(agent["evidence"])
            agent_steps = list(agent["steps"])
            inv = evidence.get("investigation") or evidence.get("explain_verification_failure") or {}
            if not inv.get("found"):
                found = False
                text = not_found_text(cid)
            else:
                text = _investigation_text(inv) if inv.get("extraction") else str(inv.get("why") or inv.get("summary") or "")
            cmp = evidence.get("compare_sources") or {}
            if cmp.get("bank_minus_settlement_display"):
                text += (
                    f"\nSource comparison residual {cmp.get('bank_minus_settlement_display')}. "
                    "Computed by compare_sources. Overlay does not write CLEARED."
                )
    elif intent == FinanceIntent.INVESTIGATE:
        if not cid:
            text = insufficient_text()
        else:
            agent = run_agent(q, cid, intent, post_json=post_json)
            tools.extend(agent["tools"])
            evidence.update(agent["evidence"])
            agent_steps = list(agent["steps"])
            inv = evidence.get("intel") or {}
            if not inv.get("found"):
                found = False
                text = not_found_text(cid)
            else:
                text = str(inv.get("summary") or "")
            cmp = evidence.get("compare_sources") or {}
            if cmp.get("found"):
                text += (
                    f"\nSources compared. Bank minus settlement "
                    f"{cmp.get('bank_minus_settlement_display')}. "
                    "The AI did not calculate this difference."
                )
    elif intent == FinanceIntent.ROOT_CAUSE:
        evidence["root"] = _tool(tools, "get_root_cause")
        text = str(evidence["root"].get("text") or "")
    elif intent == FinanceIntent.RECOVERABLE:
        evidence["recoverable"] = _tool(tools, "get_potentially_recoverable", limit=20)
        n = evidence["recoverable"].get("n")
        text = (
            f"POTENTIALLY_RECOVERABLE: {n} credits have extracted identifiers that look up a "
            "structured record not already proven residual-zero. This is not a match rate. "
            "Overlay does not write CLEARED."
        )
    elif intent == FinanceIntent.EXPLORER:
        kind = "MISSING_SETTLEMENT"
        folded = q.casefold()
        if "high-value" in folded or "high value" in folded or "highest-value" in folded or "highest value" in folded:
            kind = "HIGH_VALUE_AMBIGUOUS"
        elif "refund" in folded:
            kind = "REFUND_MISMATCH"
        elif "disagree" in folded:
            kind = "LEDGER_SETTLEMENT_DISAGREE"
        elif "reference" in folded and "verification" in folded:
            kind = "UNVERIFIED_EXTRACT"
        elif "settlement" in folded and "description" in folded:
            kind = "DESCRIPTION_HAS_SETTLEMENT_WORD"
        elif "recoverable" in folded:
            kind = "POTENTIALLY_RECOVERABLE"
        elif "missing ledger" in folded:
            kind = "MISSING_LEDGER"
        evidence["explorer"] = _tool(tools, "explorer_query", kind=kind, limit=20)
        rows = evidence["explorer"].get("rows") or []
        ids = ", ".join(str(r.get("transaction_id")) for r in rows[:8]) or "(none)"
        text = (
            f"Explorer {kind}: {evidence['explorer'].get('n')} rows. "
            f"Sample: {ids}. Not a reconciliation. Overlay does not write CLEARED."
        )
    elif intent in {
        FinanceIntent.TRANSACTION_EXPLANATION,
        FinanceIntent.TRANSACTION_LOOKUP,
        FinanceIntent.HUMAN_REVIEW,
    }:
        if intent == FinanceIntent.HUMAN_REVIEW and not cid:
            evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
            evidence["top"] = _tool(tools, "get_top_exceptions", limit=10)
            evidence["ambiguous"] = _tool(tools, "get_exceptions", exception_type="AMBIGUOUS")
            text = (
                exception_text(evidence["top"], q)
                + " Human review is required for AMBIGUOUS rows. "
                "The AI finance controller cannot approve a clear. Overlay does not write CLEARED."
            )
        elif not cid:
            text = insufficient_text()
        else:
            agent = run_agent(q, cid, intent, post_json=post_json)
            tools.extend(agent["tools"])
            evidence.update(agent["evidence"])
            agent_steps = list(agent["steps"])
            pack = evidence.get("pack") or evidence.get("get_transaction_evidence") or {}
            if not pack.get("found"):
                txn = evidence.get("transaction") or {}
                recon = evidence.get("reconciliation") or {}
                if txn.get("found") or recon.get("found"):
                    pack = {
                        "found": True,
                        "transaction": txn,
                        "reconciliation": recon,
                        "forensic": evidence.get("forensic") or {},
                    }
            if not pack.get("found"):
                found = False
                text = not_found_text(cid)
            else:
                evidence["transaction"] = pack.get("transaction") or evidence.get("transaction") or {}
                evidence["reconciliation"] = pack.get("reconciliation") or evidence.get("reconciliation") or {}
                evidence["forensic"] = pack.get("forensic") or {}
                if intent == FinanceIntent.HUMAN_REVIEW:
                    text = review_assistant_text(pack)
                elif intent == FinanceIntent.TRANSACTION_LOOKUP:
                    recon = pack.get("reconciliation") or {}
                    text = (
                        f"Transaction {cid}: amount {recon.get('bank_amount_display')}, "
                        f"residual {recon.get('residual_display')}, uniqueness {recon.get('uniqueness')}, "
                        f"disposition {recon.get('disposition') or 'FLAGGED'}. "
                        "Overlay does not write CLEARED."
                    )
                else:
                    text = transaction_explanation_text(pack)
                recon_pack = pack.get("reconciliation") or {}
                cmp = evidence.get("compare_sources") or {}
                if cmp.get("found") and recon_pack.get("uniqueness") == "AMBIGUOUS":
                    text += (
                        " Two residual-zero explanations can exist. "
                        "The controller will not pick one. Overlay does not write CLEARED."
                    )
    else:
        evidence["stats"] = _tool(tools, "get_reconciliation_statistics")
        if cid:
            pack = _tool(tools, "get_transaction_evidence", transaction_id=cid)
            evidence["pack"] = pack
            if pack.get("found"):
                text = transaction_explanation_text(pack)
            else:
                found = False
                text = not_found_text(cid)
        else:
            text = insufficient_text() + " " + product_policy_note()

    provider_used = False
    provider_error = ""
    mode = "fallback"
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    provider_name = "fallback"
    if live_enabled() and found and text:
        prose, provider_error, usage = explain_evidence(q, evidence, text, post_json=post_json)
        if prose:
            ok, why = validate_answer(prose, evidence, q, intent=getattr(intent, "value", str(intent)))
            if ok:
                text = prose
                provider_used = True
                mode = "llm"
                provider_name = provider_model()
            else:
                provider_error = provider_error or why
                provider_used = False
                mode = "fallback"
        else:
            mode = "fallback"
            provider_name = "fallback"
    elif live_enabled():
        mode = "fallback"
        provider_error = provider_error or "not applicable"
    else:
        mode = "fallback"
        provider_error = provider_error or "live provider off"

    # The answer actually returned — model prose that passed validation above, or the
    # deterministic template — is validated once more here. A template is kept even if this
    # fails, because the template IS the engine's own rendering and suppressing it would
    # leave the operator with nothing. The boolean already reached the AI audit log; the
    # reason string was discarded and the `if not ok_claim: pass` branch did nothing, so a
    # failing template was invisible to a caller. Both are now returned (found 2026-09).
    answer_validated, answer_validation_why = validate_answer(text, evidence, q)

    sections = _sections(intent, text, evidence)
    refs: list[dict[str, Any]] = []
    for blob in evidence.values():
        if isinstance(blob, dict):
            refs.extend(list(blob.get("evidence") or []))
            pack = blob.get("reconciliation") if isinstance(blob.get("reconciliation"), dict) else None
            if pack:
                refs.extend(list(pack.get("evidence") or []))
    citations = []
    if cid:
        citations.append(cid)
    for ref in refs:
        rec = str(ref.get("source_record_id") or "")
        if rec and rec not in citations:
            citations.append(rec)
        if len(citations) >= 8:
            break

    latency_ns = time.monotonic_ns() - started
    inv = evidence.get("investigation") or evidence.get("intel") or {}
    if isinstance(inv, dict) and isinstance(inv.get("investigation"), dict):
        inv = inv.get("investigation") or inv
    extracted = []
    verified = []
    prompt_version = ""
    if isinstance(inv, dict):
        extracted = [
            {"field": r.get("field"), "value": r.get("value"), "method": r.get("method")}
            for r in (inv.get("validated_fields") or [])[:24]
        ]
        verified = [r.get("field") for r in (inv.get("validated_fields") or []) if r.get("verified")]
        prompt_version = str((inv.get("extraction") or {}).get("prompt_version") or "")
        if not prompt_version and isinstance(inv.get("investigation"), dict):
            prompt_version = str((inv["investigation"].get("extraction") or {}).get("prompt_version") or "")
    recon_status = ""
    if isinstance(evidence.get("reconciliation"), dict):
        recon_status = str(evidence["reconciliation"].get("status") or "")
    elif isinstance(inv, dict):
        recon_status = str((inv.get("recon") or {}).get("status") or "")
    record_audit(
        {
            "ai_run_id": f"{started}-{intent.value}",
            "timestamp_ns": started,
            "question": q,
            "intent": intent.value,
            "transaction_id": cid,
            "credit_id": cid,
            "tools": [
                {
                    "tool": t["tool"],
                    "inputs": t.get("inputs"),
                    "ok": t.get("ok"),
                    "output_error": (
                        (t.get("output") or {}).get("error")
                        if isinstance(t.get("output"), dict)
                        else None
                    ),
                }
                for t in tools
            ],
            "investigation_steps": agent_steps,
            "model": provider_model() if provider_used else "",
            "prompt_version": prompt_version,
            "extracted_fields": extracted,
            "verified_fields": verified,
            "final_reconciliation_status": recon_status,
            "provider": provider_name,
            "mode": mode,
            "answer": text,
            "evidence_ids": [r.get("evidence_id") for r in refs[:20]],
            "latency_ns": latency_ns,
            "usage": usage,
            "error": provider_error,
            "fallback": mode == "fallback",
            "claim_validation": answer_validated,
            "claim_validation_why": answer_validation_why,
            "writes_cleared": False,
        }
    )
    return {
        "ok": True,
        "found": found,
        "intent": intent.value,
        "answer": text,
        "mode": mode,
        "llm_used": provider_used,
        "provider_live": live_enabled(),
        "provider_used": provider_used,
        "provider_error": provider_error,
        "provider_model": provider_model() if live_enabled() else "",
        "provider": provider_name if provider_used else "fallback",
        "ai_provider": ai_provider(),
        "writes_cleared": False,
        "answer_validated": answer_validated,
        "answer_validation": answer_validation_why,
        "credit_id": cid,
        "citations": tuple(citations),
        "evidence": evidence,
        "evidence_refs": refs[:24],
        "checks": (evidence.get("pack") or {}).get("checks") if isinstance(evidence.get("pack"), dict) else [],
        "decision": sections["decision"],
        "recommended_action": sections["recommended_action"],
        "summary": sections["summary"],
        "headline": sections["headline"],
        "tools_called": [t["tool"] for t in tools],
        "investigation_steps": agent_steps or [
            {"n": i + 1, "label": t.get("tool"), "tool": t.get("tool"), "ok": t.get("ok"), "source": "controller"}
            for i, t in enumerate(tools)
        ],
        "tool_latency_ns": sum(int(t.get("latency_ns") or 0) for t in tools),
        "latency_ns": latency_ns,
        "usage": usage,
        "style": intent.value,
    }
