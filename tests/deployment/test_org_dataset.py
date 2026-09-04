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
