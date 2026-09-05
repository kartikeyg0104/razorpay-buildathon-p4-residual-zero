"""One test per production bug this deployment work found. Each names the bug.

These are the defects that only show up once the desk is behind a real domain, on a real
database, serving more than one organisation — which is exactly why they survived a suite
that already had 1300 passing tests.
"""

from __future__ import annotations

import gc
import json
import re
import sqlite3
from pathlib import Path

import pytest

SELF = {"Origin": "http://testserver"}
ALPHA_CREDIT = "crd_001_acc_01_2025-01-09"


# ---------------------------------------------------------------- connection leak


@pytest.mark.parametrize("path", ["/journal.csv", "/journal.tally", "/api/journal"])
def test_the_no_ledger_path_does_not_leak_a_connection(deployment, path):
    """BUG: the connection was opened before the early return, so it was never closed.

    Harmless against a SQLite file. Against PostgreSQL it is one leaked connection per
    request from any organisation with no ledger — a pool exhaustion, and the organisation
    with no ledger is every organisation on its first day.
    """
    beta = deployment.login("owner@beta.test")  # no records of its own
    opened: list[object] = []
    real_open = sqlite3.connect

    def counting_connect(*args, **kwargs):
        conn = real_open(*args, **kwargs)
        opened.append(conn)
        return conn

    import residual_zero.db as db_module

    original = db_module.sqlite3.connect
    db_module.sqlite3.connect = counting_connect
    try:
        for _ in range(3):
            beta.get(path)
    finally:
        db_module.sqlite3.connect = original

    gc.collect()
    still_open = []
    for conn in opened:
        try:
            conn.execute("SELECT 1")
            still_open.append(conn)
        except sqlite3.ProgrammingError:
            pass  # closed, which is what we want
    for conn in still_open:
        conn.close()
    assert not still_open, f"{path} left {len(still_open)} connection(s) open"


def test_the_source_never_acquires_a_connection_before_an_early_return():
    """Static form of the same bug, so a new route cannot reintroduce it.

    An early return is only a leak when there is something to close. Returning because the
    connection itself is ``None`` — the "this organisation has no ledger" case — is fine,
    and so is closing it explicitly on the way out.
    """
    offenders = []
    for rel in ("src/residual_zero/console/extra.py", "src/residual_zero/console/ext_api.py",
                "src/residual_zero/console/app.py"):
        lines = Path(rel).read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(lines):
            if not re.search(r"conn\s*=\s*_db\(\)", line):
                continue
            for j in range(i + 1, min(i + 12, len(lines))):
                nxt = lines[j].strip()
                if nxt.startswith("try:"):
                    break
                if not nxt.startswith("return "):
                    continue
                between = "\n".join(lines[i:j])
                guarded_on_none = re.search(r"if\s+conn\s+is\s+None\s*:", between)
                closed = "conn.close()" in between
                if not (guarded_on_none or closed):
                    offenders.append(f"{rel}:{i + 1} -> early return at {j + 1}")
                break
    assert not offenders, offenders


# ---------------------------------------------------------------- fake HTTP 200


def test_a_malformed_recon_body_answers_400_not_200(deployment):
    """BUG: POST /recon answered 200 with the parse error rendered into the page.

    A 2xx for a request that failed cannot be told apart from one that worked, by a client
    or by a monitor.
    """
    client = deployment.login("owner@alpha.test")
    for body in ("{not json", "[1,2,3]", "", "null"):
        response = client.post("/recon", content=body, headers=SELF)
        assert response.status_code == 400, f"{body!r} answered {response.status_code}"
    ok = client.post("/recon", json={"items": []}, headers=SELF)
    assert ok.status_code == 200


# ---------------------------------------------------------------- duplicated keys


@pytest.mark.parametrize("path", ["/api/health"])
def test_a_json_response_declares_each_field_once(deployment, path):
    """BUG: /api/health's dict literal repeated four keys, so half the values were dead.

    A repeated key is inert — the last one wins — but it reads as two deliberate fields and
    hides which value is actually served.
    """
    client = deployment.login("owner@alpha.test")
    raw = client.get(path).text
    seen: list[str] = []

    def object_pairs_hook(pairs):
        seen.extend(key for key, _value in pairs)
        return dict(pairs)

    json.loads(raw, object_pairs_hook=object_pairs_hook)
    duplicates = {key for key in seen if seen.count(key) > 1}
    assert not duplicates, f"{path} repeats {sorted(duplicates)}"


def test_the_provider_status_card_declares_each_field_once():
    from residual_zero.semantic.provider import desk_ai_status

    source = Path("src/residual_zero/semantic/provider.py").read_text(encoding="utf-8")
    body = source[source.index("def desk_ai_status"):]
    body = body[: body.index("\ndef ")]
    keys = re.findall(r'^\s+"([A-Za-z_]+)":', body, re.M)
    duplicates = {key for key in keys if keys.count(key) > 1}
    assert not duplicates, f"desk_ai_status repeats {sorted(duplicates)}"
    assert isinstance(desk_ai_status(), dict)


# ---------------------------------------------------------------- portable SQL


def test_no_query_uses_a_sqlite_only_construct_untranslated():
    """BUG: json_extract reached PostgreSQL as an UndefinedFunction error.

    A construct only SQLite has must either be translated (see storage.dialect) or not
    used. This test lists the ones the translator knows about and fails on anything else.
    """
    from residual_zero.storage.dialect import translate

    translated = {"json_extract", "PRAGMA", "INSERT OR REPLACE", "INSERT OR IGNORE"}
    untranslatable = ("json_each", "json_group_array", "GLOB ", "julianday(",
                      "last_insert_rowid", "IFNULL(", "group_concat(", " rowid")
    for path in Path("src/residual_zero").rglob("*.py"):
        if path.name == "dialect.py":
            continue
        text = path.read_text(encoding="utf-8")
        for construct in untranslatable:
            assert construct not in text, f"{path} uses {construct!r}, which PostgreSQL lacks"
    # And the translated ones really are translated.
    assert "json_extract" not in (
        translate("SELECT json_extract(payload, '$.bank_credit_id') FROM audit_entry") or ""
    )


def test_the_audit_head_query_is_standard_sql():
    """BUG: `SELECT MAX(seq), entry_hash` relied on a SQLite extension.

    Standard SQL rejects a bare column beside an aggregate. The replacement selects the
    head row explicitly, which is the same row SQLite was returning.
    """
    source = Path("src/residual_zero/audit.py").read_text(encoding="utf-8")
    # Strip comments: the fix's own note quotes the old query to explain what changed.
    code = "\n".join(
        line for line in source.split("\n") if not line.lstrip().startswith("#")
    )
    assert "MAX(seq), entry_hash" not in code
    assert "ORDER BY seq DESC LIMIT 1" in code
    # And the lock is taken before the read-modify-write.
    assert "lock_for_append" in code


def test_a_missing_table_degrades_on_both_backends():
    """BUG: `except sqlite3.OperationalError` stopped matching once Postgres was a backend.

    The handler exists so an organisation whose ingest has not run reads as empty rather
    than as a 500. Catching a SQLite-specific class made that silently backend-dependent.
    """
    from residual_zero.storage.errors import QUERY_ERRORS

    assert sqlite3.OperationalError in QUERY_ERRORS
    for path in Path("src/residual_zero").rglob("*.py"):
        if path.name == "errors.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "except sqlite3.OperationalError" not in text, (
            f"{path} still catches a SQLite-only error class"
        )


# ---------------------------------------------------------------- conflicting clear


def test_a_conflicting_second_clear_is_refused_on_sqlite(tmp_path, monkeypatch):
    """A race or a re-run must not silently replace one explanation with another."""
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)
    from residual_zero.db import init_db
    from residual_zero.verify import ConflictingClearError, open_verify, write_cleared
    from tests.deployment.test_storage_backends import _cleared_decomposition

    db = tmp_path / "ledger.sqlite"
    init_db(db)
    conn = open_verify(db)
    try:
        first = _cleared_decomposition("crd_x", ("itm_a", "itm_b"))
        write_cleared(conn, first)
        write_cleared(conn, first)  # replay is a no-op
        members = [r[0] for r in conn.execute(
            "SELECT item_id FROM decomposition_member WHERE bank_credit_id = 'crd_x' "
            "ORDER BY item_id"
        )]
        assert members == ["itm_a", "itm_b"]
        with pytest.raises(ConflictingClearError):
            write_cleared(conn, _cleared_decomposition("crd_x", ("itm_c", "itm_d")))
        # The original members survive the refusal.
        members = [r[0] for r in conn.execute(
            "SELECT item_id FROM decomposition_member WHERE bank_credit_id = 'crd_x' "
            "ORDER BY item_id"
        )]
        assert members == ["itm_a", "itm_b"]
    finally:
        conn.close()


def test_an_unwritable_evidence_cache_does_not_fail_the_lookup(tmp_path, monkeypatch):
    """REGRESSION: /api/finance/evidence returned 500 in the container.

    The extraction cache defaults to artifacts/console/, which the image ships read-only
    to the service account, so writing it raised PermissionError and a perfectly good
    evidence lookup became an internal error. A cache is an optimisation; failing to
    write one must never fail the read it exists to speed up.

    Same shape as the AI audit log before it, which is why the Dockerfile now has to keep
    every runtime write path under /app/var — asserted in test_render_config.
    """
    from residual_zero.qa import evidence_extract

    unwritable = tmp_path / "readonly"
    unwritable.mkdir()
    unwritable.chmod(0o500)
    monkeypatch.setenv("RZ_EXTRACT_CACHE", str(unwritable / "nested" / "cache.jsonl"))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    try:
        evidence_extract._cache_put("k", [{"field": "utr", "value": "x"}])
    finally:
        unwritable.chmod(0o700)
