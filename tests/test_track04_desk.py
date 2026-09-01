"""Track 04 snapshot from committed artifacts. No invented rates."""

from residual_zero.console.facts import track04_snapshot
from residual_zero.qa.desk_tools import batch_prose, get_batch_summary


def test_track04_snapshot_matches_headline():
    snap = track04_snapshot()
    assert snap.exact == "148/239"
    assert snap.residual_zero == "159/239"
    assert snap.settlement_linked == "148/239"
    assert snap.search_cleared == "0"
    assert snap.scored == "239"
    assert snap.double_claimed == "0"
    assert snap.unreconciled == "1,44,25,758.19"
    assert snap.test_budget == "0"
    assert snap.test_search_completed == "800/800"


def test_desk_tools_do_not_claim_auto_clear():
    row = get_batch_summary()
    assert row["search_cleared"] == "0"
    assert row["writes_cleared"] is False
    assert row["auto_clear_is_not_exact"] is True
    prose = batch_prose()
    assert "148/239" in prose
    assert "residual-zero" in prose
    assert "159/239" in prose
    assert "does not write CLEARED" in prose
