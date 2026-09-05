"""Browser extension: Manifest V3, localhost desk, no write path."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from residual_zero.console.app import app
from residual_zero.console.ext_api import DEMO_CREDIT

EXT = Path("extension")


def _route(path: str, method: str = "GET"):
    for route in app.routes:
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(path)


def test_manifest_is_mv3_and_narrow():
    manifest = json.loads(EXT.joinpath("manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    hosts = set(manifest["host_permissions"])
    assert hosts == {
        # This extension's own hosted desk, granted at install because it is the default.
        # One named host; `<all_urls>` is still forbidden below.
        "https://residual-zero-production.up.railway.app/*",
        "http://127.0.0.1:8765/*",
        "http://localhost:8765/*",
        "https://dashboard.razorpay.com/*",
    }
    forbidden = {"cookies", "webRequest", "webRequestBlocking", "debugger", "history", "clipboardRead"}
    assert not (forbidden & set(manifest["permissions"]))
    assert "<all_urls>" not in json.dumps(manifest)


def test_extension_js_has_no_eval_or_remote_script():
    blob = "\n".join(p.read_text(encoding="utf-8") for p in EXT.glob("*.js"))
    assert "eval(" not in blob
    assert "http://" not in blob.replace("http://127.0.0.1:8765", "").replace("http://localhost:8765", "")
    html = EXT.joinpath("popup.html").read_text(encoding="utf-8")
    assert "cdn" not in html.casefold()
    assert "<script src=\"http" not in html


def test_icons_exist():
    for name in ("16.png", "48.png", "128.png"):
        path = EXT.joinpath("icons", name)
        assert path.is_file()
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_api_desk_is_overlay_not_cleared():
    body = json.loads(_route("/api/desk").endpoint().body)
    assert body["ok"] is True
    assert body["cleared"] == 0
    assert body["writes_cleared"] is False
    assert body["demo_credit"] == DEMO_CREDIT
    assert "does not write CLEARED" in body["honesty"]
    assert body["gate_a"] >= body["journalable"]


def test_api_credit_demo_and_missing():
    demo = json.loads(_route("/api/credit/{credit_id}").endpoint(DEMO_CREDIT).body)
    assert demo["ok"] is True
    assert demo["id"] == DEMO_CREDIT
    assert demo["writes_cleared"] is False
    missing = json.loads(_route("/api/credit/{credit_id}").endpoint("crd_missing").body)
    assert missing["ok"] is False


def test_api_lookup_finds_demo():
    body = json.loads(_route("/api/lookup").endpoint(q=DEMO_CREDIT).body)
    assert body["ok"] is True
    assert body["rows"][0]["id"] == DEMO_CREDIT
    prefix = json.loads(_route("/api/lookup").endpoint(q="crd_001_acc_01").body)
    assert any(row["id"] == DEMO_CREDIT for row in prefix["rows"])
    from residual_zero.console.app import _split

    split = _split()
    assert split is not None
    utr = split[4][DEMO_CREDIT].utr or ""
    assert utr
    by_utr = json.loads(_route("/api/lookup").endpoint(q=utr).body)
    assert any(row["id"] == DEMO_CREDIT for row in by_utr["rows"])


def test_finance_evidence_accepts_transaction_id():
    ev = json.loads(_route("/api/finance/evidence").endpoint(transaction_id=DEMO_CREDIT).body)
    assert ev["found"] is True
    assert ev["writes_cleared"] is False
    assert ev["transaction_id"] == DEMO_CREDIT
    src = Path("src/residual_zero/console/ext_api.py").read_text(encoding="utf-8")
    assert 'payload.get("tool")' in src
    assert "transaction_id" in src
    page = _route("/extension").endpoint()
    assert page.status_code == 200
    assert b"download extension" in page.body
    assert b"/extension.zip" in page.body


def test_extension_zip_contains_manifest():
    from residual_zero.console.ext_api import pack_extension_zip

    raw = pack_extension_zip()
    assert raw[:2] == b"PK"
    names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
    assert "residual-zero-extension/manifest.json" in names
    assert "residual-zero-extension/popup.html" in names
    zipped = _route("/extension.zip").endpoint()
    assert zipped.media_type == "application/zip"
    assert b"manifest.json" in zipped.body or zipped.body[:2] == b"PK"


def test_api_recon_parses_sample_and_writes_nothing():
    from residual_zero.console.ext_api import preview_recon

    payload = json.loads(Path("fixtures/recon/combined_sample.json").read_text(encoding="utf-8"))
    body = preview_recon(payload)
    assert body["ok"] is True
    assert body["written"] is False
    assert body["n"] == 3
    assert body["cleared"] == 0
    assert body["ledger_hits"] == 0
    assert _route("/api/recon", "POST") is not None


def test_api_mcp_tools_are_read_only_fixture():
    from residual_zero.ingest.mcp_settlements import SettlementMcp

    tools = json.loads(_route("/api/mcp/tools").endpoint().body)
    assert tools["enabled"] is False
    assert tools["source"] == "fixture"
    assert tools["written"] is False
    assert "fetch_all_instant_settlements" in tools["allowed"]
    assert "desk_status" in tools["allowed"]
    assert "capture_payment" in tools["refused"]
    assert "create_instant_settlement" in tools["refused"]
    assert tools["stdio"] == "python -m residual_zero.mcp"
    assert _route("/mcp", "GET") is not None
    assert _route("/mcp", "POST") is not None
    assert _route("/api/mcp/tool", "POST") is not None
    got = SettlementMcp.from_config().invoke(
        "fetch_settlement_recon_details", {"year": 2025, "month": 1}
    )
    assert got["source"] == "fixture"
    assert got["written"] is False
    assert got["n"] == 3
    assert got["cleared"] == 0
    assert got["ledger_hits"] == 0


def test_extension_setl_chip_routes_into_the_extension_not_the_desk():
    """A settlement chip still resolves settlement ids — natively, since v2.

    This used to assert the chip built a desk URL
    (`/recon?tool=fetch_settlement_with_id&settlement_id=…`) and opened it in a tab. That
    redirect was the behaviour removed in v2: the chip now messages the service worker,
    which opens the extension's own data-sources view. The capability is unchanged; the
    navigation target is not.
    """
    js = EXT.joinpath("content.js").read_text(encoding="utf-8")
    assert "setlod_" in js
    assert "setl_" in js
    assert "open-settlement" in js
    assert "open-credit" in js
    # The old redirect must not come back.
    assert "settlement_id=" not in js
    assert "/recon" not in js
    assert "chrome.tabs.create" not in js

    # The service worker validates the id and opens an extension page.
    bg = EXT.joinpath("background.js").read_text(encoding="utf-8")
    assert "open-settlement" in bg
    assert "SETTLEMENT_RE" in bg
    assert "chrome.runtime.getURL" in bg

    # The read-only MCP tools those ids resolve to are still registered on the desk.
    from residual_zero.ingest.mcp_settlements import ALLOWED_TOOLS

    assert "fetch_settlement_with_id" in ALLOWED_TOOLS
    assert "fetch_instant_settlement_with_id" in ALLOWED_TOOLS


def test_api_credits_still_mounted():
    rows = json.loads(_route("/api/credits").endpoint().body)
    assert isinstance(rows, list)
    assert any(row["id"] == DEMO_CREDIT for row in rows)
