"""Corpus-fitted controller. Integer BoW + k-NN. Never writes CLEARED."""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from residual_zero.models import ExceptionClass
from residual_zero.qa.compose import compose
from residual_zero.qa.corpus import LABELS, CorpusDoc
from residual_zero.qa.format import deterministic_answer, render_slots
from residual_zero.qa.retrieve import Intent, RetrievedRows, classify_intent, retrieve
from residual_zero.qa.desk_tools import batch_prose
from residual_zero.qa.train import all_documents, predict_doc, trained
from residual_zero.semantic.provider import (
    provider_model,
    live_enabled,
    request_budget,
    rewrite as provider_rewrite,
)

FIT_FLOOR = 70


def nearest_label(question: str) -> tuple[str, int] | None:
    """Return (doc_id, score) for the closest labelled question. Score is 0–100 integer."""
    q = question.strip()
    if not q:
        return None
    best_id = ""
    best = 0
    for labelled, doc_id in LABELS:
        score = int(fuzz.token_set_ratio(q, labelled))
        if score > best:
            best = score
            best_id = doc_id
    if best < FIT_FLOOR or not best_id:
        return None
    return best_id, best


def rank_documents(question: str, docs: tuple[CorpusDoc, ...]) -> tuple[CorpusDoc | None, int]:
    by_id = {doc.id: doc for doc in docs}
    q = question.casefold()
    for cls in ExceptionClass:
        needle = cls.value.casefold()
        spaced = needle.replace("_", " ")
        if needle in q or spaced in q:
            found = by_id.get("exc_" + cls.value)
            if found is not None:
                display = int(fuzz.token_set_ratio(question, found.title + " " + found.body))
                return found, display
    hit = nearest_label(question)
    if hit is not None:
        doc_id, score = hit
        found = by_id.get(doc_id)
        if found is not None:
            return found, score
    bow_id, bow_score = predict_doc(trained().weights, question)
    if bow_score > 0:
        found = by_id.get(bow_id)
        if found is not None:
            display = int(fuzz.token_set_ratio(question, found.title + " " + found.body))
            return found, display
    best_doc: CorpusDoc | None = None
    best = 0
    for doc in docs:
        blob = doc.title + " " + doc.body
        score = int(fuzz.token_set_ratio(question, blob))
        if score > best:
            best = score
            best_doc = doc
    if best < FIT_FLOOR:
        return None, best
    return best_doc, best


def _ledger_rows(question: str, credit_id: str) -> RetrievedRows:
    intent = classify_intent(question, None)
    cid = credit_id.strip()
    if not cid:
        return RetrievedRows(intent=intent, rows=(), citations=())
    from residual_zero.console.app import _db, _overlay

    conn = _db()
    overlay_rows: RetrievedRows | None = None
    overlay = _overlay()
    if overlay is not None and cid in overlay.by_id:
        gate = overlay.by_id[cid]
        overlay_rows = RetrievedRows(
            intent=intent if intent != Intent.UNRECOGNISED else Intent.CREDIT_DETAIL,
            rows=(
                {
                    "bank_credit_id": cid,
                    "claimed_total_paise": gate.computed_total_paise,
                    "residual_paise": gate.residual_paise,
                    "uniqueness": "AMBIGUOUS",
                    "disposition": "FLAGGED",
                },
                {"member_count": len(gate.member_ids)},
            ),
            citations=(cid, *gate.member_ids[:3]),
        )
    if conn is None:
        return overlay_rows or RetrievedRows(intent=intent, rows=(), citations=())
    try:
        rows = retrieve(intent, {"credit_id": cid}, conn)
    finally:
        conn.close()
    if rows.rows:
        return rows
    return overlay_rows or rows


def _overlay_note(credit_id: str) -> str:
    from residual_zero.console.app import _overlay

    overlay = _overlay()
    cid = credit_id.strip()
    if overlay is None or cid not in overlay.by_id:
        return ""
    gate = overlay.by_id[cid]
    if gate.ok:
        return (
            " Overlay: declared stack re-derives (Gate A). "
            "Search uniqueness stays AMBIGUOUS. Overlay does not write CLEARED."
        )
    return (
        " Overlay: declared stack failed verify_declared. "
        "Overlay does not write CLEARED."
    )


def _qualitative_rewrite(question: str, qualitative: str) -> tuple[str, bool, str]:
    """The provider may rewrite qualitative facts. Amounts stay in ledger slots. Never CLEARED."""
    if not qualitative.strip() or not live_enabled():
        return qualitative, False, ""
    prose, err = provider_rewrite(question, qualitative)
    if prose:
        return prose, True, ""
    return qualitative, False, err


def answer(question: str, credit_id: str = "") -> dict[str, Any]:
    """Fit-time retrieval + finance tools + optional NVIDIA NIM explain. No CLEARED write.

    This is the request boundary for /ask, so the shared provider deadline opens here and
    not in `finance_ask`: this function makes its own qualitative-rewrite call *in addition*
    to everything `finance_ask` does, and budgeting only the inner half left the request
    unbounded across the two. `finance_ask` still opens its own budget for callers that
    reach it directly; nesting keeps the earliest deadline.
    """
    with request_budget():
        return _answer(question, credit_id)


def _answer(question: str, credit_id: str = "") -> dict[str, Any]:
    from residual_zero.qa.finance_controller import finance_ask
    from residual_zero.qa.finance_intents import FinanceIntent, classify_finance_intent

    q = question.strip()
    docs = all_documents()
    model = trained()
    intent = classify_intent(q, None) if q else Intent.UNRECOGNISED
    finance_intent = classify_finance_intent(q) if q else FinanceIntent.UNKNOWN
    finance = finance_ask(q, credit_id) if q else {
        "answer": "",
        "intent": "",
        "citations": (),
        "provider_used": False,
        "provider_error": "",
        "provider_live": live_enabled(),
        "provider_model": "",
        "provider": "fitted",
        "mode": "fallback",
        "writes_cleared": False,
        "evidence_refs": [],
        "decision": "",
        "recommended_action": "",
        "tools_called": [],
        "checks": [],
        "latency_ns": 0,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        "found": True,
    }
    rows = _ledger_rows(q, credit_id) if q else RetrievedRows(intent=Intent.UNRECOGNISED, rows=(), citations=())
    ledger_text = ""
    if q and rows.rows:
        ledger_text = compose(
            q,
            rows,
            ("TOTAL", "RESIDUAL", "DISPOSITION", "UNIQUENESS", "CITATIONS"),
            None,
        )
        ledger_text += _overlay_note(credit_id)
    elif q and not rows.rows:
        ledger_text = deterministic_answer(rows, render_slots(rows))

    doc, score = rank_documents(q, docs) if q else (None, 0)
    product = any(
        token in q.casefold()
        for token in (
            "auto-clear",
            "auto clear",
            "threshold",
            "gate a",
            "cleared",
            "overlay",
            "uniqueness",
            "unreconciled",
            "batch summary",
            "match rate",
        )
    )
    qualitative = ""
    if doc is not None and (product or not rows.rows or doc.id.startswith("exc_")):
        qualitative = doc.body
    provider_used = bool(finance.get("provider_used"))
    provider_error = str(finance.get("provider_error") or "")
    if qualitative:
        qualitative, corpus_live, corpus_err = _qualitative_rewrite(q, qualitative)
        if corpus_live:
            provider_used = True
        if corpus_err and not provider_error:
            provider_error = corpus_err

    keep_corpus = bool(
        doc is not None
        and finance_intent
        not in {
            FinanceIntent.REFUSE_CLEAR,
            FinanceIntent.TRANSACTION_EXPLANATION,
            FinanceIntent.TRANSACTION_LOOKUP,
            FinanceIntent.INVESTIGATE,
            FinanceIntent.CLOSE_BRIEFING,
        }
        and (
            intent == Intent.PRODUCT_POLICY
            or (doc.id.startswith("exc_") if doc is not None else False)
            or (doc.id == "a3_cleared" if doc is not None else False)
        )
    )
    parts: list[str] = []
    if finance_intent == FinanceIntent.BATCH_SUMMARY or (
        intent == Intent.BATCH_SUMMARY
        and finance_intent
        not in {
            FinanceIntent.UNRECONCILED_ANALYSIS,
            FinanceIntent.PERFORMANCE_ANALYSIS,
            FinanceIntent.AMBIGUITY_ANALYSIS,
            FinanceIntent.COMPARISON,
        }
    ):
        parts.append(str(finance.get("answer") or batch_prose()))
        keep_corpus = False
    elif finance_intent in {
        FinanceIntent.TRANSACTION_EXPLANATION,
        FinanceIntent.TRANSACTION_LOOKUP,
        FinanceIntent.AMBIGUITY_ANALYSIS,
        FinanceIntent.UNRECONCILED_ANALYSIS,
        FinanceIntent.REFUSE_CLEAR,
        FinanceIntent.EXCEPTION_ANALYSIS,
        FinanceIntent.PERFORMANCE_ANALYSIS,
        FinanceIntent.COMPARISON,
        FinanceIntent.HUMAN_REVIEW,
        FinanceIntent.EXTRACT_REFERENCE,
        FinanceIntent.ROOT_CAUSE,
        FinanceIntent.EXPLORER,
        FinanceIntent.INVESTIGATE,
        FinanceIntent.RECOVERABLE,
        FinanceIntent.CLOSE_BRIEFING,
    } and not keep_corpus:
        parts.append(str(finance.get("answer") or ""))
    if keep_corpus and qualitative:
        parts.append(qualitative)
    elif qualitative and not parts:
        parts.append(qualitative)
    if ledger_text and rows.rows and keep_corpus:
        parts.append(ledger_text)
    elif ledger_text and doc is None and not parts:
        parts.append(ledger_text)
    if not parts and finance.get("answer"):
        parts.append(str(finance["answer"]))
    text = " ".join(p for p in parts if p).strip()
    if not text:
        text = "I cannot answer that from the fitted corpus or the reconciled ledger."

    citations = list(rows.citations)
    for extra in finance.get("citations") or ():
        if extra not in citations:
            citations.append(extra)
    source = ""
    if doc is not None:
        source = doc.source
        if doc.id not in citations:
            citations.append(doc.id)

    provider = "fitted"
    if finance.get("provider_used"):
        provider = str(finance.get("provider") or provider_model())
    elif provider_used:
        provider = provider_model()
    elif str(finance.get("mode") or "") == "fallback" and not keep_corpus and finance.get("answer"):
        provider = "fallback"

    return {
        "ok": True,
        "intent": str(finance.get("intent") or (intent.value if q else "")),
        "legacy_intent": intent.value if q else "",
        "answer": text,
        "citations": tuple(citations),
        "doc_id": doc.id if doc is not None else "",
        "doc_title": doc.title if doc is not None else "",
        "source": source,
        "fit_score": score,
        "n_docs": model.n_docs,
        "n_labels": model.n_labels,
        "n_train": model.n_train,
        "n_holdout": model.n_holdout,
        "n_holdout_ok": model.n_holdout_ok,
        "n_credits": model.n_credits,
        "holdout": f"{model.n_holdout_ok}/{model.n_holdout}",
        "writes_cleared": False,
        "trained": True,
        "provider_live": live_enabled(),
        "provider_used": provider_used,
        "provider_error": provider_error,
        "provider_model": provider_model() if live_enabled() else "",
        "provider": provider,
        "mode": "llm" if provider_used else str(finance.get("mode") or "fitted"),
        "llm_used": provider_used,
        "evidence": finance.get("evidence") or {},
        "evidence_refs": finance.get("evidence_refs") or [],
        "checks": finance.get("checks") or [],
        "decision": finance.get("decision") or "",
        "recommended_action": finance.get("recommended_action") or "",
        "tools_called": finance.get("tools_called") or [],
        "investigation_steps": finance.get("investigation_steps") or [],
        "latency_ns": finance.get("latency_ns") or 0,
        "usage": finance.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0},
        "found": finance.get("found", True),
        "credit_id": finance.get("credit_id") or credit_id,
    }
