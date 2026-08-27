"""Fit ε(n)=ceil(k·√n) paise on paise-exact true decompositions. Eval path only."""

from __future__ import annotations

from collections import Counter
from math import ceil, sqrt
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from eval.truth_loader import load_truth
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.money import to_rupee_units
from residual_zero.solver.tolerance import ceil_k_sqrt_n, paise_window_to_rupees

_STRICT = ConfigDict(frozen=True, extra="forbid")


class FittedEpsilon(BaseModel):
    model_config = _STRICT

    n_truth: int = Field(ge=0)
    n_exact: int = Field(ge=0)
    k: int = Field(ge=1)
    derived_epsilon_paise: int = Field(ge=0)
    derived_epsilon_rupees: int = Field(ge=0)
    max_rupee_err: int = Field(ge=0)
    rupee_err_counts: dict[int, int]


def _rupee_err(member_paise: tuple[int, ...], credit_paise: int) -> int:
    return abs(sum(to_rupee_units(a) for a in member_paise) - to_rupee_units(credit_paise))


def fit_k(split: str = "dev", data_root: Path | None = None) -> FittedEpsilon:
    """Smallest integer k such that ceil(k·√n)/100 covers every paise-exact true set."""
    root_path = (data_root or Path("data")).joinpath(split, "rendered")
    root = SourceRoot(root_path)
    items = {it.id: it for it in load_ledger_items(root)}
    credits = {c.id: c for c in load_bank_credits(root)}
    recs = load_truth(split, data_root or Path("data"))
    exact: list[tuple[int, int]] = []
    for rec in recs:
        members = [items[i] for i in rec.member_ids if i in items]
        if len(members) != len(rec.member_ids):
            continue
        credit = credits[rec.bank_credit_id]
        paise = tuple(m.amount_paise for m in members)
        if sum(paise) != credit.amount_paise:
            continue
        exact.append((len(members), _rupee_err(paise, credit.amount_paise)))
    if not exact:
        raise RuntimeError("no paise-exact true decompositions to fit")
    k = 1
    while True:
        misses = [
            (n, err)
            for n, err in exact
            if paise_window_to_rupees(ceil_k_sqrt_n(k, n) if n else 0) < err
        ]
        if not misses:
            break
        k += 1
        if k > 10_000:
            raise RuntimeError("k did not converge")
    max_n = max(n for n, _ in exact)
    derived_paise = ceil_k_sqrt_n(k, max_n)
    derived_rupees = paise_window_to_rupees(derived_paise)
    counts = Counter(err for _, err in exact)
    return FittedEpsilon(
        n_truth=len(recs),
        n_exact=len(exact),
        k=k,
        derived_epsilon_paise=derived_paise,
        derived_epsilon_rupees=derived_rupees,
        max_rupee_err=max(err for _, err in exact),
        rupee_err_counts={int(a): int(b) for a, b in sorted(counts.items())},
    )


def main() -> None:
    fitted = fit_k()
    print(fitted.model_dump_json(indent=2))
    # eval may use floats; this print is documentary.
    print("float_check", ceil(fitted.k * sqrt(max(fitted.rupee_err_counts) or 1)))


if __name__ == "__main__":
    main()
