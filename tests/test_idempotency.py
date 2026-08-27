"""F25: replay is a no-op; crash-resume does not double-count."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.audit import verify_chain
from residual_zero.db import open_readonly
from residual_zero.features import FeatureFlags
from residual_zero.orchestrator import CrashSimulated, run_split


def _flags() -> FeatureFlags:
    return FeatureFlags.all_off().model_copy(update={"f25_idempotency": True, "f52_trace": False, "f31_disambiguation": False, "f40_journal": False, "f37_clustering": False, "f38_drift": False, "f49_pii": False})


@pytest.mark.skipif(not Path("data/dev/rendered/bank.csv").is_file(), reason="data/dev missing")
def test_replay_does_not_duplicate_audit(tmp_path: Path):
    db = tmp_path / "l.sqlite"
    flags = _flags()
    n1 = run_split("dev", db, limit=3, offline=True, flags=flags)
    conn = open_readonly(db)
    try:
        n_audit_1 = conn.execute("SELECT COUNT(*) FROM audit_entry").fetchone()[0]
        ok1, _, _ = verify_chain(conn)
    finally:
        conn.close()
    n2 = run_split("dev", db, limit=3, offline=True, flags=flags)
    conn = open_readonly(db)
    try:
        n_audit_2 = conn.execute("SELECT COUNT(*) FROM audit_entry").fetchone()[0]
        ok2, _, _ = verify_chain(conn)
    finally:
        conn.close()
    assert n1 == 3
    assert n2 == 0
    assert n_audit_1 == n_audit_2 == 3
    assert ok1 and ok2


@pytest.mark.skipif(not Path("data/dev/rendered/bank.csv").is_file(), reason="data/dev missing")
def test_crash_resume_does_not_break_the_chain(tmp_path: Path):
    db = tmp_path / "l.sqlite"
    flags = _flags()
    with pytest.raises(CrashSimulated):
        run_split("dev", db, limit=5, offline=True, flags=flags, halt_after=2)
    n = run_split("dev", db, limit=5, offline=True, flags=flags)
    conn = open_readonly(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM audit_entry").fetchone()[0]
        ok, broken, _ = verify_chain(conn)
    finally:
        conn.close()
    assert ok and broken is None
    assert count == 5
    assert n == 3  # two already present in the 5-credit batch, three new
