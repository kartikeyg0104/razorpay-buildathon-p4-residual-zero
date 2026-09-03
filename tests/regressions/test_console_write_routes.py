"""Regression: the two console write routes escape their output and validate their input.

`/exceptions/{id}/resolve` and `/exceptions/{id}/work` are the only browser-reachable writes.
They built their response with an f-string into `HTMLResponse`, which bypasses the Jinja
autoescaping the rest of the console relies on, and they persisted a row for any credit id and
any resolution string at all — including ids that name no exception.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3

import pytest

from residual_zero.console import app as console_app
from residual_zero.console.ops_pack import RESOLUTIONS, normalise_resolution

XSS_ID = "<img src=x onerror=alert(1)>"
XSS_VALUE = "<script>alert(2)</script>"


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Point the console at a copy so a write test never touches artifacts/dev."""
    copy = tmp_path.joinpath("ledger.sqlite")
    shutil.copy(console_app.DB, copy)
    monkeypatch.setattr(console_app, "DB", copy)
    return copy


def _known_credit(db) -> str:
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT bank_credit_id FROM exception LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row is not None, "fixture ledger has no exceptions to annotate"
    return row[0]


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


FORM = {"Content-Type": "application/x-www-form-urlencoded"}
SELF = {"Origin": "http://127.0.0.1:8765", **FORM}


def _client(_db=None):
    from fastapi.testclient import TestClient

    return TestClient(console_app.app)


def test_resolve_rejects_an_unknown_credit_and_writes_nothing(isolated_db):
    before = _digest(isolated_db)
    got = _client().post("/exceptions/crd_does_not_exist/resolve?resolution=accept",
                         headers=SELF, content="")
    assert got.status_code == 404
    assert _digest(isolated_db) == before


def test_work_rejects_an_unknown_credit_and_writes_nothing(isolated_db):
    before = _digest(isolated_db)
    got = _client().post("/exceptions/crd_does_not_exist/work?assignee=a&status=open",
                         headers=SELF, content="")
    assert got.status_code == 404
    assert _digest(isolated_db) == before


def test_resolution_is_a_closed_set(isolated_db):
    credit = _known_credit(isolated_db)
    before = _digest(isolated_db)
    got = _client().post(f"/exceptions/{credit}/resolve?resolution=whatever-i-like",
                         headers=SELF, content="")
    assert got.status_code == 400
    assert _digest(isolated_db) == before


def test_resolution_cannot_be_cleared(isolated_db):
    """The overlay does not write CLEARED, and it does not record one either."""
    credit = _known_credit(isolated_db)
    got = _client().post(f"/exceptions/{credit}/resolve?resolution=cleared",
                         headers=SELF, content="")
    assert got.status_code == 400
    assert "does not write CLEARED" in got.text
    with pytest.raises(ValueError):
        normalise_resolution("CLEARED")


def test_hostile_input_is_escaped_not_reflected(isolated_db):
    """User input reaches the body only as escaped text, never as markup.

    The payload's own characters may still appear (``onerror=`` is inert once its angle
    brackets are entities); what must not appear is a tag the browser would parse. So the
    invariant is that every ``<`` and ``>`` in the response belongs to the template's own
    markup, not to the reflected value.
    """
    import urllib.parse as up

    quoted = up.quote(XSS_ID, safe="")
    payload = up.quote(XSS_VALUE, safe="")
    for response in (
        _client().post(f"/exceptions/{quoted}/resolve?resolution={payload}",
                       headers=SELF, content=""),
        _client().post(f"/exceptions/{quoted}/work?assignee={payload}&note={payload}",
                       headers=SELF, content=""),
    ):
        body = response.text
        assert "<script" not in body.lower()
        assert "<img" not in body.lower()
        # The only tags left are the wrapping <p>...</p> the handler itself writes.
        assert body.count("<") == 2 and body.count(">") == 2
        assert "&lt;" in body  # the payload's brackets survived as entities


def test_a_legitimate_resolution_still_persists(isolated_db):
    credit = _known_credit(isolated_db)
    for resolution in sorted(RESOLUTIONS):
        got = _client().post(f"/exceptions/{credit}/resolve?resolution={resolution}",
                             headers=SELF, content="")
        assert got.status_code == 200
        conn = sqlite3.connect(isolated_db)
        try:
            row = conn.execute(
                "SELECT resolution FROM exception_resolution WHERE bank_credit_id = ?",
                (credit,),
            ).fetchone()
        finally:
            conn.close()
        assert row == (resolution,)


# ---------------------------------------------------------------- CSRF / origin

# CORS does not protect a write: it withholds the *response* while the request still
# executes. A form content-type keeps the POST "simple" so no preflight can fail, and both
# resolution fields are query params — so any page the operator visited could silently
# write exception resolutions to the local desk (confirmed 2026-09). Session
# authentication would not have helped: a cookie rides along on exactly this request.
@pytest.mark.parametrize("route", ["resolve?resolution=correct", "work?status=open"])
@pytest.mark.parametrize("origin", [
    "https://evil.example",
    "http://127.0.0.1:9999",
    "https://dashboard.razorpay.com",
    "null",
])
def test_a_foreign_origin_cannot_write(isolated_db, route, origin):
    credit = _known_credit(isolated_db)
    before = _digest(isolated_db)
    got = _client(isolated_db).post(
        f"/exceptions/{credit}/{route}",
        headers={"Origin": origin, **FORM}, content="",
    )
    assert got.status_code == 403, got.text
    assert "may not write" in got.text
    assert _digest(isolated_db) == before, "a cross-site POST changed the ledger"


def test_the_console_itself_can_still_write(isolated_db):
    credit = _known_credit(isolated_db)
    got = _client(isolated_db).post(
        f"/exceptions/{credit}/resolve?resolution=accept",
        headers={"Origin": "http://127.0.0.1:8765", **FORM}, content="",
    )
    assert got.status_code == 200
    conn = sqlite3.connect(isolated_db)
    try:
        row = conn.execute(
            "SELECT resolution FROM exception_resolution WHERE bank_credit_id = ?", (credit,)
        ).fetchone()
    finally:
        conn.close()
    assert row == ("accept",)


def test_a_non_browser_client_is_unaffected(isolated_db):
    """Browsers always send Origin on POST, so no header means curl / the CLI / tests."""
    credit = _known_credit(isolated_db)
    got = _client(isolated_db).post(
        f"/exceptions/{credit}/resolve?resolution=escalate", headers=FORM, content="")
    assert got.status_code == 200


def test_the_origin_allowlist_is_narrow():
    from residual_zero.console.app import WRITE_ORIGINS

    assert WRITE_ORIGINS == {"http://127.0.0.1:8765", "http://localhost:8765"}
    # The extension is read-only; it must not be on the write allowlist.
    assert not any("chrome-extension" in o for o in WRITE_ORIGINS)
