"""The console over its real HTTP layer.

Every other console test calls route endpoint FUNCTIONS directly, because
`starlette.testclient` needs httpx2 and the dev extra did not declare it (found 2026-09).
That left FastAPI's own routing, path and query coercion, method dispatch, status codes and
error handling with no coverage at all — a route could 500 on a real request while the
in-process tests stayed green.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from residual_zero.console import app as console_app
from residual_zero.console.app import app

# GET routes that take no path parameter and must answer a plain request.
SIMPLE_GETS = [
    "/", "/exceptions", "/audit", "/explorer", "/ask", "/books", "/journal", "/journal.csv",
    "/journal.tally", "/close", "/api/close", "/close.md", "/certificate", "/metrics",
    "/exceptions.csv", "/api/health", "/health", "/api/ops", "/standup.md", "/clusters",
    "/whatif", "/controller", "/asof", "/evidence", "/demo", "/mixed", "/challenge",
    "/safety", "/alts", "/human", "/recon", "/api/t04", "/api/credits", "/api/desk",
    "/api/mcp/tools", "/extension",
]

HOSTILE_IDS = [
    "nonexistent",
    "' OR 1=1--",
    "'; DROP TABLE audit_entry;--",
    "../../etc/passwd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "A" * 2000,
    "crd_null",
    "<script>alert(1)</script>",
    "../" * 20 + "etc/passwd",
]


@pytest.fixture(scope="module")
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", SIMPLE_GETS)
def test_every_get_route_answers(path, client):
    response = client.get(path)
    assert response.status_code == 200, f"{path} -> {response.status_code}"
    assert response.content, f"{path} returned an empty body"
    assert b"Traceback" not in response.content


@pytest.mark.parametrize("path", SIMPLE_GETS)
def test_no_route_leaks_a_key(path, client):
    body = client.get(path).content.decode("utf-8", "replace")
    # Real key shapes only. A bare "sk-" matches "ask-form" and every other hyphenated word.
    leaks = re.findall(r"\bgsk_[A-Za-z0-9]{8,}|\bnvapi-[A-Za-z0-9_-]{8,}|\bsk-[A-Za-z0-9]{16,}", body)
    assert not leaks, f"{path} leaked a key-shaped token"
    assert "Authorization: Bearer" not in body


@pytest.mark.parametrize("bad", HOSTILE_IDS)
def test_hostile_credit_ids_never_500(bad, client):
    for template in ("/credit/{}", "/api/credit/{}", "/proof/{}"):
        response = client.get(template.format(bad))
        assert response.status_code < 500, f"{template.format(bad[:30])} -> {response.status_code}"
        assert b"Traceback" not in response.content


@pytest.mark.parametrize("bad", HOSTILE_IDS)
def test_hostile_query_params_never_500(bad, client):
    for path in ("/api/lookup", "/ask", "/api/ask"):
        response = client.get(path, params={"q": bad, "question": bad, "credit_id": bad})
        assert response.status_code < 500, f"{path} q={bad[:30]} -> {response.status_code}"


def test_no_route_reads_a_file_outside_the_repo(client):
    """Path traversal must not surface /etc/passwd content through any download route."""
    for path in ("/credit/../../../etc/passwd", "/proof/..%2f..%2f..%2fetc%2fpasswd"):
        body = client.get(path).content
        assert b"root:x:" not in body
        assert b"/bin/bash" not in body


def test_downloads_are_real_files(client):
    csv = client.get("/journal.csv")
    assert csv.status_code == 200
    assert csv.content.count(b"\n") > 1, "journal.csv has no rows"

    zipped = client.get("/close.zip")
    assert zipped.status_code == 200
    assert zipped.content[:2] == b"PK", "close.zip is not a zip"

    ext = client.get("/extension.zip")
    assert ext.status_code == 200
    assert ext.content[:2] == b"PK", "extension.zip is not a zip"


def test_method_dispatch_is_enforced(client):
    assert client.get("/exceptions/crd_x/resolve").status_code == 405
    assert client.get("/exceptions/crd_x/work").status_code == 405
    assert client.post("/audit").status_code == 405


class TestWritesOverHttp:
    """The two browser-reachable writes, driven the way a browser drives them."""

    @pytest.fixture()
    def isolated(self, tmp_path, monkeypatch):
        copy = tmp_path.joinpath("ledger.sqlite")
        shutil.copy(console_app.DB, copy)
        monkeypatch.setattr(console_app, "DB", copy)
        return copy

    @staticmethod
    def _digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_unknown_credit_is_404_and_writes_nothing(self, client, isolated):
        before = self._digest(isolated)
        got = client.post("/exceptions/crd_not_real/resolve", params={"resolution": "accept"})
        assert got.status_code == 404
        assert self._digest(isolated) == before

    def test_invalid_resolution_is_400(self, client, isolated):
        got = client.post("/exceptions/crd_not_real/resolve", params={"resolution": "banana"})
        assert got.status_code == 400

    def test_cleared_is_refused_over_http(self, client, isolated):
        got = client.post("/exceptions/crd_not_real/resolve", params={"resolution": "cleared"})
        assert got.status_code == 400
        assert b"does not write CLEARED" in got.content

    def test_reflected_markup_is_escaped_over_http(self, client, isolated):
        got = client.post(
            "/exceptions/<script>alert(1)</script>/resolve", params={"resolution": "accept"}
        )
        assert b"<script>" not in got.content

    def test_no_get_request_can_write(self, client, isolated):
        """A read-only verb must never mutate the ledger, whatever it is pointed at."""
        before = self._digest(isolated)
        for path in SIMPLE_GETS:
            client.get(path)
        for bad in HOSTILE_IDS[:4]:
            client.get(f"/credit/{bad}")
        assert self._digest(isolated) == before, "a GET mutated the ledger"
