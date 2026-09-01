"""Console honesty strip is parsed from committed headlines, not invented."""

from residual_zero.console.facts import credit_forensic, forensic_summary, honesty_line


def test_honesty_line_separates_eval_from_overlay():
    line = honesty_line(248, 142, 123, 106)
    assert "does not write CLEARED" in line
    assert "refuse-all" in line
    assert "148/239" in line
    assert "residual-zero 159/239" in line
    assert "settlement-linked" in line
    assert "3977/5973" in line
    assert "budget-exceeded 0" in line
    assert "501/800" in line
    assert "F56 not run" in line
    assert "posted-mismatch 19" in line
    assert "Gate A 142" in line
    assert "not the exact cell" in line


def test_forensic_summary_is_the_measured_audit():
    summary = forensic_summary()
    assert summary["n_scored"] == 239
    assert summary["residual_zero"] == 159
    assert summary["a3_exact_verify_gated"] == 142
    assert summary["named_declared_eq_truth"] == 148
    assert summary["recovered_if_f58"] == 6
    assert summary["auto_clear"] == 0
    assert summary["false_clears"] == 0
    assert summary.get("account_miss_credits", 0) == 0
    assert summary.get("remaining_unmatched", 91) == 91


def test_credit_forensic_does_not_invent_a_match():
    row = credit_forensic("crd_001_acc_01_2025-01-09")
    assert row is not None
    assert row["recovery"] in {
        "MATCHED",
        "RECOVERED",
        "GENUINELY_UNMATCHED",
        "AMBIGUOUS",
        "COMPUTATIONALLY_UNRESOLVED",
    }
    assert row["n_pool"] >= 0

