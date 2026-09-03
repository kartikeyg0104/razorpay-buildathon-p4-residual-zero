"""Controlled multi-step investigation. LLM may pick the next tool. Tools decide truth."""

from __future__ import annotations

import time
from typing import Any, Callable

from residual_zero.qa.finance_intents import FinanceIntent
from residual_zero.qa.finance_tools import TOOL_NAMES, call_finance_tool
from residual_zero.qa.investigate_tools import INVESTIGATE_TOOLS
from residual_zero.semantic.provider import provider_model, live_enabled, record_live_result, select_next_tool

PostJson = Callable[[str, str, bytes], dict[str, Any]]

PROMPT_VERSION = "agent-v1"
MAX_TOOLS = 8
MAX_REPEAT = 2
MAX_NS = 30_000_000_000

STEP_LABEL = {
    "get_transaction": "Retrieved transaction",
    "get_reconciliation": "Retrieved reconciliation",
    "get_settlement_details": "Checked settlement",
    "get_match_candidates": "Retrieved candidates",
    "get_transaction_evidence": "Checked transaction evidence",
    "get_tax_breakdown": "Checked tax lines",
    "get_audit_trail": "Checked audit trail",
    "compare_sources": "Compared sources",
    "get_candidate_equations": "Compared equations",
    "compare_solutions": "Compared alternative solutions",
    "get_proof_explorer": "Opened proof explorer",
    "explain_candidate_rejection": "Explained candidate rejection",
    "explain_verification_failure": "Explained verification failure",
    "get_missing_records": "Checked missing records",
    "get_transaction_timeline": "Checked timeline",
    "find_by_reference": "Looked up reference",
    "find_by_settlement": "Looked up settlement",
    "find_by_invoice": "Looked up invoice",
    "find_by_member": "Looked up member",
    "get_batch_summary": "Retrieved batch summary",
    "get_reconciliation_statistics": "Retrieved reconciliation statistics",
    "get_root_cause": "Retrieved root-cause metrics",
    "get_unreconciled_amount": "Retrieved unreconciled amount",
    "get_ambiguous_transactions": "Listed ambiguous transactions",
    "get_unmatched_transactions": "Listed unmatched transactions",
    "get_top_exceptions": "Retrieved top exceptions",
    "get_exceptions": "Retrieved exceptions",
    "get_verified_transactions": "Listed residual-zero transactions",
    "exception_intelligence": "Compiled exception intelligence",
    "investigate_transaction": "Ran extraction + deterministic lookup",
    "explorer_query": "Queried explorer",
    "get_potentially_recoverable": "Listed potentially recoverable",
}


def _key(name: str, arguments: dict[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
    items = tuple(sorted((str(k), str(v)) for k, v in arguments.items() if v is not None))
    return name, items


def playbook(intent: FinanceIntent, credit_id: str, question: str) -> list[tuple[str, dict[str, Any]]]:
    """Deterministic first investigation. The provider may add later steps only."""
    cid = credit_id
    q = question.casefold()
    if intent == FinanceIntent.REFUSE_CLEAR:
        steps = [("get_reconciliation_statistics", {})]
        if cid:
            steps.append(("get_reconciliation", {"transaction_id": cid}))
        return steps
    if intent in {FinanceIntent.BATCH_SUMMARY, FinanceIntent.PERFORMANCE_ANALYSIS, FinanceIntent.COMPARISON}:
        return [
            ("get_batch_summary", {}),
            ("get_unreconciled_amount", {}),
            ("get_root_cause", {}),
        ]
    if intent == FinanceIntent.ROOT_CAUSE:
        return [
            ("get_root_cause", {}),
            ("get_reconciliation_statistics", {}),
            ("get_top_exceptions", {"limit": 10}),
        ]
    if intent == FinanceIntent.RECOVERABLE:
        return [("get_potentially_recoverable", {"limit": 20}), ("get_root_cause", {})]
    if intent == FinanceIntent.EXPLORER:
        kind = "MISSING_SETTLEMENT"
        if "high-value" in q or "high value" in q:
            kind = "HIGH_VALUE_AMBIGUOUS"
        elif "recoverable" in q:
            kind = "POTENTIALLY_RECOVERABLE"
        return [("explorer_query", {"kind": kind, "limit": 20})]
    if intent == FinanceIntent.UNRECONCILED_ANALYSIS:
        return [("get_unreconciled_amount", {}), ("get_reconciliation_statistics", {})]
    if intent == FinanceIntent.AMBIGUITY_ANALYSIS and not cid:
        return [
            ("get_reconciliation_statistics", {}),
            ("get_ambiguous_transactions", {"limit": 10}),
        ]
    if cid:
        steps = [
            ("get_transaction", {"transaction_id": cid}),
            ("get_reconciliation", {"transaction_id": cid}),
            ("get_settlement_details", {"settlement_id": cid}),
            ("get_match_candidates", {"transaction_id": cid}),
            ("compare_sources", {"transaction_id": cid}),
            ("get_candidate_equations", {"transaction_id": cid}),
        ]
        if intent in {FinanceIntent.TRANSACTION_EXPLANATION, FinanceIntent.TRANSACTION_LOOKUP, FinanceIntent.HUMAN_REVIEW}:
            steps.append(("get_transaction_evidence", {"transaction_id": cid}))
        elif intent == FinanceIntent.AMBIGUITY_ANALYSIS:
            steps.append(("compare_solutions", {"transaction_id": cid}))
            steps.append(("get_proof_explorer", {"transaction_id": cid}))
        elif intent == FinanceIntent.INVESTIGATE:
            steps.append(("exception_intelligence", {"transaction_id": cid}))
        elif intent == FinanceIntent.EXTRACT_REFERENCE:
            steps.append(("investigate_transaction", {"transaction_id": cid}))
        elif intent == FinanceIntent.TAX_ANALYSIS:
            steps.append(("get_tax_breakdown", {"transaction_id": cid}))
        elif intent == FinanceIntent.AUDIT_ANALYSIS:
            steps.append(("get_audit_trail", {"transaction_id": cid}))
        else:
            steps.append(("explain_verification_failure", {"transaction_id": cid}))
        return steps[:MAX_TOOLS]
    if intent == FinanceIntent.EXCEPTION_ANALYSIS:
        return [("get_top_exceptions", {"limit": 10}), ("get_exceptions", {})]
    return [("get_reconciliation_statistics", {})]


def run_agent(
    question: str,
    credit_id: str,
    intent: FinanceIntent,
    post_json: PostJson | None = None,
) -> dict[str, Any]:
    """Execute playbook, then optional provider next-tool picks. Never writes CLEARED."""
    started = time.monotonic_ns()
    tools: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}
    repeats: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
    llm_picks = 0
    stopped = "complete"

    def reject(name: str, arguments: dict[str, Any], source: str, error: str) -> dict[str, Any]:
        """Record a refused tool request. Nothing is executed.

        Rejections are kept out of ``tools`` so they never consume a MAX_TOOLS slot, but
        they are still reported so the audit trail shows what the model asked for.
        """
        out = {"ok": False, "error": error, "tool": name, "writes_cleared": False}
        rejected.append(
            {
                "n": len(rejected) + 1,
                "tool": name,
                "error": error,
                "inputs": {k: v for k, v in arguments.items() if v is not None},
                "source": source,
                "executed": False,
            }
        )
        return out

    def execute(name: str, arguments: dict[str, Any], source: str) -> dict[str, Any]:
        key = _key(name, arguments)
        if repeats.get(key, 0) >= MAX_REPEAT:
            return reject(name, arguments, source, "repeat_limit")
        if name not in TOOL_NAMES:
            return reject(name, arguments, source, "unknown_tool")
        t0 = time.monotonic_ns()
        out = call_finance_tool(name, arguments)
        repeats[key] = repeats.get(key, 0) + 1
        tools.append(
            {
                "n": len(tools) + 1,
                "tool": name,
                "label": STEP_LABEL.get(name, name),
                "inputs": {k: v for k, v in arguments.items() if v is not None},
                "ok": out.get("found", True) is not False and out.get("error") not in {"not_found", "unknown_tool"},
                "latency_ns": time.monotonic_ns() - t0,
                "source": source,
                "output": out,
            }
        )
        evidence[name] = out
        if name == "get_batch_summary" or name == "get_reconciliation_statistics":
            evidence["stats"] = out
        if name == "get_reconciliation":
            evidence["reconciliation"] = out
        if name == "get_transaction":
            evidence["transaction"] = out
        if name == "get_transaction_evidence":
            evidence["pack"] = out
            if isinstance(out.get("reconciliation"), dict):
                evidence["reconciliation"] = out["reconciliation"]
        if name == "get_root_cause":
            evidence["root"] = out
        if name == "exception_intelligence":
            evidence["intel"] = out
        if name == "get_potentially_recoverable":
            evidence["recoverable"] = out
        if name == "explorer_query":
            evidence["explorer"] = out
        if name == "get_unreconciled_amount":
            evidence["unreconciled"] = out
        if name == "get_top_exceptions":
            evidence["top"] = out
        if name == "get_exceptions" or name == "get_ambiguous_transactions":
            evidence["ambiguous" if "ambiguous" in name else "exceptions"] = out
        if name == "investigate_transaction":
            evidence["investigation"] = out
        return out

    for name, arguments in playbook(intent, credit_id, question):
        if len(tools) >= MAX_TOOLS:
            stopped = "tool_limit"
            break
        if time.monotonic_ns() - started >= MAX_NS:
            stopped = "time_limit"
            break
        execute(name, arguments, "playbook")

    remaining = [n for n in (*TOOL_NAMES, *INVESTIGATE_TOOLS) if n in TOOL_NAMES]
    while (
        live_enabled()
        and len(tools) < MAX_TOOLS
        and time.monotonic_ns() - started < MAX_NS
        and credit_id
    ):
        called = [t["tool"] for t in tools]
        nxt, err = select_next_tool(question, called, remaining, credit_id, post_json=post_json)
        if err or not nxt or nxt.get("stop"):
            break
        name = str(nxt.get("tool") or "")
        if name not in TOOL_NAMES:
            execute(name or "invalid_tool", {}, "llm_rejected")
            break
        args = dict(nxt.get("arguments") or {})
        if "transaction_id" not in args and "credit_id" not in args and credit_id:
            args["transaction_id"] = credit_id
        execute(name, args, "llm")
        llm_picks += 1
        if llm_picks >= 3:
            break

    if llm_picks:
        record_live_result(ok=True, llm_picks=llm_picks)

    if len(tools) >= MAX_TOOLS:
        stopped = "tool_limit"
    elif time.monotonic_ns() - started >= MAX_NS:
        stopped = "time_limit"

    steps = [
        {
            "n": t["n"],
            "label": t["label"],
            "tool": t["tool"],
            "ok": t["ok"],
            "source": t["source"],
            "arguments": t.get("inputs") or {},
            "duration": t.get("latency_ns"),
            "latency_ns": t.get("latency_ns"),
            "result_summary": t["label"],
            "evidence_ids": [
                e.get("evidence_id")
                for e in ((t.get("output") or {}).get("evidence") or [])
                if isinstance(e, dict) and e.get("evidence_id")
            ][:8],
        }
        for t in tools
    ]
    return {
        "tools": tools,
        "rejected_tools": rejected,
        "steps": steps,
        "evidence": evidence,
        "stopped": stopped,
        "llm_picks": llm_picks,
        "prompt_version": PROMPT_VERSION,
        "model": provider_model() if live_enabled() else "",
        "writes_cleared": False,
        "latency_ns": time.monotonic_ns() - started,
    }
