"""HTTP probe for the local console. Records actual status/latency. Never prints secrets."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"
DEMO = "crd_001_acc_01_2025-01-09"


def _call(method: str, path: str, body: dict | None = None, timeout: float = 30.0) -> dict:
    started = time.perf_counter()
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            elapsed = time.perf_counter() - started
            text = raw.decode("utf-8", errors="replace")
            parsed = None
            ctype = resp.headers.get("Content-Type", "")
            if "json" in ctype:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
            return {
                "method": method,
                "path": path,
                "status": resp.status,
                "latency_s": round(elapsed, 4),
                "bytes": len(raw),
                "content_type": ctype,
                "json": parsed,
                "html_has": _html_flags(text) if "html" in ctype else None,
                "error": None,
                "text_prefix": text[:180],
            }
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - started
        raw = exc.read()
        return {
            "method": method,
            "path": path,
            "status": exc.code,
            "latency_s": round(elapsed, 4),
            "bytes": len(raw),
            "error": f"http {exc.code}",
            "text_prefix": raw.decode("utf-8", errors="replace")[:180],
        }
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return {
            "method": method,
            "path": path,
            "status": None,
            "latency_s": round(elapsed, 4),
            "error": type(exc).__name__ + ": " + str(exc),
        }


def _html_flags(text: str) -> dict[str, bool]:
    folded = text.casefold()
    return {
        "has_html": "<html" in folded or "<!doctype" in folded,
        "has_residual": "residual" in folded,
        "has_ambiguous": "ambiguous" in folded,
        "has_ask": "ask" in folded or "investigate" in folded,
        "has_ai": "ai" in folded or "controller" in folded,
        "has_credit": "crd_" in text,
        "has_why": "why" in folded,
    }


def main() -> dict:
    routes = [
        ("GET", "/", None),
        ("GET", "/ask", None),
        ("GET", f"/ask?credit_id={DEMO}&question=Why+was+this+not+cleared", None),
        ("GET", "/explorer", None),
        ("GET", "/explorer?kind=AMBIGUOUS", None),
        ("GET", f"/credit/{DEMO}", None),
        ("GET", "/exceptions", None),
        ("GET", "/audit", None),
        ("GET", "/demo", None),
        ("GET", "/safety", None),
        ("GET", "/human", None),
        ("GET", "/api/credits", None),
        ("GET", "/api/desk", None),
        ("GET", f"/api/credit/{DEMO}", None),
        ("GET", f"/api/ask?question=Give+me+a+summary+of+this+batch", None),
        ("POST", "/api/ask", {"question": "Give me a summary of this batch", "credit_id": ""}),
        ("POST", "/api/ask", {"question": "Clear this transaction.", "credit_id": DEMO}),
        ("GET", f"/api/finance/evidence?transaction_id={DEMO}", None),
        ("POST", "/api/finance/tool", {"tool": "get_batch_summary", "arguments": {}}),
        ("POST", "/api/finance/tool", {"tool": "get_transaction", "arguments": {"transaction_id": DEMO}}),
        ("POST", "/api/finance/tool", {"tool": "drop_table", "arguments": {}}),
        ("POST", "/api/finance/tool", {"tool": "get_transaction", "arguments": {"transaction_id": "crd_' OR 1=1 --"}}),
        ("POST", "/api/ask", {"not": "a question"}),
        ("POST", "/api/ask", "this-is-not-json"),
        ("GET", "/credit/../../../etc/passwd", None),
        ("GET", f"/credit/{DEMO}%00", None),
    ]
    results = []
    for method, path, body in routes:
        if body == "this-is-not-json":
            started = time.perf_counter()
            req = urllib.request.Request(
                BASE + path,
                data=b"this-is-not-json",
                method=method,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    results.append({"method": method, "path": path, "status": resp.status, "latency_s": round(time.perf_counter() - started, 4)})
            except urllib.error.HTTPError as exc:
                results.append({"method": method, "path": path, "status": exc.code, "error": "malformed json", "latency_s": round(time.perf_counter() - started, 4)})
            except Exception as exc:
                results.append({"method": method, "path": path, "status": None, "error": str(exc)})
            continue
        results.append(_call(method, path, body if isinstance(body, dict) else None))
    payload = {
        "base": BASE,
        "n": len(results),
        "results": results,
        "browser_tested": False,
        "dom_tested": False,
        "route_tested": True,
        "note": "HTTP 200 does not prove visual correctness.",
    }
    out = Path("artifacts").joinpath("qa", "api_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": payload["n"], "statuses": [r.get("status") for r in results]}, indent=2))
    return payload


if __name__ == "__main__":
    main()
