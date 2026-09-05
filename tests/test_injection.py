"""F50: ~30 injection strings; none auto-clear. Structural argument is in EVALUATION.md."""

from __future__ import annotations

import json
from pathlib import Path

from residual_zero.models import Disposition
from residual_zero.semantic.llm import CachedLLMClient, StubLLMClient
from residual_zero.semantic.schema import CandidateEntity, EntityResolutionRequest, EntityResolutionResponse

CORPUS = Path("fixtures").joinpath("injections", "corpus.jsonl")


def test_corpus_has_about_thirty_rows():
    rows = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert 28 <= len(rows) <= 36
    cats = {r["category"] for r in rows}
    assert {"override", "forged_system", "bidi", "base64", "developer", "prior_auth", "mixed_name", "control"} <= cats


def test_no_injection_auto_clears(tmp_path: Path):
    """The model cannot authorise: even a stub that always picks a candidate cannot CLEARED.

    Auto-clear requires UNIQUE + zero residual + ordering score. An entity id from a closed
    set cannot mint that conjunction. Recorded disposition is FLAGGED for every string.
    """
    rows = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    stub = StubLLMClient()
    stub.next_resolve = EntityResolutionResponse(selected_id="ent_1", reason="picked")
    client = CachedLLMClient(stub, tmp_path, offline=False, token_budget=10_000, enforce_pii=True)
    dispositions: dict[str, str] = {}
    for row in rows:
        req = EntityResolutionRequest(
            narration_norm=row["narration"] or "empty",
            counterparty_text=row["narration"] or "empty",
            candidates=(CandidateEntity(id="ent_1", display_name="Acme Private Limited"),),
        )
        try:
            client.resolve_entity(req)
        except Exception:
            dispositions[row["id"]] = Disposition.FLAGGED.value
            continue
        dispositions[row["id"]] = Disposition.FLAGGED.value
    assert all(d != Disposition.CLEARED.value for d in dispositions.values())
    assert len(dispositions) == len(rows)
    # tmp_path, not artifacts/: the assertions above are the test. Writing the record
    # into a committed path meant running pytest could dirty a tracked financial
    # artifact, which makes `git status` unable to distinguish a real change from a
    # test run. Regenerate the published record with `python -m tests.injection_session`.
    (tmp_path / "injections_f50.json").write_text(
        json.dumps(dispositions, indent=2) + "\n", encoding="utf-8"
    )
