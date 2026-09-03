#!/usr/bin/env python3
"""Sections 9-12 and 31-35 — code hygiene, decoupling, secrets, frontend safety.

Classifies rather than deletes. Writes `artifacts/qa/code_hygiene_audit.json`.

  artifact_decoupling  production code must not silently depend on evaluation artifacts
  hardcoded_metrics    every official-number occurrence classified
  machine_paths        absolute/user-specific paths in production code
  secrets              credential handling; values are never printed
  error_handling       broad suppression that could convert failure into false success
  debug_leakage        prints, breakpoints, TODO/FIXME in production paths
  frontend             official metrics in templates/JS must come from the backend
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
QA = ROOT / "artifacts" / "qa"
SRC = ROOT / "src" / "residual_zero"
TEMPLATES = SRC / "console" / "templates"
STATIC = SRC / "console" / "static"

OFFICIAL_NUMBERS = ["159/239", "521/800", "148/239", "129/239", "501/800", "464/800", "142/239"]
OFFICIAL_SCALARS = ["239", "800", "159", "521", "142", "464", "148", "501", "236", "779"]

# CLI entrypoints: stdout is their interface, so print() is correct there.
CLI_MODULES = {
    "cli.py", "orchestrator.py", "__main__.py", "books.py", "challenge.py",
}


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def py_files(base: Path):
    for p in sorted(base.rglob("*.py")):
        if "__pycache__" not in p.parts:
            yield p


# --------------------------------------------------------- 9. artifact decoupling


def artifact_decoupling() -> dict:
    """Production code may read a committed official card, but must degrade safely."""
    refs: list[dict] = []
    patterns = {
        "artifacts/dev": r"artifacts[\"'/\\ ]*.{0,4}dev",
        "artifacts/test": r"artifacts[\"'/\\ ]*.{0,4}test",
        "truth.jsonl": r"truth\.jsonl",
        "tests/": r"[\"']tests/",
        "fixtures/": r"fixtures/",
    }
    for path in py_files(SRC):
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pat in patterns.items():
            for m in re.finditer(pat, text):
                line_no = text[: m.start()].count("\n") + 1
                line = text.splitlines()[line_no - 1].strip()
                refs.append({"file": rel(path), "line": line_no, "kind": label, "code": line[:150]})

    # The console card readers are architectural. Verify they degrade instead of faking.
    from residual_zero.console.facts import t04_fields, t04_view

    missing_split = t04_view("definitely_not_a_split")
    degrades = all(v == "" for v in missing_split.values())
    empty_fields = t04_fields("definitely_not_a_split") == {}

    return {
        "artifact_references_in_src": refs,
        "reference_count": len(refs),
        "t04_view_missing_card_returns_empty_strings": degrades,
        "t04_fields_missing_card_returns_empty_dict": empty_fields,
        "pass": degrades and empty_fields,
        "note": (
            "The console intentionally reads committed artifacts/{split}/t04.md as the "
            "official card. Missing or unparseable cards yield empty strings, which the "
            "templates render as a placeholder rather than a fabricated metric."
        ),
    }


# ------------------------------------------------------ 10 + 34. hardcoded metrics


def hardcoded_metrics() -> dict:
    rows: list[dict] = []
    scan_targets = (
        [(p, "production-python") for p in py_files(SRC)]
        + [(p, "template") for p in sorted(TEMPLATES.glob("*.html"))]
        + [(p, "frontend-js") for p in sorted(STATIC.glob("*.js"))]
        + [(p, "frontend-css") for p in sorted(STATIC.glob("*.css"))]
    )
    for path, kind in scan_targets:
        text = path.read_text(encoding="utf-8", errors="replace")
        for number in OFFICIAL_NUMBERS:
            for m in re.finditer(re.escape(number), text):
                line_no = text[: m.start()].count("\n") + 1
                line = text.splitlines()[line_no - 1].strip()
                # Any official metric baked into production Python is a literal, whether
                # it is a bare string or interpolated inside an f-string.
                classification = "DOCUMENTATION"
                if kind == "production-python" and not line.lstrip().startswith("#"):
                    classification = "PRODUCTION_LITERAL"
                elif kind in {"template", "frontend-js"} and "{{" not in line and "{%" not in line:
                    classification = "DISPLAY_COPY"
                rows.append(
                    {
                        "file": rel(path),
                        "line": line_no,
                        "number": number,
                        "kind": kind,
                        "class": classification,
                        "code": line[:160],
                    }
                )

    production_literals = [r for r in rows if r["class"] == "PRODUCTION_LITERAL"]

    # Behavioural check: render the metric surfaces with no artifacts at all.
    import subprocess
    import tempfile

    # Cover the console metric strip *and* the AI answer surfaces. A hardcoded official
    # number anywhere in these paths becomes a fabricated financial fact.
    probe = (
        "import json\n"
        "from residual_zero.console.facts import honesty_line, track04_snapshot, t04_view\n"
        "print(honesty_line(0,0,0,0))\n"
        "print(' '.join(str(v) for v in track04_snapshot()))\n"
        "print(json.dumps(t04_view('dev')), json.dumps(t04_view('test')))\n"
        "from residual_zero.qa.desk_tools import batch_prose\n"
        "print(batch_prose())\n"
        "from residual_zero.qa.corpus import load_documents\n"
        "print(' '.join(d.body for d in load_documents()))\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=tmp,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
        )
    fabricated = [n for n in OFFICIAL_NUMBERS if n in proc.stdout] if proc.returncode == 0 else ["probe_failed"]

    # Templates must bind metrics through the template engine.
    batch = (TEMPLATES / "batch.html").read_text(encoding="utf-8")
    bound = "t04_test.residual_zero" in batch and "t04_dev.verified_linked" in batch

    return {
        "occurrences": rows,
        "occurrence_count": len(rows),
        "by_class": {
            c: sum(1 for r in rows if r["class"] == c)
            for c in {r["class"] for r in rows}
        },
        "production_literals": production_literals,
        "fabricated_without_artifacts": fabricated,
        "dashboard_binds_metrics_through_template": bound,
        "pass": not production_literals and not fabricated and bound,
    }


# ------------------------------------------------------- 11. machine-specific paths


def machine_paths() -> dict:
    bad = re.compile(r"/Users/|C:\\\\Users|/home/[a-z][a-z0-9_-]*|/private/var/folders|/tmp/[a-z]")
    hits = []
    for path in py_files(SRC):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in bad.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            hits.append(
                {
                    "file": rel(path),
                    "line": line_no,
                    "match": m.group(0),
                    "code": text.splitlines()[line_no - 1].strip()[:150],
                }
            )
    # venv path assumptions inside production code
    venv_hits = [
        {"file": rel(p), "line": text.count("\n", 0, m.start()) + 1}
        for p in py_files(SRC)
        for text in [p.read_text(encoding="utf-8", errors="replace")]
        for m in re.finditer(r"\.venv/bin/python", text)
    ]
    return {
        "absolute_or_user_paths_in_src": hits,
        "venv_assumptions_in_src": venv_hits,
        "pass": not hits and not venv_hits,
    }


# ------------------------------------------------------------------ 12. secrets


def secrets_audit() -> dict:
    """Never prints a value. Reports names, lengths and gitignore status only."""
    import subprocess

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").is_file() else ""
    ignored = {}
    for candidate in (".env", ".env.local", "credentials.json", "secrets.yaml", "id_rsa"):
        proc = subprocess.run(
            ["git", "check-ignore", candidate], cwd=ROOT, capture_output=True, text=True
        )
        ignored[candidate] = proc.returncode == 0

    # .env.example must be a template: no value that looks like a real key.
    example = ROOT / ".env.example"
    example_rows = []
    if example.is_file():
        for line in example.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            value = value.strip().strip("\"'")
            example_rows.append(
                {
                    "name": name.strip(),
                    "value_length": len(value),
                    "looks_like_real_secret": bool(re.fullmatch(r"gsk_[A-Za-z0-9]{20,}", value)),
                }
            )

    # Hardcoded key literals anywhere in tracked source.
    key_pattern = re.compile(r"gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}")
    literal_hits = []
    for base in (SRC, ROOT / "scripts", ROOT / "eval", ROOT / "tests", ROOT / "config"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if key_pattern.search(text):
                literal_hits.append(rel(path))

    # Credentials must be read from the environment.
    env_reads = []
    for path in py_files(SRC):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"environ(?:\.get)?\(\s*[\"'](NVIDIA[A-Z_]*|AI_[A-Z_]*|RZ_LLM[A-Z_]*)[\"']", text):
            env_reads.append({"file": rel(path), "var": m.group(1)})

    # The audit sink must strip the key.
    from residual_zero.qa import finance_audit
    import inspect

    strips_key = "api_key" in inspect.getsource(finance_audit.record_audit)

    return {
        "gitignore_covers": ignored,
        "env_example_rows": example_rows,
        "env_example_has_no_real_secret": all(not r["looks_like_real_secret"] for r in example_rows),
        "hardcoded_key_literals": literal_hits,
        "credential_env_reads": env_reads,
        "audit_sink_strips_api_key": strips_key,
        "dotenv_is_gitignored": ignored.get(".env", False),
        "pass": (
            ignored.get(".env", False)
            and not literal_hits
            and all(not r["looks_like_real_secret"] for r in example_rows)
            and strips_key
        ),
    }


# ------------------------------------------------- 31 + 32 + 33. quality / errors


def error_and_debug_audit() -> dict:
    broad: list[dict] = []
    bare: list[dict] = []
    prints: list[dict] = []
    markers: list[dict] = []
    for path in py_files(SRC):
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    bare.append({"file": rel(path), "line": node.lineno})
                    continue
                names = []
                if isinstance(node.type, ast.Name):
                    names = [node.type.id]
                elif isinstance(node.type, ast.Tuple):
                    names = [e.id for e in node.type.elts if isinstance(e, ast.Name)]
                if "Exception" in names or "BaseException" in names:
                    body_is_pass = len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
                    returns_none = (
                        len(node.body) == 1
                        and isinstance(node.body[0], ast.Return)
                        and (node.body[0].value is None
                             or (isinstance(node.body[0].value, ast.Constant) and node.body[0].value.value is None))
                    )
                    broad.append(
                        {
                            "file": rel(path),
                            "line": node.lineno,
                            "silent_pass": body_is_pass,
                            "returns_none": returns_none,
                            "code": lines[node.lineno - 1].strip()[:120],
                            "financial_module": path.name in {"verify.py", "candidates.py", "money.py"}
                            or "solver" in path.parts,
                        }
                    )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "print":
                    prints.append(
                        {
                            "file": rel(path),
                            "line": node.lineno,
                            "class": "SAFE_CLI" if path.name in CLI_MODULES else "REVIEW",
                        }
                    )
                if node.func.id == "breakpoint":
                    markers.append({"file": rel(path), "line": node.lineno, "kind": "breakpoint"})
        for i, line in enumerate(lines, 1):
            if re.search(r"\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b", line):
                markers.append({"file": rel(path), "line": i, "kind": "marker", "code": line.strip()[:120]})
            if "pdb.set_trace" in line or "import pdb" in line or "ipdb" in line:
                markers.append({"file": rel(path), "line": i, "kind": "pdb"})

    financial_broad = [b for b in broad if b["financial_module"]]
    silent = [b for b in broad if b["silent_pass"]]
    prints_review = [p for p in prints if p["class"] == "REVIEW"]

    # Explicitly verify the two conversions the spec forbids.
    solver_text = (SRC / "solver" / "enumerate.py").read_text(encoding="utf-8")
    budget_not_downgraded = "Uniqueness.BUDGET_EXCEEDED" in solver_text
    provider_text = (SRC / "semantic" / "provider.py").read_text(encoding="utf-8")
    provider_failure_explicit = "fallback" in provider_text.casefold() and "error" in provider_text.casefold()

    return {
        "broad_except_count": len(broad),
        "broad_except_in_financial_modules": financial_broad,
        "silent_pass_handlers": silent,
        "bare_except_handlers": bare,
        "print_calls": len(prints),
        "print_calls_outside_cli": prints_review,
        "debug_markers": markers,
        "budget_exceeded_state_preserved": budget_not_downgraded,
        "provider_failure_reported_explicitly": provider_failure_explicit,
        "pass": (
            not financial_broad
            and not bare
            and not markers
            and not prints_review
            and budget_not_downgraded
        ),
    }


# ------------------------------------------------------------------ 33. logging


def logging_audit() -> dict:
    """Log/audit sinks must not carry credentials."""
    audit_log = ROOT / "artifacts" / "console" / "ai_audit.jsonl"
    findings = {"file": rel(audit_log) if audit_log.is_file() else None}
    if audit_log.is_file():
        blob = audit_log.read_text(encoding="utf-8", errors="replace")
        findings.update(
            {
                "entries": sum(1 for line in blob.splitlines() if line.strip()),
                "gsk_key_hits": len(re.findall(r"gsk_[A-Za-z0-9]{10,}", blob)),
                "authorization_hits": len(re.findall(r"(?i)authorization", blob)),
                "bearer_hits": len(re.findall(r"(?i)bearer\s", blob)),
                "api_key_field_hits": len(re.findall(r'"api_key"', blob)),
            }
        )
        findings["pass"] = (
            findings["gsk_key_hits"] == 0
            and findings["authorization_hits"] == 0
            and findings["bearer_hits"] == 0
            and findings["api_key_field_hits"] == 0
        )
    else:
        findings["pass"] = True
        findings["note"] = "no audit log present"
    return findings


# ------------------------------------------------------- 35. frontend consistency


def frontend_consistency() -> dict:
    """No template may compute financial truth; it renders backend values."""
    arithmetic = re.compile(r"\{\{[^}]*[\*/%][^}]*\}\}")
    offenders = []
    for path in sorted(TEMPLATES.glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in arithmetic.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            offenders.append({"file": rel(path), "line": line_no, "expr": m.group(0)[:120]})
    js_math = []
    for path in sorted(STATIC.glob("*.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"(residual|uniqueness|cleared|matched)\s*[-+*/]=", text, re.I):
            js_math.append({"file": rel(path), "match": m.group(0)})
    return {
        "template_arithmetic_on_values": offenders,
        "frontend_financial_mutation": js_math,
        "pass": not offenders and not js_math,
    }


SECTIONS = {
    "artifact_decoupling": artifact_decoupling,
    "hardcoded_metrics": hardcoded_metrics,
    "machine_paths": machine_paths,
    "secrets": secrets_audit,
    "error_and_debug": error_and_debug_audit,
    "logging": logging_audit,
    "frontend": frontend_consistency,
}


def main() -> int:
    QA.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    for name, fn in SECTIONS.items():
        payload[name] = fn()
    failures = [n for n, r in payload.items() if not r.get("pass")]
    payload["failures"] = failures
    payload["pass"] = not failures
    (QA / "code_hygiene_audit.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    for name in SECTIONS:
        r = payload[name]
        print(f"  [{'PASS' if r.get('pass') else 'FAIL'}] {name}")
    print(f"\nHYGIENE: {'PASS' if payload['pass'] else 'FAIL'}  failures={failures}")
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
