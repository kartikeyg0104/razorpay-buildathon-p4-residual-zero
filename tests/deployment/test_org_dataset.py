"""Repointing an organisation at the committed corpus.

A self-service signup starts on ``sql`` and therefore starts empty. That is the correct
default — one tenant's books are never another tenant's starting point — but it is also
why a freshly deployed desk showed zeros in every panel. Moving the demonstration
organisation onto the file corpus is a supported operation, and it must not become a way
for one organisation to read another's rows.
"""

from __future__ import annotations

import pytest

from residual_zero.identity.store import AuthError, IdentityStore


def _posted_credits(deployment, email: str) -> int:
    """How many credits the desk reports for this organisation.

    ``/api/health``, not ``/api/credits``: the latter lists *exceptions*, which live in the
    organisation's schema and are legitimately empty until something is recorded. A corpus
    organisation with no exceptions yet still has 248 credits to show, and asserting on the
    exception list would have called that zero.
    """
    client = deployment.login(email)
    response = client.get("/api/health")
    assert response.status_code == 200
    return int(response.json()["n_credits"])


def test_an_empty_organisation_shows_records_once_it_reads_the_corpus(deployment):
    """REGRESSION: the deployed desk reported n_credits=0 on every panel."""
    assert _posted_credits(deployment, "owner@beta.test") == 0, "beta must start empty"

    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()

    after = _posted_credits(deployment, "owner@beta.test")
    assert after > 100, f"beta reports {after} credits after being pointed at the corpus"


def test_repointing_is_idempotent(deployment):
    """Safe to run on every deploy: the second run is a no-op, not an error."""
    store = IdentityStore()
    first = store.set_organization_dataset("beta", "files", "data/dev/rendered")
    second = store.set_organization_dataset("beta", "files", "data/dev/rendered")
    assert (first.dataset_kind, first.dataset_root) == (second.dataset_kind, second.dataset_root)


def test_returning_an_organisation_to_its_own_rows_clears_the_corpus_root(deployment):
    store = IdentityStore()
    store.set_organization_dataset("beta", "files", "data/dev/rendered")
    reverted = store.set_organization_dataset("beta", "sql")
    assert reverted.dataset_kind == "sql"
    assert reverted.dataset_root == "", "a sql organisation must not keep a corpus path"
    deployment.module.reset_caches()
    assert _posted_credits(deployment, "owner@beta.test") == 0


def test_an_unknown_organisation_is_refused(deployment):
    with pytest.raises(AuthError):
        IdentityStore().set_organization_dataset("no-such-org", "files", "data/dev/rendered")


def test_an_unknown_dataset_kind_is_refused_before_it_is_stored(deployment):
    store = IdentityStore()
    with pytest.raises(Exception):
        store.set_organization_dataset("beta", "elsewhere")
    assert store.tenant_for_org("beta").dataset_kind == "sql", "a rejected value was stored"


def test_repointing_beta_does_not_give_it_alphas_own_rows(deployment):
    """The corpus is shared and synthetic; another tenant's *schema* stays unreachable."""
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    assert deployment.alpha_tenant.db_schema != deployment.beta_tenant.db_schema
    # Both read the same committed files, so both see the same count — that is the corpus,
    # not alpha's storage. The isolation that matters is asserted in test_org_isolation.py.
    assert _posted_credits(deployment, "owner@beta.test") == _posted_credits(
        deployment, "owner@alpha.test"
    )


def test_the_desk_does_not_claim_an_audit_chain_it_never_verified(deployment):
    """REGRESSION: an organisation with no ledger rendered "audit intact".

    ``chain_ok`` defaulted to True and was only overwritten when there was a database to
    verify, so the one case with nothing to check made the strongest claim on the page.
    "No chain yet" and "chain verified" are different statements, and on a desk that sells
    deterministic proof the difference is the whole product.
    """
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    page = deployment.login("owner@beta.test").get("/")
    assert page.status_code == 200
    assert "audit intact" not in page.text, "claimed a verification that never ran"
    assert "audit not run" in page.text


def test_a_real_chain_is_still_reported_as_intact(deployment):
    """The fix must not silence a genuine verification."""
    from residual_zero.audit import append_entry
    from residual_zero.storage.engine import open_tenant_readwrite
    from residual_zero.tenancy import use_tenant

    with use_tenant(deployment.beta_tenant):
        conn = open_tenant_readwrite("audit")
        try:
            append_entry(conn, {"credit": "bc-1", "disposition": "AMBIGUOUS"}, {"n": 1})
            conn.commit()
        finally:
            conn.close()
    deployment.module.reset_caches()

    page = deployment.login("owner@beta.test").get("/")
    assert page.status_code == 200
    assert "audit intact" in page.text, "a real, verifiable chain was not reported"
    assert "audit not run" not in page.text


# ------------------------------------------------- dashboard provenance semantics
#
# Three provenances land on the dashboard and a bare 0 cannot tell them apart:
# the committed evaluation run, this organisation's posted credits, and this
# organisation's own search/audit run. A deployed organisation has the first two and
# not the third, because the pipeline writes a SQLite ledger and has no PostgreSQL
# output. "search completed 0/0" and "ambiguous 0" claimed a search had run.


def _dashboard(deployment, email: str) -> str:
    page = deployment.login(email).get("/")
    assert page.status_code == 200
    return page.text


def test_an_unrun_search_says_so_instead_of_reporting_zero(deployment):
    """REGRESSION: the deployed desk showed "search completed 0/0"."""
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    page = _dashboard(deployment, "owner@beta.test")

    assert "Not run" in page, "an unrun search must name its state"
    assert "no search recorded for this organisation" in page
    assert "search completed 0/0" not in page
    assert "0/0" not in page, "a 0/0 ratio reads as a completed search over nothing"


def test_uniqueness_and_ambiguity_are_not_reported_as_measured_zeros(deployment):
    """0 ambiguous is a finding. It must not appear when nothing was searched."""
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    page = _dashboard(deployment, "owner@beta.test")

    for label in ("uniqueness needs a recorded search", "ambiguity needs a recorded search"):
        assert label in page, label
    assert "Not evaluated" in page


def test_auto_cleared_is_not_claimed_when_nothing_was_searched(deployment):
    """"0 auto-cleared" is a safety claim, and an unsearched corpus has not earned it."""
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    page = _dashboard(deployment, "owner@beta.test")

    assert "no run to auto-clear from" in page
    assert "guesses refused" not in page, "claimed refused guesses without a search"


def test_the_deterministic_scores_survive_the_change(deployment):
    """The evaluation numbers are real and must keep being shown."""
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    page = _dashboard(deployment, "owner@beta.test")

    assert "159/239" in page, "proven residual-zero was lost"
    assert "148/239" in page, "settlement-linked was lost"
    assert "Deterministic scores" in page, "the provenance legend is missing"


def test_an_organisation_with_records_still_reports_its_overlay_numbers(deployment):
    """`has_records` and `search_recorded` are different states, not one flag.

    A corpus organisation has posted credits and no recorded run: verified/accepted and
    the human review queue are real overlay results and must keep their numbers, while
    only the search-derived cards go quiet.
    """
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    page = _dashboard(deployment, "owner@beta.test")

    assert "settlement reports re-derived successfully" in page
    assert "still unproven" in page, "the human review queue was blanked"
    assert "no posted credits for this organisation" not in page


def test_an_organisation_with_no_records_blanks_the_record_scoped_cards(deployment):
    """beta on `sql` has nothing posted: those cards are unevaluated, not zero."""
    page = _dashboard(deployment, "owner@beta.test")

    assert "no posted credits for this organisation" in page
    assert "no credits posted" in page, "the banner must not imply an empty corpus"
    assert "settlement reports re-derived successfully" not in page


def test_the_close_certificate_does_not_report_a_broken_chain_that_never_existed(deployment):
    """REGRESSION: /close rendered "chain broken" for an organisation with no chain.

    Worse than the dashboard's silent zeros: this one raises an alarm about evidence that
    was never produced. The certificate object itself is unchanged — the artifacts and
    /certificate keep their exact fields — only the sentence the page renders changes.
    """
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    page = deployment.login("owner@beta.test").get("/close")
    assert page.status_code == 200
    assert "chain not run" in page.text
    assert "broken" not in page.text, "alarmed about a chain that was never built"
    assert "not evaluated — no search recorded" in page.text


def test_the_headline_verdict_does_not_claim_auto_clear_held(deployment):
    """REGRESSION: the verdict said "auto-clear stayed at zero — uniqueness not proven".

    That is a result: a search ran, found no unique explanation, and refused to clear. With
    no recorded search it is the strongest safety claim on the page resting on nothing.
    """
    IdentityStore().set_organization_dataset("beta", "files", "data/dev/rendered")
    deployment.module.reset_caches()
    page = deployment.login("owner@beta.test").get("/").text

    assert "auto-clear stayed at zero" not in page
    assert "search not run" in page
    assert "nothing to auto-clear" in page
    # The overlay results beside it are real and must survive.
    assert "settlement reports verified against the rate table" in page
