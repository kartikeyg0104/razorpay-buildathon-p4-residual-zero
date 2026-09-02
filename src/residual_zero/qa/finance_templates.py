"""Deterministic answer templates from tool JSON. Never invent figures."""

from __future__ import annotations

from typing import Any, Mapping


def _s(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def batch_summary_text(stats: Mapping[str, Any]) -> str:
    test = stats.get("test") if isinstance(stats.get("test"), dict) else {}
    return (
        "BATCH SUMMARY\n"
        f"{_s(stats.get('scored'))} transactions processed on the official dev split.\n"
        f"{_s(stats.get('residual_zero'))} have residual-zero explanations.\n"
        f"{_s(stats.get('settlement_linked'))} are settlement/member-linked.\n"
        f"{_s(stats.get('ambiguous'))} remain ambiguous under current uniqueness rules.\n"
        f"{_s(stats.get('none_found'))} have no valid explanation.\n"
        f"{_s(stats.get('budget_exceeded'))} exceeded the search budget.\n"
        f"{_s(stats.get('auto_clear'))} were auto-cleared.\n"
        f"{_s(stats.get('false_clears'))} false clears were recorded.\n"
        f"Search coverage {_s(stats.get('search_coverage'))}. "
        f"Unreconciled {_s(stats.get('unreconciled_display'))}. "
        "The system deliberately routed ambiguous cases to review rather than guessing. "
        f"Official test: residual-zero {_s(test.get('residual_zero'))}, "
        f"ambiguous {_s(test.get('ambiguous'))}, auto-clear {_s(test.get('auto_clear'))}, "
        f"false clears {_s(test.get('false_clears'))}, "
        f"search coverage {_s(test.get('search_coverage'))}. "
        "Exact is not auto-clear. Overlay does not write CLEARED. Search auto-clear 0."
    )


def batch_insight_text(stats: Mapping[str, Any]) -> str:
    test = stats.get("test") if isinstance(stats.get("test"), dict) else {}
    return (
        f"{_s(stats.get('residual_zero'))} of the official dev batch reached residual-zero. "
        f"Official test residual-zero is {_s(test.get('residual_zero'))}. "
        f"The remaining transactions are primarily blocked by ambiguity "
        f"({_s(stats.get('ambiguous'))} dev / {_s(test.get('ambiguous'))} test), "
        "missing source records, or conflicting financial evidence. "
        f"{_s(stats.get('auto_clear'))} transactions were auto-cleared. "
        f"{_s(stats.get('false_clears'))} false clears. "
        "The deterministic reconciliation engine did not guess. Overlay does not write CLEARED."
    )


def transaction_explanation_text(evidence: Mapping[str, Any]) -> str:
    recon = evidence.get("reconciliation") if isinstance(evidence.get("reconciliation"), dict) else evidence
    txn = evidence.get("transaction") if isinstance(evidence.get("transaction"), dict) else {}
    forensic = evidence.get("forensic") if isinstance(evidence.get("forensic"), dict) else {}
    amount = _s(recon.get("bank_amount_display") or txn.get("bank_amount_display"))
    residual = _s(recon.get("residual_display"))
    matched = _s(recon.get("matched_count"))
    solutions = _s(recon.get("solution_count"))
    uniqueness = _s(recon.get("uniqueness"))
    status = _s(recon.get("status"))
    disposition = _s(recon.get("disposition"), "FLAGGED")
    body = (
        "WHY THIS DID NOT AUTO-CLEAR\n"
        f"Bank credit: {amount}\n"
        f"Matched records: {matched}\n"
        f"Residual: {residual}\n"
        f"Solutions: {solutions}\n"
        f"Uniqueness: {uniqueness}\n"
        f"Status: {status}\n"
        f"Disposition: {disposition}\n"
    )
    if recon.get("residual_paise") == 0 and uniqueness == "AMBIGUOUS":
        body += (
            "The transaction has an exact mathematical reconciliation with a residual of "
            f"{residual}, but the engine found {solutions} valid ledger explanations. "
            "Because the explanation is not unique, automatic clearing was blocked and "
            "the transaction requires human review. Overlay does not write CLEARED."
        )
    elif uniqueness == "NONE_FOUND" or status == "UNMATCHED":
        why = _s(forensic.get("recovery_why"), "No complete permitted combination equals the bank credit.")
        body += (
            f"{why} Automation stopped because search uniqueness is {uniqueness}. "
            "Recommended action: inspect missing ledger or settlement rows, then leave the "
            "row flagged. Overlay does not write CLEARED."
        )
    else:
        body += (
            f"Disposition stays {disposition}. Uniqueness is {uniqueness}, so auto-clear is refused. "
            "Overlay does not write CLEARED."
        )
    return body


def ambiguity_text(stats: Mapping[str, Any], evidence: Mapping[str, Any] | None = None) -> str:
    recon = {}
    if evidence and isinstance(evidence.get("reconciliation"), dict):
        recon = evidence["reconciliation"]
    if recon:
        return (
            "WHAT MATCHES / WHY AMBIGUOUS\n"
            f"Residual {_s(recon.get('residual_display'))} with "
            f"{_s(recon.get('solution_count'))} valid explanations and "
            f"{_s(recon.get('matched_count'))} named members. "
            "Both combinations satisfy the deterministic financial equation. "
            "No authoritative evidence distinguishes them. "
            "Selecting one would introduce an unsupported financial assumption, so the "
            "transaction remains AMBIGUOUS and requires human review. "
            "The AI finance controller will not pick a winner. Overlay does not write CLEARED."
        )
    return (
        f"{_s(stats.get('ambiguous'))} transactions are ambiguous on the official dev split "
        f"(test {_s((stats.get('test') or {}).get('ambiguous'))}). "
        "Multiple financially valid explanations exist. Choosing one would require an unsupported "
        "assumption, so the deterministic reconciliation engine refused auto-clear. "
        "Search auto-clear 0. Overlay does not write CLEARED."
    )


def unreconciled_text(blob: Mapping[str, Any]) -> str:
    return (
        f"Total unreconciled amount is {_s(blob.get('unreconciled_display'))} "
        f"({_s(blob.get('unreconciled_paise'))} paise from books). "
        f"Overlay open residual {_s(blob.get('overlay_open_display'))}. "
        "Auto-clear 0. Overlay does not write CLEARED."
    )


def performance_text(stats: Mapping[str, Any], question: str) -> str:
    q = question.casefold()
    if "yesterday" in q or "today" in q:
        return (
            "No transactions were auto-cleared in the available dataset. "
            f"Official auto-clear {_s(stats.get('auto_clear'))}; false clears {_s(stats.get('false_clears'))}. "
            "Overlay does not write CLEARED."
        )
    if "false clear" in q:
        return (
            f"False clears: {_s(stats.get('false_clears'))}. "
            "The uniqueness gate blocked auto-clear. Overlay does not write CLEARED."
        )
    if "residual" in q:
        return (
            f"Residual-zero rate is {_s(stats.get('residual_zero'))} on official dev "
            f"and {_s((stats.get('test') or {}).get('residual_zero'))} on official test. "
            "Residual-zero is not auto-clear. Overlay does not write CLEARED."
        )
    if "search" in q or "coverage" in q:
        return (
            f"Search coverage {_s(stats.get('search_coverage'))} dev, "
            f"{_s((stats.get('test') or {}).get('search_coverage'))} test. "
            "A completed search is not a clear. Overlay does not write CLEARED."
        )
    return (
        f"Auto-clear {_s(stats.get('auto_clear'))}/{_s(stats.get('scored'))}. "
        f"False clears {_s(stats.get('false_clears'))}. "
        f"Unique {_s(stats.get('unique'))}. Overlay does not write CLEARED."
    )


def refuse_clear_text() -> str:
    return (
        "I cannot authorize a financial clear because the deterministic reconciliation "
        "engine has not established a unique verified explanation. "
        "The AI finance controller does not write CLEARED. "
        "Human review is required for AMBIGUOUS rows. Search auto-clear stays 0."
    )


def briefing_text(exposure: Mapping[str, Any], dupes: Mapping[str, Any]) -> str:
    rows = list(exposure.get("rows") or [])[:5]
    lines = [
        "CLOSE BRIEFING",
        f"Human-queue exposure rows { _s(exposure.get('n')) }. Rank is |amount| × (age+1), not a match score.",
    ]
    for row in rows:
        lines.append(
            f"- {_s(row.get('id'))} · {_s(row.get('amount_display'))} · age {_s(row.get('age_days'))}d"
        )
    if not rows:
        lines.append("- (empty human queue)")
    lines.append(f"Duplicate UTR groups {_s(dupes.get('n'))}. Overlay does not write CLEARED.")
    return "\n".join(lines)


def not_found_text(transaction_id: str) -> str:
    cid = transaction_id.strip() or "that id"
    return f"I couldn't find transaction {cid}."


def insufficient_text() -> str:
    return "The available records do not provide enough evidence to answer that conclusively."


def exception_text(blob: Mapping[str, Any], question: str) -> str:
    q = question.casefold()
    biggest = blob.get("biggest_unresolved") if isinstance(blob.get("biggest_unresolved"), list) else []
    accounts = blob.get("by_account") if isinstance(blob.get("by_account"), list) else []
    if "biggest" in q and biggest:
        row = biggest[0]
        return (
            f"Biggest unresolved transaction is {_s(row.get('transaction_id'))} at "
            f"{_s(row.get('bank_amount_display'))} (uniqueness {_s(row.get('uniqueness'))}). "
            "Not auto-cleared. Overlay does not write CLEARED."
        )
    if "account" in q and accounts:
        row = accounts[0]
        return (
            f"Account {_s(row.get('account_id'))} has the most exception rows ({_s(row.get('n'))}). "
            "Counts come from the posted ledger, not a guess. Overlay does not write CLEARED."
        )
    count = _s(blob.get("count") if "count" in blob else blob.get("official_ambiguous"))
    return (
        f"Exception rows: {count}. Official ambiguous {_s(blob.get('official_ambiguous'))}. "
        "AMBIGUOUS is not reconciled. Overlay does not write CLEARED."
    )


def comparison_text(stats: Mapping[str, Any]) -> str:
    return (
        f"Verified residual-zero {_s(stats.get('residual_zero'))} versus "
        f"ambiguous {_s(stats.get('ambiguous'))} on official dev. "
        f"Test: residual-zero {_s((stats.get('test') or {}).get('residual_zero'))} versus "
        f"ambiguous {_s((stats.get('test') or {}).get('ambiguous'))}. "
        "Verified residual-zero is not CLEARED. Overlay does not write CLEARED."
    )


def product_policy_note() -> str:
    return (
        "Deterministic reconciliation engine = financial truth. "
        "AI finance controller = investigation and explanation. "
        "Human review = final decision for ambiguous cases. "
        "Uniqueness threshold 1.000000 is refuse-all. Overlay does not write CLEARED."
    )


def review_assistant_text(evidence: Mapping[str, Any]) -> str:
    recon = evidence.get("reconciliation") if isinstance(evidence.get("reconciliation"), dict) else {}
    cid = _s(recon.get("transaction_id") or evidence.get("transaction_id"))
    uniqueness = _s(recon.get("uniqueness"))
    matched = _s(recon.get("matched_count"))
    solutions = _s(recon.get("solution_count"))
    amount = _s(recon.get("bank_amount_display"))
    return (
        "AI REVIEW ASSISTANT\n"
        f"Transaction: {cid}\n"
        f"Issue: {uniqueness}\n"
        f"AI analysis: {solutions} valid combinations produce {amount}. "
        f"Named members: {matched}. "
        "Evidence distinguishing the alternatives is not stored as a chosen winner — "
        "search uniqueness is AMBIGUOUS. "
        "Recommendation: review settlement/member reference metadata before a human approves. "
        "The AI finance controller must not approve automatically. Overlay does not write CLEARED."
    )


def extract_text(blob: Mapping[str, Any]) -> str:
    if not blob.get("ok"):
        return "No structured reference could be extracted from the narration without guessing."
    fields = []
    for key in ("source", "settlement_id", "settlement_date", "reference", "invoice_id", "member_id", "payment_type"):
        value = blob.get(key)
        if value:
            fields.append(f"{key}={value}")
    joined = ", ".join(fields) if fields else "(none)"
    return (
        f"Candidate extraction (not a reconciliation): {joined}. "
        "This is candidate evidence only. The deterministic engine still has to look it up. "
        "Overlay does not write CLEARED."
    )
