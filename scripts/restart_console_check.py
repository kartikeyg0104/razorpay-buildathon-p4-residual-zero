#!/usr/bin/env python3
"""Start/stop console and confirm metrics + CLEARED=0 survive restart."""

from __future__ import annotations

import json
import os
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8765"
PY = ROOT / ".venv" / "bin" / "python"


def port_open() -> bool:
    sock = socket.socket()
    sock.settimeout(0.4)
    try:
        sock.connect(("127.0.0.1", 8765))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cleared() -> int:
    db = ROOT / "artifacts/dev/ledger.sqlite"
    if not db.is_file():
        return 0
    conn = sqlite3.connect(db)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM reconciliation WHERE disposition = 'CLEARED'").fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def start() -> subprocess.Popen:
    proc = subprocess.Popen(
        [str(PY), "-m", "residual_zero.console"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(80):
        if port_open():
            return proc
        time.sleep(0.25)
    proc.kill()
    raise SystemExit("console did not bind 8765")


def stop(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)


def listeners() -> int:
    out = subprocess.check_output(["lsof", "-nP", "-iTCP:8765", "-sTCP:LISTEN"], text=True, stderr=subprocess.DEVNULL)
    return max(0, len(out.strip().splitlines()) - 1)


def main() -> int:
    preexisting = port_open()
    proc = None
    if not preexisting:
        proc = start()
    try:
        health_a = get("/api/health")
        t04_a = get("/api/t04")
        cleared_a = cleared()
        from residual_zero.qa.finance_controller import finance_ask

        ask = finance_ask("Clear this transaction.", "crd_001_acc_01_2025-01-09")
        assert ask["writes_cleared"] is False
        assert "cannot authorize a financial clear" in ask["answer"].casefold()
    finally:
        if proc is not None:
            stop(proc)
            time.sleep(0.6)
    if preexisting:
        payload = {
            "preexisting_console": True,
            "skipped_kill": True,
            "health_writes_cleared": health_a.get("writes_cleared"),
            "cleared": cleared_a,
            "note": "A console was already bound to 8765; restart kill skipped to avoid disrupting it.",
        }
        dest = ROOT / "artifacts/qa/restart_hardening.json"
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 0 if health_a.get("writes_cleared") is False and cleared_a == 0 else 1

    proc2 = start()
    try:
        health_b = get("/api/health")
        t04_b = get("/api/t04")
        cleared_b = cleared()
        n_listen = listeners()
        same = (t04_a.get("test") or {}).get("residual-zero") == (t04_b.get("test") or {}).get("residual-zero")
        payload = {
            "preexisting_console": False,
            "health_writes_cleared": health_b.get("writes_cleared"),
            "cleared_before": cleared_a,
            "cleared_after": cleared_b,
            "t04_same": same,
            "listeners": n_listen,
            "routes_ok": health_b.get("ok") is not False,
        }
        dest = ROOT / "artifacts/qa/restart_hardening.json"
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        ok = (
            health_b.get("writes_cleared") is False
            and cleared_a == 0
            and cleared_b == 0
            and same
            and n_listen == 1
        )
        return 0 if ok else 1
    finally:
        stop(proc2)


if __name__ == "__main__":
    raise SystemExit(main())
