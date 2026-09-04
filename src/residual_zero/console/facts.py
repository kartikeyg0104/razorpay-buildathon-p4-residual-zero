"""Eval facts from committed artifacts. Console overlay is a different predicate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple


def _arm_row(path: Path, arm: str) -> list[str] | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= set("-:"):
            continue
        if cells[0].casefold() == arm:
            return cells
    return None


def _residual_zero_cell(split: str) -> str:
    """residual-zero for a split, read from the committed official card.

    Never falls back to a literal. A missing or unparseable card renders "—" so the
    console cannot display an official-looking metric that was never computed.
    """
    cell = t04_fields(split).get("residual-zero", "").strip()
    if cell:
        return cell
    row = _arm_row(Path("artifacts").joinpath(split, "headline.md"), "a3")
    if split == "dev":
        summary = forensic_summary()
        rz = summary.get("residual_zero")
        n_scored = summary.get("n_scored") or (row[1] if row and len(row) > 1 else None)
        if rz is not None and n_scored:
            return f"{rz}/{n_scored}"
    return "—"


def honesty_line(
    n_posted: int,
    n_gate_a: int,
    n_journalable: int,
    n_human: int,
) -> str:
    """One strip a reviewer can check against headline.md. No overlay writes CLEARED."""
    mismatch = n_gate_a - n_journalable if n_gate_a >= n_journalable else 0
    dev = _arm_row(Path("artifacts").joinpath("dev", "headline.md"), "a3")
    test = _arm_row(Path("artifacts").joinpath("test", "headline.md"), "a3")
    exact = dev[2] if dev and len(dev) > 2 else "—"
    assign_r = dev[4] if dev and len(dev) > 4 else "—"
    test_exact = test[2] if test and len(test) > 2 else "—"
    test_budget = test[7] if test and len(test) > 7 else "—"
    scored = dev[1] if dev and len(dev) > 1 else "—"
    dev_residual_zero = _residual_zero_cell("dev")
    test_residual_zero = _residual_zero_cell("test")
    return (
        f"Eval A3 (n={scored} scored): residual-zero {dev_residual_zero}, settlement-linked {exact}, "
        f"search-cleared 0, assignment R {assign_r}. "
        f"Console overlay (n={n_posted} posted): Gate A {n_gate_a} is verify_declared.ok, "
        f"not the exact cell; journalable {n_journalable}; posted-mismatch {mismatch}; "
        f"human {n_human}. Overlay does not write CLEARED. Synthetic corpus. F56 not run. "
        f"Test A3: settlement-linked {test_exact}, budget-exceeded {test_budget}, "
        f"residual-zero {test_residual_zero}, cleared 0. "
        f"Threshold 1.000000 is refuse-all. F36 live pairs 245/245 cap-refused."
    )


class Track04Snapshot(NamedTuple):
    """Headline / books / latency strings. No computed percentages."""

    scored: str
    exact: str
    search_cleared: str
    flagged: str
    budget_dev: str
    test_exact: str
    test_budget: str
    unreconciled: str
    double_claimed: str
    throughput_per_1000s: str
    wall_ns: str
    residual_zero: str
    settlement_linked: str
    test_search_completed: str


def _after_equals(blob: str, key: str) -> str:
    needle = key + "="
    start = blob.find(needle)
    if start < 0:
        return ""
    start += len(needle)
    end = start
    while end < len(blob) and blob[end] not in " \n":
        end += 1
    return blob[start:end]


def _dash_field(blob: str, key: str) -> str:
    needle = "- " + key + ":"
    for line in blob.splitlines():
        if line.startswith(needle):
            return line.split(":", 1)[1].strip()
    return ""


def t04_fields(split: str) -> dict[str, str]:
    """Parse committed artifacts/{split}/t04.md dash fields. Missing file → empty."""
    path = Path("artifacts").joinpath(split, "t04.md")
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- ") or ":" not in line:
            continue
        key, _, value = line[2:].partition(":")
        name = key.strip()
        if name:
            out[name] = value.strip()
    return out


def t04_view(split: str) -> dict[str, str]:
    """Stable keys for templates. Empty strings if the official card is missing."""
    raw = t04_fields(split)
    return {
        "n_scored": raw.get("n_scored", ""),
        "residual_zero": raw.get("residual-zero", ""),
        "identified": raw.get("settlement-linked / member-identified", ""),
        "verified_linked": raw.get("verified-linked (ids + residual 0)", ""),
        "unique": raw.get("unique", ""),
        "ambiguous": raw.get("ambiguous", ""),
        "none_found": raw.get("none_found", ""),
        "auto_clear": raw.get("auto-clear", ""),
        "false_clears": raw.get("false_clears", ""),
        "search_coverage": raw.get("search_coverage", ""),
        "budget_exceeded_search": raw.get("budget_exceeded_search", ""),
        "flagged": raw.get("flagged", ""),
    }


def track04_snapshot() -> Track04Snapshot:
    """Read committed artifacts only. Exact/n is the match rate. Auto-clear is a different cell."""
    dev = _arm_row(Path("artifacts").joinpath("dev", "headline.md"), "a3")
    test = _arm_row(Path("artifacts").joinpath("test", "headline.md"), "a3")
    books = Path("artifacts").joinpath("dev", "books.md")
    latency = Path("artifacts").joinpath("dev", "latency.md")
    book_text = books.read_text(encoding="utf-8") if books.is_file() else ""
    lat_text = latency.read_text(encoding="utf-8") if latency.is_file() else ""
    fs = forensic_summary()
    rz = fs.get("residual_zero")
    if rz is None:
        rz = fs.get("a3_exact_verify_gated")
    sl = fs.get("named_declared_eq_truth")
    n_scored = fs.get("n_scored") or (dev[1] if dev and len(dev) > 1 else "")
    residual_zero = f"{rz}/{n_scored}" if rz is not None and n_scored else _residual_zero_cell("dev")
    settlement_linked = f"{sl}/{n_scored}" if sl is not None and n_scored else "—"
    test_n = test[1] if test and len(test) > 1 else ""
    test_budget = test[7] if test and len(test) > 7 else "—"
    completed = ""
    if str(test_n).isdigit() and str(test_budget).isdigit():
        completed = f"{int(test_n) - int(test_budget)}/{test_n}"
    return Track04Snapshot(
        scored=dev[1] if dev and len(dev) > 1 else "—",
        exact=dev[2] if dev and len(dev) > 2 else "—",
        search_cleared=dev[5] if dev and len(dev) > 5 else "—",
        flagged=dev[6] if dev and len(dev) > 6 else "—",
        budget_dev=dev[7] if dev and len(dev) > 7 else "—",
        test_exact=test[2] if test and len(test) > 2 else "—",
        test_budget=test_budget,
        unreconciled=_after_equals(book_text, "unreconciled_value") or "—",
        double_claimed=_after_equals(book_text, "double_claimed") or "—",
        throughput_per_1000s=_dash_field(lat_text, "throughput_credits_per_1000s"),
        wall_ns=_dash_field(lat_text, "wall_ns"),
        residual_zero=residual_zero,
        settlement_linked=settlement_linked,
        test_search_completed=completed or "—",
    )


_RECOVERY = {
    "EXACT_DECLARED_OK": "MATCHED",
    "DECLARED_EQ_TRUTH_VERIFY_FAIL": "RECOVERED",
    "DECLARED_OK_BUT_NOT_TRUTH": "GENUINELY_UNMATCHED",
    "DECLARED_NE_TRUTH_VERIFY_FAIL": "GENUINELY_UNMATCHED",
    "NO_DECLARED_WINDOW_MISS": "GENUINELY_UNMATCHED",
    "NO_DECLARED_TRUTH_MISSING": "GENUINELY_UNMATCHED",
    "NO_DECLARED_ACCOUNT_MISS": "GENUINELY_UNMATCHED",
    "NO_DECLARED_SEARCH_PATH": "AMBIGUOUS",
    "OTHER": "COMPUTATIONALLY_UNRESOLVED",
}

_RECOVERY_WHY = {
    "MATCHED": "Named declared members equal truth and verify_declared.ok.",
    "RECOVERED": "Settlement named the true ids. Rate re-derive failed. f58 predicts the named set. Not auto-cleared.",
    "GENUINELY_UNMATCHED": "No complete permitted combination equals the bank credit under current semantics.",
    "AMBIGUOUS": "True ids sit in the pool. Search finds more than one subset. Auto-clear refused.",
    "COMPUTATIONALLY_UNRESOLVED": "Search did not finish or the bucket is unclassified.",
}


def forensic_summary() -> dict[str, object]:
    path = Path("artifacts").joinpath("dev", "forensics_summary.json")
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def credit_forensic(credit_id: str) -> dict[str, object] | None:
    """Eval artifact only. Does not open the answer-key file. Missing file → None."""
    rows = _forensic_rows()
    row = rows.get(credit_id)
    if row is None:
        return None
    bucket = str(row.get("bucket") or "OTHER")
    recovery = _RECOVERY.get(bucket, "COMPUTATIONALLY_UNRESOLVED")
    return {
        "bucket": bucket,
        "recovery": recovery,
        "recovery_why": _RECOVERY_WHY[recovery],
        "n_pool": row.get("n_pool", 0),
        "n_declared": row.get("n_declared", 0),
        "n_truth": row.get("n_truth", 0),
        "truth_in_pool": row.get("truth_in_pool", 0),
        "fp_ok": bool(row.get("fp_ok")),
        "residual": row.get("residual"),
        "window_miss": int(row.get("window_miss") or 0),
        "account_miss": int(row.get("account_miss") or 0),
        "ledger_miss": int(row.get("ledger_miss") or 0),
        "a3_exact": bool(row.get("a3_exact")),
        "decl_eq_truth": bool(row.get("decl_eq_truth")),
        "corrupt": list(row.get("corrupt") or []),
    }


def _forensic_rows() -> dict[str, dict]:
    path = Path("artifacts").joinpath("dev", "forensics_exact.json")
    if not path.is_file():
        return {}
    blob = json.loads(path.read_text(encoding="utf-8"))
    return {str(r["id"]): r for r in blob.get("rows") or [] if "id" in r}
