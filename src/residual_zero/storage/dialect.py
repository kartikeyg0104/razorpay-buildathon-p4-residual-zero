"""Translate the application's SQLite-flavoured SQL into PostgreSQL.

The application writes one dialect. Rather than rewrite ~60 call sites — and risk changing
a financial query while doing it — this module translates the four constructs the codebase
actually uses:

=========================================  ===============================================
SQLite                                     PostgreSQL
=========================================  ===============================================
``?`` placeholder                          ``%s``
``INSERT OR REPLACE INTO t ...``           ``INSERT INTO t ... ON CONFLICT (pk) DO UPDATE``
``INSERT OR IGNORE INTO t ...``            ``INSERT INTO t ... ON CONFLICT DO NOTHING``
``PRAGMA ...``                             no-op
``json_extract(col, '$.key')``             ``(col::jsonb ->> 'key')``
=========================================  ===============================================

Translation is textual but quote-aware: a ``?`` or a keyword inside a string literal is
left alone. Everything it cannot recognise passes through unchanged, so an unsupported
construct fails loudly in Postgres rather than being silently rewritten into something
that means something else.

There is no arithmetic here, and there is none in any statement it translates. Financial
truth is computed in Python before a statement is built (:mod:`residual_zero.verify`).
"""

from __future__ import annotations

import re

# Primary keys of the tables ``INSERT OR REPLACE`` targets. Needed because Postgres wants an
# explicit conflict target. A table missing from this map cannot be upserted, which is the
# safe failure: better a loud KeyError at the call site than an ON CONFLICT clause guessing
# at which columns identify a financial row.
PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "reconciliation": ("bank_credit_id",),
    "decomposition_member": ("bank_credit_id", "item_id"),
    "audit_entry": ("seq",),
    "exception": ("bank_credit_id",),
    "exception_resolution": ("bank_credit_id",),
    "exception_work": ("bank_credit_id",),
    "ai_investigation": ("investigation_id",),
    "idempotency_record": ("scope", "idempotency_key"),
    "stream_pool": ("item_id",),
    "webhook_event": ("event_id",),
    "applied_item": ("item_id",),
    "buffer_event": ("event_id",),
    "bank_credit": ("credit_id",),
    "ledger_item": ("item_id",),
    "settlement_line": ("credit_id", "item_id"),
    "organization": ("org_id",),
    "app_user": ("user_id",),
    "user_session": ("session_id",),
    "api_token": ("token_id",),
    "schema_migration": ("version",),
}


class UnsupportedStatement(ValueError):
    """A statement this translator will not rewrite. Raised instead of guessing."""


_INSERT_OR = re.compile(
    r"^\s*INSERT\s+OR\s+(REPLACE|IGNORE|ABORT|FAIL|ROLLBACK)\s+INTO\s+"
    r"[\"']?(?P<table>[A-Za-z_][A-Za-z0-9_]*)[\"']?",
    re.IGNORECASE,
)
_COLUMN_LIST = re.compile(r"\(([^()]*)\)\s*VALUES", re.IGNORECASE)


CODE = "code"
STRING = "string"
COMMENT = "comment"


def scan(sql: str) -> list[tuple[str, str]]:
    """Segment ``sql`` into runs tagged :data:`CODE`, :data:`STRING` or :data:`COMMENT`.

    Every rewrite in this module keys off this one scanner, so a ``?``, a ``%`` or a ``;``
    is only ever treated as syntax when it is actually syntax. A semicolon inside a ``--``
    comment used to end a statement here, which truncated a migration mid-CHECK-constraint
    (found while first applying the schema to PostgreSQL).

    Handles single-quoted strings (with SQL's doubled-quote escape, which falls out
    naturally), double-quoted identifiers, ``--`` line comments and ``/* */`` block
    comments. Dollar-quoting is not handled because no migration or query uses it.
    """
    runs: list[tuple[str, str]] = []
    buf: list[str] = []
    mode = CODE
    i = 0
    n = len(sql)

    def flush(next_mode: str) -> None:
        nonlocal buf, mode
        if buf:
            runs.append(("".join(buf), mode))
        buf = []
        mode = next_mode

    while i < n:
        ch = sql[i]
        if mode == CODE:
            if ch == "'" or ch == '"':
                flush(STRING)
                quote = ch
                buf.append(ch)
                i += 1
                while i < n:
                    buf.append(sql[i])
                    if sql[i] == quote:
                        i += 1
                        break
                    i += 1
                flush(CODE)
                continue
            if sql.startswith("--", i):
                flush(COMMENT)
                end = sql.find("\n", i)
                end = n if end == -1 else end
                buf.append(sql[i:end])
                i = end
                flush(CODE)
                continue
            if sql.startswith("/*", i):
                flush(COMMENT)
                end = sql.find("*/", i + 2)
                end = n if end == -1 else end + 2
                buf.append(sql[i:end])
                i = end
                flush(CODE)
                continue
        buf.append(ch)
        i += 1
    flush(CODE)
    return runs


# json_extract is SQLite's own function. Two audit-trail queries filter on a field inside
# the hashed audit payload with it, and on PostgreSQL that was an UndefinedFunction error
# rather than a rewritten query (found while running the desk against Postgres).
#
# Only a single top-level key is translated. A nested or array path raises rather than being
# approximated: these queries select which audit entries belong to a bank credit, and a
# wrong-but-plausible translation would silently return the wrong set of financial events.
_JSON_EXTRACT = re.compile(
    r"json_extract\s*\(\s*(?P<col>[A-Za-z_][A-Za-z0-9_.\"]*)\s*,\s*"
    r"'\$\.(?P<path>[^']*)'\s*\)",
    re.IGNORECASE,
)
_SIMPLE_JSON_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _json_extract_to_pg(sql: str) -> str:
    def replace(match: re.Match[str]) -> str:
        path = match.group("path")
        if not _SIMPLE_JSON_KEY.match(path):
            raise UnsupportedStatement(
                f"json_extract path '$.{path}' is not a single top-level key; "
                "translate it explicitly rather than approximating it"
            )
        return f"({match.group('col')}::jsonb ->> '{path}')"

    return _JSON_EXTRACT.sub(replace, sql)


def qmark_to_pyformat(sql: str, *, escape_percent: bool = True) -> str:
    """``?`` -> ``%s`` outside string literals.

    ``escape_percent`` doubles any literal ``%`` so psycopg's client-side parameter
    interpolation leaves it alone. It must be False when the statement is executed with no
    parameters, because psycopg only interpolates when parameters are supplied and would
    otherwise leave a literal ``%%`` in the SQL.
    """
    pieces: list[str] = []
    for text, kind in scan(sql):
        chunk = text.replace("%", "%%") if escape_percent else text
        pieces.append(chunk.replace("?", "%s") if kind == CODE else chunk)
    return "".join(pieces)


def _conflict_clause(table: str, columns: list[str], verb: str) -> str:
    if verb.upper() == "IGNORE":
        return " ON CONFLICT DO NOTHING"
    keys = PRIMARY_KEYS.get(table)
    if keys is None:
        raise UnsupportedStatement(
            f"INSERT OR REPLACE INTO {table!r} needs an entry in "
            "residual_zero.storage.dialect.PRIMARY_KEYS naming the columns that identify a row"
        )
    updatable = [c for c in columns if c not in keys]
    target = ", ".join(keys)
    if not updatable:
        # Every column is part of the key: replacing the row would be a no-op.
        return f" ON CONFLICT ({target}) DO NOTHING"
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in updatable)
    return f" ON CONFLICT ({target}) DO UPDATE SET {assignments}"


def translate(sql: str, *, has_params: bool = True) -> str | None:
    """Rewrite one SQLite statement for Postgres. ``None`` means "skip this statement".

    ``None`` is returned for ``PRAGMA``, which has no Postgres equivalent and no effect
    worth emulating: WAL mode and ``query_only`` are replaced by, respectively, Postgres'
    own WAL and a read-only transaction (see :mod:`residual_zero.storage.pg`).

    ``has_params`` says whether the caller will pass parameters, which decides whether a
    literal ``%`` needs doubling for psycopg.
    """
    stripped = sql.strip()
    if not stripped:
        return None
    if re.match(r"^PRAGMA\b", stripped, re.IGNORECASE):
        return None
    match = _INSERT_OR.match(stripped)
    if match:
        verb = match.group(1)
        table = match.group("table")
        if verb.upper() in {"ABORT", "FAIL", "ROLLBACK"}:
            raise UnsupportedStatement(f"INSERT OR {verb.upper()} has no Postgres translation")
        columns_match = _COLUMN_LIST.search(stripped)
        columns = (
            [c.strip().strip('"') for c in columns_match.group(1).split(",")]
            if columns_match
            else []
        )
        head = f"INSERT INTO {table}"
        body = stripped[match.end():]
        stripped = head + body + _conflict_clause(table, columns, verb)
    return qmark_to_pyformat(_json_extract_to_pg(stripped), escape_percent=has_params)


def split_script(script: str) -> list[str]:
    """Split a multi-statement script on semicolons that are actually statement ends.

    Semicolons inside string literals, quoted identifiers and comments do not split.
    """
    statements: list[str] = []
    buf: list[str] = []
    for text, kind in scan(script):
        if kind != CODE:
            buf.append(text)
            continue
        parts = text.split(";")
        for part in parts[:-1]:
            buf.append(part)
            statements.append("".join(buf))
            buf = []
        buf.append(parts[-1])
    tail = "".join(buf)
    if tail.strip():
        statements.append(tail)
    return [s for s in (st.strip() for st in statements) if s]
