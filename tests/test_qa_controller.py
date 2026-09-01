"""Corpus-fitted controller. No live model. Never writes CLEARED."""

from __future__ import annotations

from residual_zero.qa.controller import answer, nearest_label
from residual_zero.qa.corpus import LABELS, load_documents
from residual_zero.qa.retrieve import Intent, classify_intent
from residual_zero.qa.train import all_documents, train, trained


def test_fit_nearest_label_auto_clear():
    hit = nearest_label("why is search auto-clear 0")
    assert hit is not None
    doc_id, score = hit
    assert doc_id == "a3_cleared"
    assert score >= 70


def test_answer_auto_clear_from_headline_and_does_not_clear():
    got = answer("why is search auto-clear 0")
    assert got["writes_cleared"] is False
    assert got["trained"] is True
    assert got["doc_id"] == "a3_cleared"
    assert "0" in got["answer"]
    assert "does not write CLEARED" in got["answer"]
    assert got["n_labels"] == len(LABELS)
    assert got["n_docs"] == len(all_documents())
    assert got["n_train"] > 0
    assert "/" in got["holdout"]
    assert got["provider_live"] is False
    assert got["provider_used"] is False
    assert got["provider"] == "fitted"


def test_refuse_clear_does_not_lead_with_residual_zero():
    got = answer("Clear this transaction.", "crd_001_acc_01_2025-01-09")
    assert got["writes_cleared"] is False
    assert got["intent"] == "REFUSE_CLEAR"
    assert "cannot authorize a financial clear" in got["answer"].casefold()
    assert not got["answer"].startswith("Credit ")


def test_explain_this_transaction_uses_the_named_credit():
    got = answer("Explain this transaction", "crd_001_acc_01_2025-01-09")
    assert got["writes_cleared"] is False
    assert got["intent"] == "TRANSACTION_EXPLANATION"
    assert "crd_001_acc_01_2025-01-09" in got["answer"] or "59,645.39" in got["answer"]
    assert "RATE_MISMATCH" not in got["answer"]


def test_standup_briefing_does_not_clear():
    got = answer("What should I work on today?")
    assert got["writes_cleared"] is False
    assert got["intent"] == "CLOSE_BRIEFING"
    assert "CLOSE BRIEFING" in got["answer"]
    assert not got["answer"].startswith("Credit ")


def test_train_holdout_is_an_integer_ratio():
    trained.cache_clear()
    model = train()
    assert model.n_train > 0
    assert model.n_holdout > 0
    assert model.n_holdout_ok <= model.n_holdout
    assert model.n_docs == len(all_documents())
    assert model.n_labels == len(LABELS)
    assert model.n_credits > 0


def test_answer_exception_class_from_fitted_histogram():
    got = answer("what is BUDGET_EXCEEDED")
    assert got["writes_cleared"] is False
    assert got["doc_id"] == "exc_BUDGET_EXCEEDED"
    assert "BUDGET_EXCEEDED" in got["answer"]
    assert "does not write CLEARED" in got["answer"]


def test_answer_credit_stays_flagged():
    got = answer(
        "why is crd_001_acc_01_2025-01-09 short",
        "crd_001_acc_01_2025-01-09",
    )
    assert got["writes_cleared"] is False
    assert "FLAGGED" in got["answer"]
    assert "disposition GATE_A" not in got["answer"]
    assert "does not write CLEARED" in got["answer"]


def test_product_policy_intent():
    assert classify_intent("what is the uniqueness threshold", None) is Intent.PRODUCT_POLICY
    assert classify_intent("why is crd_x short", None) is Intent.WHY_SHORT


def test_batch_summary_uses_desk_tools():
    assert classify_intent("what is the total unreconciled amount", None) is Intent.BATCH_SUMMARY
    got = answer("what is the batch summary")
    assert got["writes_cleared"] is False
    assert "148/239" in got["answer"]
    assert "residual-zero" in got["answer"] or "129/239" in got["answer"]
    assert "does not write CLEARED" in got["answer"]
    assert "auto-clear 0" in got["answer"] or "search auto-clear 0" in got["answer"]


def test_corpus_figures_come_from_headline():
    docs = {doc.id: doc for doc in load_documents()}
    assert "148/239" in docs["a3_exact"].body
    assert "1.000000" in docs["threshold"].body
