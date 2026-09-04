"""PostgreSQL connection presenting the same narrow surface as ``sqlite3.Connection``.

Why a shim rather than an ORM: the reconciliation engine already computes financial truth
in Python and hands storage a finished row. An ORM would buy nothing and would put a
translation layer between the verifier and what gets persisted. The surface the application
actually uses is six methods wide, so it is cheaper and far safer to implement exactly
those six than to restate 60 queries in a new dialect.

Isolation is structural, not a ``WHERE`` clause. Every organisation gets its own Postgres
schema and a connection whose ``search_path`` names only that schema. A query that forgot
an ``org_id`` filter therefore cannot reach another organisation's rows — it resolves
against the caller's own schema or fails to resolve at all. See
:mod:`residual_zero.tenancy`.
"""

from __future__ import annotations

from typing import Any, Iterator, Sequence

from residual_zero.storage.dialect import split_script, translate


class PostgresUnavailable(RuntimeError):
    """psycopg is not installed. Raised only when a Postgres URL is actually configured."""


def _psycopg():
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by test_production_config
        raise PostgresUnavailable(
            "RZ_DATABASE_URL names PostgreSQL but psycopg is not installed; "
            'install it with:  pip install "residual-zero[postgres]"'
        ) from exc
    return psycopg


class ReadOnlyViolation(RuntimeError):
    """A write was attempted on a read-only connection."""


class PgCursor:
    """Iterable result handle. Mirrors what ``sqlite3.Connection.execute`` returns."""

    __slots__ = ("_cur",)

    def __init__(self, cur: Any) -> None:
        self._cur = cur

    def __iter__(self) -> Iterator[tuple]:
        return iter(self._cur)

    def fetchone(self) -> tuple | None:
        return self._cur.fetchone()

    def fetchall(self) -> list[tuple]:
        return self._cur.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


class PgConnection:
    """``sqlite3.Connection``-shaped wrapper over psycopg.

    Read-only connections set ``default_transaction_read_only``, so the *server* rejects a
    write. That is the same discipline as the SQLite path's ``mode=ro`` URI: the refusal
    lives below the application, where a coding mistake cannot talk it out of the decision.
    """

    def __init__(
        self,
        dsn: str,
        *,
        schema: str,
        readonly: bool = False,
        create_schema: bool = False,
        application_name: str = "residual-zero",
    ) -> None:
        psycopg = _psycopg()
        self._readonly = readonly
        self._schema = schema
        self._raw = psycopg.connect(dsn, autocommit=False, application_name=application_name)
        try:
            if create_schema and not readonly:
                with self._raw.cursor() as cur:
                    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                self._raw.commit()
            with self._raw.cursor() as cur:
                # search_path names this tenant's schema only. No `public` fallback: a
                # missing table must be an error, never a silent read of a shared one.
                cur.execute(f'SET search_path TO "{schema}"')
                if readonly:
                    cur.execute("SET default_transaction_read_only = on")
            self._raw.commit()
        except BaseException:
            self._raw.close()
            raise

    # ------------------------------------------------------------------ DB-API surface

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> PgCursor:
        translated = translate(sql, has_params=bool(params))
        cur = self._raw.cursor()
        if translated is None:
            # PRAGMA and friends. Return an empty result rather than raising, matching what
            # the SQLite path does with a statement that has no rows.
            cur.execute("SELECT 1 WHERE false")
            return PgCursor(cur)
        cur.execute(translated, tuple(params) if params else None)
        return PgCursor(cur)

    def executemany(self, sql: str, rows) -> None:
        """One statement, many parameter tuples.

        Ingest writes thousands of rows. Issuing them one at a time costs a network
        round-trip each, which turned a 10,000-row corpus migration into a twenty-minute
        job against a hosted database. psycopg's executemany pipelines them.
        """
        batch = [tuple(row) for row in rows]
        if not batch:
            return
        translated = translate(sql, has_params=True)
        if translated is None:  # pragma: no cover - PRAGMA has no parameters
            return
        with self._raw.cursor() as cur:
            cur.executemany(translated, batch)

    def executescript(self, script: str) -> None:
        for statement in split_script(script):
            translated = translate(statement, has_params=False)
            if translated is None:
                continue
            with self._raw.cursor() as cur:
                cur.execute(translated)
        self._raw.commit()

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        try:
            if not self._readonly:
                self._raw.commit()
        finally:
            self._raw.close()

    # ------------------------------------------------------------------ concurrency

    def lock_for_append(self, name: str) -> None:
        """Serialise a read-modify-write against concurrent writers.

        The audit chain computes ``seq = MAX(seq) + 1`` and hashes the previous entry's
        hash. Two writers interleaving that read-modify-write would either collide on the
        primary key or fork the chain, so the whole sequence takes a transaction-scoped
        advisory lock first. It releases on COMMIT or ROLLBACK, so a crashed writer cannot
        wedge the log.
        """
        with self._raw.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (name,))

    @property
    def schema(self) -> str:
        return self._schema

    @property
    def readonly(self) -> bool:
        return self._readonly


def schema_exists(dsn: str, schema: str) -> bool:
    psycopg = _psycopg()
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema,)
            )
            return cur.fetchone() is not None


def list_schemas(dsn: str, prefix: str) -> list[str]:
    psycopg = _psycopg()
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name LIKE %s ORDER BY schema_name",
                (prefix + "%",),
            )
            return [r[0] for r in cur.fetchall()]
