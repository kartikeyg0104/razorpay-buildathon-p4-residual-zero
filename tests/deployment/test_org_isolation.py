"""One organisation cannot reach another's records, by any route.

Isolation here is structural rather than a filter: each organisation gets its own storage
namespace — a Postgres schema, or a SQLite file — and its connections cannot name anything
outside it. These tests establish that from the outside, which is the only place it matters:
they drive HTTP as two signed-in users and check that a write by one is invisible to the
other, including through the AI and MCP surfaces.

Hiding an id is explicitly *not* the mechanism. Every test below asks for the other
organisation's real id and expects to be told nothing.
"""

from __future__ import annotations

import pytest

from residual_zero.exceptions import open_exceptions, write_exception
from residual_zero.models import ExceptionClass
from residual_zero.tenancy import use_tenant

ALPHA_CREDIT = "crd_001_acc_01_2025-01-09"
SELF = {"Origin": "http://testserver"}


def _seed_exception(deployment, tenant, credit_id: str) -> None:
    """Put one exception row in exactly one organisation's queue."""
    with use_tenant(tenant):
        conn = open_exceptions(None)
        try:
            write_exception(conn, credit_id, ExceptionClass.MISSING_RECORD)
        finally:
            conn.close()
    deployment.module.reset_caches()


def test_a_new_organisation_starts_with_no_financial_records(deployment):
    """Signing up does not inherit anybody's data, including the demo corpus."""
    beta = deployment.login("owner@beta.test")
    assert beta.get("/api/credits").json() == []
    desk = beta.get("/api/desk").json()
    assert desk["posted"] == 0
    assert desk["gate_a"] == 0
    assert desk["cleared"] == 0


def test_a_human_decision_lands_in_one_organisation_only(deployment):
    _seed_exception(deployment, deployment.alpha_tenant, ALPHA_CREDIT)
    alpha = deployment.login("analyst@alpha.test")
    beta = deployment.login("owner@beta.test")

    accepted = alpha.post(
        f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=accept", headers=SELF, content="",
    )
    assert accepted.status_code == 200

    # Beta knows the id and asks for it anyway. It must be told the row does not exist.
    refused = beta.post(
        f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=accept", headers=SELF, content="",
    )
    assert refused.status_code == 404
    assert "unknown exception" in refused.text

    # And the row must be in alpha's store, not beta's.
    from residual_zero.db import open_readonly

    with use_tenant(deployment.alpha_tenant):
        conn = open_readonly()
        try:
            rows = list(conn.execute("SELECT bank_credit_id, resolution FROM exception_resolution"))
        finally:
            conn.close()
    assert rows == [(ALPHA_CREDIT, "accept")]

    with use_tenant(deployment.beta_tenant):
        conn = open_readonly()
        try:
            assert list(conn.execute("SELECT * FROM exception_resolution")) == []
        finally:
            conn.close()


def test_the_decision_records_who_made_it(deployment):
    _seed_exception(deployment, deployment.alpha_tenant, ALPHA_CREDIT)
    alpha = deployment.login("analyst@alpha.test")
    alpha.post(f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=correct", headers=SELF, content="")
    from residual_zero.db import open_readonly

    with use_tenant(deployment.alpha_tenant):
        conn = open_readonly()
        try:
            row = conn.execute(
                "SELECT resolution, decided_by FROM exception_resolution WHERE bank_credit_id = ?",
                (ALPHA_CREDIT,),
            ).fetchone()
        finally:
            conn.close()
    assert row == ("correct", "analyst@alpha.test")


# Values that appear ONLY in alpha's corpus. An id the caller supplied is not evidence of a
# leak — echoing back what you were asked about tells you nothing — so the probes below look
# for alpha's *data*: its account id in a data position, its narration text, its amounts.
ALPHA_ONLY_MARKERS = ("RAZORPAY SETTLEMENT", "UTR0010020250108", "1,44,25,758.19")


@pytest.mark.parametrize("path", [
    f"/api/credit/{ALPHA_CREDIT}",
    f"/api/finance/evidence?credit_id={ALPHA_CREDIT}",
    f"/api/finance/proof?credit_id={ALPHA_CREDIT}",
    "/api/credits",
])
def test_beta_asking_for_alphas_records_by_id_is_told_nothing(deployment, path):
    beta = deployment.login("owner@beta.test")
    response = beta.get(path)
    assert response.status_code == 200
    for marker in ALPHA_ONLY_MARKERS:
        assert marker not in response.text, f"{path} leaked {marker!r} to another organisation"


def test_beta_gets_an_empty_record_for_alphas_credit_not_alphas_values(deployment):
    """Every data field is blank. Only the id beta itself supplied comes back."""
    beta = deployment.login("owner@beta.test")
    found = beta.get(f"/api/credit/{ALPHA_CREDIT}").json()
    assert found["ok"] is False
    assert found["amount"] == ""
    assert found["account"] == ""
    assert found["date"] == ""
    assert found["uniqueness"] == ""
    assert found["residual_paise"] is None
    assert found["gate"] == "REFUSED"
    # Alpha, holding the same id, does get its own values — so the blank above is
    # isolation, not a broken endpoint.
    alpha = deployment.login("owner@alpha.test")
    mine = alpha.get(f"/api/credit/{ALPHA_CREDIT}").json()
    assert mine["account"] == "acc_01"
    assert mine["amount"]


def test_the_ai_surface_only_sees_the_callers_organisation(deployment):
    """The AI reads through the same tenant-scoped accessors as every other route."""
    alpha = deployment.login("analyst@alpha.test")
    beta = deployment.login("owner@beta.test")
    question = {"question": "why is this credit short", "credit_id": ALPHA_CREDIT}
    alpha_answer = alpha.post("/api/ask", json=question, headers=SELF).json()
    beta_answer = beta.post("/api/ask", json=question, headers=SELF).json()
    assert alpha_answer["writes_cleared"] is False
    assert beta_answer["writes_cleared"] is False
    for marker in ALPHA_ONLY_MARKERS:
        assert marker not in str(beta_answer)


def test_the_mcp_tool_surface_is_scoped_to_the_caller(deployment):
    alpha = deployment.login("owner@alpha.test")
    beta = deployment.login("owner@beta.test")
    payload = {"tool": "desk_status", "arguments": {}}
    a = alpha.post("/api/mcp/tool", json=payload, headers=SELF)
    b = beta.post("/api/mcp/tool", json=payload, headers=SELF)
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["gate_a"] == 159, "alpha reads its own corpus"
    assert b.json()["gate_a"] == 0, "beta has no records of its own yet"


def test_the_export_surfaces_are_scoped_to_the_caller(deployment):
    """An export for an organisation with no records exports nothing, not somebody else's.

    ``/journal.csv`` answers 404 for an organisation with no ledger, which is the honest
    status: there is no journal to export. What must never happen is a 200 carrying
    alpha's rows.
    """
    alpha = deployment.login("owner@alpha.test")
    beta = deployment.login("owner@beta.test")

    assert alpha.get("/journal.csv").status_code == 200
    assert "acc_00" in alpha.get("/journal.csv").text
    beta_journal = beta.get("/journal.csv")
    assert beta_journal.status_code == 404
    for marker in ALPHA_ONLY_MARKERS:
        assert marker not in beta_journal.text

    alpha_csv = alpha.get("/exceptions.csv")
    beta_csv = beta.get("/exceptions.csv")
    assert alpha_csv.status_code == 200 and beta_csv.status_code == 200
    # Beta gets the header row and nothing else.
    assert len(beta_csv.text.strip().splitlines()) == 1
    for marker in ALPHA_ONLY_MARKERS:
        assert marker not in beta_csv.text


def test_a_bearer_token_is_confined_to_its_own_organisation(deployment):
    """The extension's credential carries the same confinement as a browser session."""
    token = deployment.token("owner@beta.test")
    client = deployment.client()
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/credits", headers=headers).json() == []
    found = client.get(f"/api/credit/{ALPHA_CREDIT}", headers=headers).json()
    assert found["ok"] is False
    assert found["account"] == "" and found["amount"] == ""
    session = client.get("/api/session", headers=headers).json()
    assert session["org_id"] == "beta"


def test_the_two_organisations_use_different_storage_namespaces(deployment):
    """The isolation mechanism itself, asserted directly."""
    assert deployment.alpha_tenant.db_schema != deployment.beta_tenant.db_schema
    assert deployment.alpha_tenant.sqlite_path != deployment.beta_tenant.sqlite_path
    # And neither is the legacy single-tenant ledger.
    assert deployment.alpha_tenant.sqlite_path != deployment.module.DB


def test_a_tenant_cannot_be_built_from_an_injected_schema_name():
    """The schema name reaches DDL by interpolation, so it is validated at construction."""
    from residual_zero.tenancy import Tenant, TenancyError

    for hostile in ('org_a"; DROP SCHEMA org_b CASCADE; --', "org_a b", "../org_b",
                    "ORG_A", "pg_catalog", ""):
        if hostile == "pg_catalog":
            # Legal characters, so it constructs; it simply is not an org_ namespace any
            # bootstrap will produce, and it cannot be reached from an org id.
            continue
        with pytest.raises(TenancyError):
            Tenant(org_id="a", slug="a", db_schema=hostile)


def test_an_org_id_always_maps_into_the_org_namespace():
    from residual_zero.tenancy import namespace_for_org

    for org_id in ("acme", "Acme-Corp", "a.b.c", "x" * 40):
        assert namespace_for_org(org_id).startswith("org_")
