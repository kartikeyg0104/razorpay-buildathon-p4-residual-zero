"""Dump and compare per-credit A3 dispositions. Used by F54 and the flags-off test."""

from __future__ import annotations

import json
from pathlib import Path

from residual_zero.config import load_fees, load_llm_config, load_profile, load_solver_config, load_tax_rates
from residual_zero.features import FeatureFlags
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.models import Disposition

from eval.arms.a3_full import run_a3
from eval.loader import load_split
from eval.truth_loader import load_truth


def collect_a3_dispositions(
    split: str,
    data_root: Path,
    flags: FeatureFlags,
) -> dict[str, str]:
    """Run A3 and return {credit_id: disposition.value}."""
    items, credits = load_split(split, data_root=data_root)
    truth_recs = load_truth(split, data_root=data_root)
    truth_members = {r.bank_credit_id: r.member_ids for r in truth_recs}
    rates, fees, cfg = load_tax_rates(), load_fees(), load_solver_config()
    llm_cfg = load_llm_config()
    profile_path = Path("config").joinpath("profiles").joinpath(
        "phase1_test.yaml" if split == "test" else "phase1.yaml"
    )
    reserve_bps = load_profile(profile_path).reserve_bps
    root = SourceRoot(data_root.joinpath(split, "rendered"))
    declared_rows = load_settlement_report(root)
    by_credit: dict[str, list] = {}
    for row in declared_rows:
        by_credit.setdefault(row.credit_id, []).append(row)
    result = run_a3(
        items, credits, by_credit, truth_members, rates, fees, cfg, llm_cfg, reserve_bps,
        flags=flags,
    )
    return {cid: disp.value for cid, disp in result.dispositions.items()}


def write_dispositions(path: Path, mapping: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: mapping[k] for k in sorted(mapping)}
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def read_dispositions(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping")
    return {str(k): str(v) for k, v in raw.items()}


def assert_known_dispositions(mapping: dict[str, str]) -> None:
    allowed = {d.value for d in Disposition}
    bad = {cid: disp for cid, disp in mapping.items() if disp not in allowed}
    if bad:
        raise ValueError(f"unknown dispositions: {bad}")
