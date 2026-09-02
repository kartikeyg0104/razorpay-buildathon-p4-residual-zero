"""Constructed mixed uniqueness desk. Not official Track 04.

Official Dev/Test search UNIQUE is 0. This desk is tiny FULL-pool cases the same
solver already proves in golden tests, so a demo can show UNIQUE, AMBIGUOUS, and
NONE_FOUND side by side. Overlay still does not write CLEARED.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from residual_zero.candidates import CandidatePool
from residual_zero.config import load_solver_config
from residual_zero.console.clear_gate import auto_clear_decision
from residual_zero.models import Kind, PoolScope
from residual_zero.money import format_rupees
from residual_zero.solver import solve_search

DAY = date(2025, 1, 15)
PREFIX = "crd_mix_"


@dataclass(frozen=True)
class MixedSpec:
    credit_id: str
    rupees: tuple[int, ...]
    target_rupees: int
    expect: str
    why: str


SPECS: tuple[MixedSpec, ...] = (
    MixedSpec(
        "crd_mix_unique_pair",
        (1250, 2500),
        3750,
        "UNIQUE",
        "Two distinct payments. Only one subset equals the credit.",
    ),
    MixedSpec(
        "crd_mix_unique_triple",
        (1500, 2500, 3500),
        7500,
        "UNIQUE",
        "Three distinct payments. Only the full set equals the credit.",
    ),
    MixedSpec(
        "crd_mix_unique_one",
        (100,),
        100,
        "UNIQUE",
        "1:1 payment. One member, one explanation.",
    ),
    MixedSpec(
        "crd_mix_unique_signed",
        (1000, -300, 400),
        1100,
        "UNIQUE",
        "Signed subset-sum. Payment + refund + adjustment has one exact set.",
    ),
    MixedSpec(
        "crd_mix_ambiguous_twins",
        (5000, 5000),
        5000,
        "AMBIGUOUS",
        "Two identical amounts. Either member explains the credit.",
    ),
    MixedSpec(
        "crd_mix_ambiguous_cover",
        (1000, 2000, 3000),
        3000,
        "AMBIGUOUS",
        "Either {3000} or {1000, 2000} sums to the credit.",
    ),
    MixedSpec(
        "crd_mix_none",
        (1000, 2000, 3000),
        9999,
        "NONE_FOUND",
        "No subset equals the credit at exact paise.",
    ),
)


def is_mixed_credit(credit_id: str) -> bool:
    return str(credit_id).startswith(PREFIX)


def _zero_eps_cfg():
    base = load_solver_config()
    search = base.search.model_copy(
        update={"epsilon_rupees": 0, "epsilon_paise_equivalent": 0}
    )
    return base.model_copy(update={"search": search})


def _pool(spec: MixedSpec) -> CandidatePool:
    paise = tuple(int(a) * 100 for a in spec.rupees)
    n = len(paise)
    kinds = tuple(Kind.REFUND if a < 0 else Kind.PAYMENT for a in spec.rupees)
    return CandidatePool(
        bank_credit_id=spec.credit_id,
        item_ids=tuple(f"{spec.credit_id}_i{i:02d}" for i in range(n)),
        amounts_paise=paise,
        amounts_rupees=tuple(int(a) for a in spec.rupees),
        scope=PoolScope.FULL,
        sub_window=None,
        gross_paise=sum(p for p in paise if p > 0),
        kinds=kinds,
        occurred_on=tuple(DAY for _ in range(n)),
        value_date=DAY,
        account_id="acc_mix",
        currency="INR",
    )


def _kind_rows(spec: MixedSpec) -> list[dict[str, object]]:
    mags = [abs(int(a) * 100) for a in spec.rupees]
    peak = max(mags) if mags else 1
    rows = []
    for i, rupee in enumerate(spec.rupees):
        paise = int(rupee) * 100
        label = "REFUND" if rupee < 0 else "PAYMENT"
        rows.append(
            {
                "label": f"{label} {i:02d}",
                "amount": format_rupees(paise),
                "width_pct": (abs(paise) * 100) // peak,
            }
        )
    return rows


@dataclass(frozen=True)
class MixedRow:
    credit_id: str
    amount: str
    amount_paise: int
    residual: str
    residual_paise: int
    uniqueness: str
    expect: str
    why: str
    pool: str
    members: tuple[str, ...]
    n_members: int
    alternates: int
    eval_would_clear: bool
    eval_label: str
    console_write: str
    decision: dict
    kind_rows: list[dict[str, object]]
    proof_text: str
    narration: str


def _row(spec: MixedSpec) -> MixedRow:
    pool = _pool(spec)
    target_paise = spec.target_rupees * 100
    got = solve_search(pool, target_paise, _zero_eps_cfg())
    uniq = got.uniqueness.value
    residual_paise = 0 if uniq in {"UNIQUE", "AMBIGUOUS"} else target_paise
    ordering = "1.000000" if uniq == "UNIQUE" else ("0.650668" if uniq == "AMBIGUOUS" else None)
    decision = auto_clear_decision(
        residual_paise=residual_paise,
        uniqueness=uniq,
        pool_scope=got.pool_scope.value if got.pool_scope else "FULL",
        ordering_score=ordering,
        disposition="FLAGGED",
    )
    pool_txt = " + ".join(format_rupees(int(a) * 100) for a in spec.rupees)
    members = got.member_ids
    proof = (
        f"PROOF  {spec.credit_id}\n"
        f"corpus      CONSTRUCTED_MIXED (not official Track 04)\n"
        f"regime      B_SEARCHED\n"
        f"uniqueness  {uniq}\n"
        f"expect      {spec.expect}\n"
        f"credit      {format_rupees(target_paise)}\n"
        f"pool        {pool_txt}\n"
        f"scope       FULL  epsilon 0\n"
        f"members     {', '.join(members) if members else '—'}\n"
        f"alternates  {got.alternates}\n"
        f"eval        {decision['eval_label']}\n"
        "overlay     does not write CLEARED\n"
    )
    return MixedRow(
        credit_id=spec.credit_id,
        amount=format_rupees(target_paise),
        amount_paise=target_paise,
        residual=format_rupees(residual_paise),
        residual_paise=residual_paise,
        uniqueness=uniq,
        expect=spec.expect,
        why=spec.why,
        pool=pool_txt,
        members=members,
        n_members=len(members) if members else len(spec.rupees),
        alternates=got.alternates,
        eval_would_clear=bool(decision["eval_would_clear"]),
        eval_label=str(decision["eval_label"]),
        console_write=str(decision["final"]),
        decision=decision,
        kind_rows=_kind_rows(spec),
        proof_text=proof,
        narration=f"NEFT MIXED DESK {spec.credit_id}",
    )


@lru_cache(maxsize=1)
def mixed_rows() -> tuple[MixedRow, ...]:
    return tuple(_row(spec) for spec in SPECS)


def mixed_by_id() -> dict[str, MixedRow]:
    return {row.credit_id: row for row in mixed_rows()}


def mixed_counts() -> dict[str, int]:
    rows = mixed_rows()
    uniq = sum(1 for row in rows if row.uniqueness == "UNIQUE")
    amb = sum(1 for row in rows if row.uniqueness == "AMBIGUOUS")
    none = sum(1 for row in rows if row.uniqueness == "NONE_FOUND")
    eligible = sum(1 for row in rows if row.eval_would_clear)
    return {
        "n": len(rows),
        "unique": uniq,
        "ambiguous": amb,
        "none_found": none,
        "eval_eligible": eligible,
        "overlay_cleared": 0,
    }


def mixed_neighbors(credit_id: str) -> tuple[str | None, str | None]:
    ids = [row.credit_id for row in mixed_rows()]
    if credit_id not in ids:
        return None, None
    i = ids.index(credit_id)
    prev_id = ids[i - 1] if i > 0 else None
    next_id = ids[i + 1] if i + 1 < len(ids) else None
    return prev_id, next_id


def mixed_credit_context(credit_id: str) -> dict | None:
    row = mixed_by_id().get(credit_id)
    if row is None:
        return None
    prev_id, next_id = mixed_neighbors(credit_id)
    unique_ok = row.uniqueness == "UNIQUE"
    from residual_zero.console.proof_explorer import mixed_proof

    return {
        "active": "mixed",
        "credit_id": row.credit_id,
        "row": None,
        "amount": row.amount,
        "account": "acc_mix",
        "value_date": DAY.isoformat(),
        "narration": row.narration,
        "utr": f"UTR_MIX_{row.credit_id[-8:].upper()}",
        "currency": "INR",
        "n_members": row.n_members,
        "kind_rows": row.kind_rows,
        "exception_class": "" if unique_ok else row.uniqueness,
        "uniqueness": row.uniqueness,
        "residual": row.residual,
        "regime": "B_SEARCHED",
        "waterfall": "",
        "proof_text": row.proof_text,
        "matched_rule": "constructed mixed desk",
        "disposition": "FLAGGED",
        "prev_id": prev_id,
        "next_id": next_id,
        "gates": ["SEARCH", row.uniqueness, "FULL", row.eval_label],
        "diagnosis": row.why,
        "identity_ok": row.residual_paise == 0,
        "identity_lines": format_rupees(row.amount_paise - row.residual_paise),
        "posted_sum": "",
        "gate_a_ok": False,
        "gate_a_residual": row.residual,
        "gate_a_deltas": 0,
        "posted_mismatch": False,
        "greedy": None,
        "mcp": None,
        "resolution": "",
        "auto_cleared": False,
        "why": None,
        "evidence_level": {
            "level": 5 if unique_ok else 2,
            "label": "UNIQUE_VERIFIED" if unique_ok else row.uniqueness,
            "potentially_recoverable": False,
        },
        "next_action": {
            "action": (
                "Eval would clear. Overlay does not write CLEARED."
                if row.eval_would_clear
                else "Leave flagged. Overlay does not write CLEARED."
            ),
            "writes_cleared": False,
        },
        "four_way": None,
        "causal": (),
        "sla_age": None,
        "sla_bucket": "",
        "three_way": None,
        "dispute_draft": "",
        "playbook": row.why + " Overlay does not write CLEARED.",
        "work": {},
        "utr_siblings": {"utr": "", "n": 0, "ids": [], "writes_cleared": False},
        "clear_decision": row.decision,
        "mixed_corpus": True,
        "proof": mixed_proof(row.credit_id),
        "architecture": True,
    }
