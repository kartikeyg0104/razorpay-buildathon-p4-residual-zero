"""F46: as-of view equals audit-chain replay at 20 sampled seqs."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.bitemporal import as_of_view, load_payloads, replay_prefix, sample_seqs, views_equal
from residual_zero.db import init_db, open_readonly
from residual_zero.features import FeatureFlags
from residual_zero.orchestrator import run_split


@pytest.mark.skipif(not Path("data/dev/rendered/bank.csv").is_file(), reason="data/dev missing")
def test_as_of_equals_replay_at_twenty_seqs(tmp_path: Path):
    db = tmp_path.joinpath("ledger.sqlite")
    flags = FeatureFlags.all_off().model_copy(
        update={"f25_idempotency": True, "f46_bitemporal": True, "f52_trace": False}
    )
    n = run_split("dev", db, limit=24, offline=True, flags=flags)
    assert n >= 20
    conn = open_readonly(db)
    try:
        max_seq = conn.execute("SELECT MAX(seq) FROM audit_entry").fetchone()[0]
        assert max_seq is not None
        seqs = sample_seqs(int(max_seq), 20)
        assert len(seqs) == 20
        payloads = load_payloads(conn)
        for seq in seqs:
            as_of = as_of_view(conn, seq)
            replayed = replay_prefix(payloads, seq)
            assert views_equal(as_of, replayed), seq
    finally:
        conn.close()


def test_sample_seqs_includes_ends():
    seqs = sample_seqs(19, 20)
    assert seqs[0] == 0
    assert seqs[-1] == 19
    assert len(seqs) == 20
