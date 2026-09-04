"""Authorisation: what a signed-in user may do, and the one thing nobody may do.

The permission set is deliberately small — read, review, export, administer — and it does
not contain ``clear``. Authorising ``CLEARED`` is the deterministic engine's decision
(``UNIQUE`` + zero-paise residual + ``FULL`` pool + a derived threshold), so it is not
expressible as a role and no grant can produce it. That is the property these tests exist
to keep true as roles get added.
"""

from __future__ import annotations

import pytest

from residual_zero.identity.store import PERMISSIONS, Role

SELF = {"Origin": "http://testserver"}
ALPHA_CREDIT = "crd_001_acc_01_2025-01-09"


def test_no_role_can_clear():
    """The permission does not exist, so it cannot be granted by accident."""
    for role in Role:
        assert not role.can("clear")
        assert not role.can("write_cleared")
        assert not role.can("authorize_clear")
    every_permission = set().union(*PERMISSIONS.values())
    assert "clear" not in every_permission
    assert not any("clear" in p for p in every_permission)


def test_the_permission_set_is_closed_and_ordered():
    assert set(PERMISSIONS) == set(Role)
    # Each role is a superset of the one below it, so "more senior" never means "loses a
    # capability" — a mistake that is easy to make and hard to notice.
    assert PERMISSIONS[Role.VIEWER] < PERMISSIONS[Role.ANALYST] < PERMISSIONS[Role.OWNER]
    assert Role.VIEWER.rank() < Role.ANALYST.rank() < Role.OWNER.rank()


@pytest.mark.parametrize("route", [
    f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=accept",
    f"/exceptions/{ALPHA_CREDIT}/work?status=open",
])
def test_a_viewer_cannot_record_a_human_decision(deployment, route):
    viewer = deployment.login("viewer@alpha.test")
    response = viewer.post(route, headers=SELF, content="")
    assert response.status_code == 403
    assert "may not review exception" in response.text


@pytest.mark.parametrize("path", [
    "/journal.csv", "/journal.tally", "/exceptions.csv", "/close.zip", "/close.md",
    "/standup.md", "/extension.zip",
])
def test_a_viewer_cannot_export(deployment, path):
    viewer = deployment.login("viewer@alpha.test")
    assert viewer.get(path).status_code == 403


@pytest.mark.parametrize("path", ["/journal.csv", "/exceptions.csv", "/close.zip"])
def test_an_analyst_can_export(deployment, path):
    analyst = deployment.login("analyst@alpha.test")
    assert analyst.get(path).status_code == 200


def test_a_viewer_can_still_read_and_ask(deployment):
    """Read-only is a usable role, not a locked door."""
    viewer = deployment.login("viewer@alpha.test")
    assert viewer.get("/api/desk").status_code == 200
    assert viewer.get(f"/api/credit/{ALPHA_CREDIT}").status_code == 200
    asked = viewer.post(
        "/api/ask", json={"question": "why is this short", "credit_id": ALPHA_CREDIT},
        headers=SELF,
    )
    assert asked.status_code == 200
    assert asked.json()["writes_cleared"] is False


def test_the_admin_surface_needs_the_administer_permission(deployment):
    for email, expected in (
        ("viewer@alpha.test", 403),
        ("analyst@alpha.test", 403),
        ("owner@alpha.test", 404),  # authorised; the route itself does not exist yet
    ):
        client = deployment.login(email)
        assert client.get("/api/config").status_code == expected


def test_an_analyst_records_a_decision_and_it_is_still_not_a_clear(deployment):
    from residual_zero.exceptions import open_exceptions, write_exception
    from residual_zero.models import ExceptionClass
    from residual_zero.tenancy import use_tenant

    with use_tenant(deployment.alpha_tenant):
        conn = open_exceptions(None)
        try:
            write_exception(conn, ALPHA_CREDIT, ExceptionClass.AMBIGUOUS_DECOMPOSITION)
        finally:
            conn.close()
    deployment.module.reset_caches()

    analyst = deployment.login("analyst@alpha.test")
    ok = analyst.post(f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=accept",
                      headers=SELF, content="")
    assert ok.status_code == 200

    # 'cleared' is not in the resolution vocabulary, for any role.
    for email in ("analyst@alpha.test", "owner@alpha.test"):
        client = deployment.login(email)
        refused = client.post(f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=cleared",
                              headers=SELF, content="")
        assert refused.status_code == 400
        assert "does not write CLEARED" in refused.text

    # And no reconciliation row was created by any of it.
    from residual_zero.db import open_readonly

    with use_tenant(deployment.alpha_tenant):
        conn = open_readonly()
        try:
            rows = list(conn.execute(
                "SELECT COUNT(*) FROM reconciliation WHERE disposition = 'CLEARED'"
            ))
        finally:
            conn.close()
    assert rows[0][0] == 0


def test_a_bearer_token_carries_its_owners_role_and_no_more(deployment):
    """The extension's credential is the user's own permissions, not a broader grant."""
    viewer_token = deployment.token("viewer@alpha.test")
    client = deployment.client()
    headers = {"Authorization": f"Bearer {viewer_token}"}
    assert client.get("/api/desk", headers=headers).status_code == 200
    assert client.get("/journal.csv", headers=headers).status_code == 403
    assert client.post(
        f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=accept", headers=headers, content="",
    ).status_code == 403
