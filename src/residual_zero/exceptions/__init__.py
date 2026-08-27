"""Exception-queue owner of the db privilege map. Classification arrives at CP5."""

from __future__ import annotations

from pathlib import Path

from residual_zero.db import _open_readwrite
from residual_zero.exceptions.classify import Classification, ExceptionSignals, classify
from residual_zero.exceptions.narrate import narrate
from residual_zero.models import ExceptionClass

__all__ = [
    "Classification",
    "ExceptionClass",
    "ExceptionSignals",
    "classify",
    "narrate",
    "open_exceptions",
    "write_exception",
]


def open_exceptions(path: Path):
    return _open_readwrite(path, "exceptions")


def write_exception(conn, bank_credit_id: str, exception_class: ExceptionClass) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO exception (bank_credit_id, exception_class) VALUES (?, ?)",
        (bank_credit_id, exception_class.value),
    )
    conn.commit()
