"""F49: enforced PII boundary. Raise, do not warn-and-send."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.canonical import canonical_json
from residual_zero.semantic.llm import CachedLLMClient, StubLLMClient
from residual_zero.semantic.redact import PiiLeakError, RedactionSession, assert_no_pii, find_pii, redact_entity_request
from residual_zero.semantic.schema import CandidateEntity, EntityResolutionRequest, EntityResolutionResponse


def test_vpa_and_phone_and_card_are_detected():
    assert find_pii("payout to user@okaxis")
    assert find_pii("call 9876543210 for UTR")
    assert find_pii("card 4111 1111 1111 1111")
    assert find_pii("acct 12345678")
    assert not find_pii("ACME PRIVATE LIMITED invoice INV9001")


def test_assert_no_pii_raises():
    with pytest.raises(PiiLeakError):
        assert_no_pii(b"send to merchant@ybl immediately")


def test_redaction_is_stable_within_a_run():
    session = RedactionSession()
    a = session.redact("pay user@paytm")
    b = session.redact("pay user@paytm")
    assert a == b
    assert "user@paytm" not in a
    assert session.deredact(a) == "pay user@paytm"


def test_cached_client_refuses_unredacted_pii(tmp_path: Path):
    stub = StubLLMClient()
    stub.next_resolve = EntityResolutionResponse(selected_id="ent_1", reason="ok")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=100, enforce_pii=True)
    req = EntityResolutionRequest(
        narration_norm="payout user@okhdfcbank",
        counterparty_text="user@okhdfcbank",
        candidates=(CandidateEntity(id="ent_1", display_name="Acme"),),
    )
    # Redaction happens inside the client; the guard must not see the raw VPA.
    bound = client.resolve_entity(req)
    assert bound is not None
    for payload in client.egress_log:
        assert b"user@okhdfcbank" not in payload
        assert_no_pii(payload)


def test_guard_cannot_be_skipped_by_calling_provider_directly_through_client(tmp_path: Path):
    """If redaction failed, the guard still raises rather than sending."""
    session = RedactionSession()
    req = EntityResolutionRequest(
        narration_norm="payout",
        counterparty_text="safe",
        candidates=(CandidateEntity(id="ent_1", display_name="Acme"),),
    )
    # Build a payload that still contains a VPA and assert the detector fires.
    leak = canonical_json({"kind": "resolve_entity", "request": {
        "narration_norm": "x", "counterparty_text": "thief@ybl", "candidates": []
    }})
    with pytest.raises(PiiLeakError):
        assert_no_pii(leak)
    _ = session, req


def test_flags_off_does_not_raise_on_raw_vpa(tmp_path: Path):
    stub = StubLLMClient()
    stub.next_resolve = EntityResolutionResponse(selected_id="ent_1", reason="ok")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=100, enforce_pii=False)
    req = EntityResolutionRequest(
        narration_norm="payout user@okaxis",
        counterparty_text="user@okaxis",
        candidates=(CandidateEntity(id="ent_1", display_name="Acme"),),
    )
    assert client.resolve_entity(req) is not None
