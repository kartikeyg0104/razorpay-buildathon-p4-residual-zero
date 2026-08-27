"""Q&A: slot substitution, amount rejection, citations, readonly."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.db import init_db, open_readonly
from residual_zero.qa.compose import compose
from residual_zero.qa.format import deterministic_answer, render_slots
from residual_zero.qa.retrieve import Intent, retrieve
from residual_zero.semantic.llm import StubLLMClient
from residual_zero.semantic.schema import NarrationResponse
from residual_zero.verify import open_verify


def test_every_figure_is_slot_substituted(tmp_path: Path):
    db = tmp_path.joinpath("l.sqlite")
    init_db(db)
    v = open_verify(db)
    try:
        v.execute(
            "INSERT INTO reconciliation (bank_credit_id, claimed_total_paise, residual_paise, uniqueness, pool_scope, disposition) "
            "VALUES ('crd_x', 10000, 0, 'UNIQUE', 'FULL', 'CLEARED')"
        )
        v.commit()
    finally:
        v.close()
    conn = open_readonly(db)
    try:
        rows = retrieve(Intent.CREDIT_DETAIL, {"credit_id": "crd_x"}, conn)
        slots = render_slots(rows)
        answer = deterministic_answer(rows, slots)
        assert "100.00" in answer or slots["TOTAL"] in answer
        assert slots["TOTAL"] in answer
    finally:
        conn.close()


def test_model_prose_with_a_literal_is_rejected():
    from residual_zero.qa.retrieve import RetrievedRows
    stub = StubLLMClient()
    stub.next_narrate = NarrationResponse(prose="The residual is Rs. 12.50")
    rows = RetrievedRows(intent=Intent.UNRECOGNISED, rows=(), citations=())
    out = compose("why?", rows, ("RESIDUAL",), stub)
    assert "12.50" not in out


def test_answers_carry_citations(tmp_path: Path):
    db = tmp_path.joinpath("l.sqlite")
    init_db(db)
    v = open_verify(db)
    try:
        v.execute(
            "INSERT INTO reconciliation (bank_credit_id, claimed_total_paise, residual_paise, uniqueness, pool_scope, disposition) "
            "VALUES ('crd_x', 10000, 0, 'UNIQUE', 'FULL', 'CLEARED')"
        )
        v.commit()
    finally:
        v.close()
    conn = open_readonly(db)
    try:
        rows = retrieve(Intent.CREDIT_DETAIL, {"credit_id": "crd_x"}, conn)
        answer = deterministic_answer(rows, render_slots(rows))
        assert "crd_x" in answer
    finally:
        conn.close()


def test_qa_cannot_see_unreconciled_state(tmp_path: Path):
    db = tmp_path.joinpath("l.sqlite")
    init_db(db)
    conn = open_readonly(db)
    try:
        rows = retrieve(Intent.CREDIT_DETAIL, {"credit_id": "crd_absent"}, conn)
        assert rows.rows == ()
    finally:
        conn.close()


def test_qa_connection_is_readonly(tmp_path: Path):
    db = tmp_path.joinpath("l.sqlite")
    init_db(db)
    conn = open_readonly(db)
    try:
        with pytest.raises(Exception):
            conn.execute("INSERT INTO reconciliation (bank_credit_id, claimed_total_paise, residual_paise, uniqueness, pool_scope, disposition) VALUES ('z',1,0,'UNIQUE','FULL','CLEARED')")
            conn.commit()
    finally:
        conn.close()
