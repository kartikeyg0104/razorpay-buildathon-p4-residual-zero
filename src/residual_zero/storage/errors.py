"""One exception tuple for "this query could not run against this store".

Several read paths degrade rather than fail when a table is absent — an organisation whose
ingest has not run yet, or an older ledger missing a table a newer feature reads. Those
handlers caught ``sqlite3.OperationalError`` by name, which silently stopped degrading the
moment PostgreSQL became a backend: the equivalent psycopg error is a different class, so
the ``except`` did not match and a missing table became a 500.

:data:`QUERY_ERRORS` is the backend-agnostic tuple to catch instead. It stays narrow on
purpose — a programming error should still surface — and psycopg is imported only if it is
installed, so the SQLite-only install is unaffected.
"""

from __future__ import annotations

import sqlite3


def _psycopg_errors() -> tuple[type[BaseException], ...]:
    try:
        from psycopg import errors as pg_errors
    except ModuleNotFoundError:
        return ()
    return (
        pg_errors.UndefinedTable,
        pg_errors.UndefinedColumn,
        pg_errors.UndefinedFunction,
        pg_errors.InvalidSchemaName,
        pg_errors.InFailedSqlTransaction,
        pg_errors.SyntaxError,
    )


QUERY_ERRORS: tuple[type[BaseException], ...] = (
    sqlite3.OperationalError,
    sqlite3.DatabaseError,
) + _psycopg_errors()


def rollback_quietly(conn) -> None:
    """Clear a failed transaction so the next query on this connection can run.

    PostgreSQL aborts the whole transaction on a failed statement, so a read path that
    swallows one error and issues another query gets ``InFailedSqlTransaction`` for the
    rest of the request. SQLite has no such state and this is a no-op there.
    """
    rollback = getattr(conn, "rollback", None)
    if rollback is None:
        return
    try:
        rollback()
    except Exception:
        pass
