"""Deterministic F19/F56 credit selection from the dev split. Eval-side; never imported by src/."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from residual_zero.models import Regime

from eval.truth_loader import load_truth

_ID = re.compile(r"^crd_(\d+)_(acc_\d+)_(\d{4}-\d{2}-\d{2})$")


def _sort_key(credit_id: str) -> tuple[int, str, str, str]:
    match = _ID.match(credit_id)
    if match is None:
        return (0, "", "", credit_id)
    seed, account, value_date = match.group(1), match.group(2), match.group(3)
    return (int(seed), account, value_date, credit_id)


def select_credits(split: str = "dev", n: int = 20, data_root: Path = Path("data")) -> tuple[str, ...]:
    """Sort by (seed, account_id, value_date, credit_id), then stratified sample (D18)."""
    records = load_truth(split, data_root)
    ordered = sorted(records, key=lambda r: _sort_key(r.bank_credit_id))
    by_class: dict[int, list] = defaultdict(list)
    for rec in ordered:
        labels = rec.corruption_classes or (0,)
        by_class[min(labels)].append(rec)
    picked: list = []
    seen: set[str] = set()

    def take_class(cls: int, need: int) -> None:
        taken = 0
        for rec in by_class.get(cls, ()):
            if rec.bank_credit_id in seen:
                continue
            picked.append(rec)
            seen.add(rec.bank_credit_id)
            taken += 1
            if taken >= need:
                return

    take_class(23, 2)
    take_class(4, 2)
    take_class(1, 2)
    if not any(p.regime == Regime.A_DECLARED for p in picked):
        for rec in ordered:
            if rec.regime == Regime.A_DECLARED and rec.bank_credit_id not in seen:
                picked.append(rec)
                seen.add(rec.bank_credit_id)
                break
    for rec in ordered:
        if len(picked) >= n:
            break
        if rec.bank_credit_id in seen:
            continue
        picked.append(rec)
        seen.add(rec.bank_credit_id)
    return tuple(p.bank_credit_id for p in picked[:n])


def write_study(out: Path, split: str = "dev", data_root: Path = Path("data")) -> Path:
    ids = select_credits(split, 20, data_root)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "split": split,
        "n": len(ids),
        "credit_ids": list(ids),
        "selection": (
            "D18: sort (seed, account_id, value_date, credit_id); "
            "stratified 2x class-23, 2x class-4, 2x class-1, >=1 Regime A; remainder by sort key"
        ),
    }
    path = out.joinpath("selected_credits.json")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    header = "credit_id,disposition,member_ids,elapsed_seconds,confusion_note\n"
    for n_rater in (1, 2, 3):
        rows = header + "".join(f"{cid},,,,\n" for cid in ids)
        out.joinpath(f"rater_{n_rater}.csv").write_text(rows, encoding="utf-8")
    return path
