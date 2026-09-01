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
    "record_resolution",
    "record_work",
    "write_exception",
]


def open_exceptions(path: Path | None = None):
    """Write connection for the exception queue.

    ``None`` means "wherever the current organisation's rows live", which is what the
    console passes in production. An explicit path is the single-tenant CLI and test route.
    """
    return _open_readwrite(path, "exceptions")


def write_exception(conn, bank_credit_id: str, exception_class: ExceptionClass) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO exception (bank_credit_id, exception_class) VALUES (?, ?)",
        (bank_credit_id, exception_class.value),
    )
    conn.commit()


def record_resolution(conn, credit_id: str, resolution: str, actor: str) -> None:
    """Persist one human resolution, attributed to whoever made it.

    ``resolution`` must already have been through :func:`normalise_resolution`, which is a
    closed set that refuses ``cleared`` by name. The production schema refuses the same
    value with a CHECK constraint, so a human note cannot become a financial clear whether
    it arrives through this function, a migration or a hand-written UPDATE.
    """
    conn.execute(
        "INSERT OR REPLACE INTO exception_resolution "
        "(bank_credit_id, resolution, decided_by) VALUES (?, ?, ?)",
        (credit_id, resolution, actor[:200]),
    )
    conn.commit()


def record_work(
    conn, credit_id: str, assignee: str, note: str, status: str, actor: str,
) -> None:
    """Persist one work-queue annotation. Never writes a disposition."""
    conn.execute(
        "INSERT OR REPLACE INTO exception_work "
        "(bank_credit_id, assignee, note, status, updated_by) VALUES (?, ?, ?, ?, ?)",
        (credit_id, assignee, note, status, actor[:200]),
    )
    conn.commit()
