"""Logs must be useful and must never carry a credential. And nothing secret is committed.

A public deployment turns logging from a convenience into a liability: the same line that
lets somebody diagnose a provider failure is the line that leaks the key if the redaction
is opt-in. So redaction here is applied on the way out, by the formatter, and these tests
try to smuggle a secret past it through several shapes at once.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest

from residual_zero import obs

SECRETS = [
    ("NVIDIA_API_KEY", "nvapi-abcdefghijklmnopqrstuvwxyz"),
    ("AI_API_KEY", "nvapi-0123456789abcdefghij"),
    ("password", "hunter2hunter2"),
    ("RZ_SESSION_SECRET", "s" * 48),
    ("authorization", "Bearer rz_pat_abcdefghijklmnopqrstuv"),
    ("cookie", "rz_session=abcdefghijklmnop"),
    ("database_url", "postgresql://u:" + "npg_realpassword" + "@host/db"),
    ("api_key", "sk-abcdefghijklmnopqrstuvwx"),
]


@pytest.mark.parametrize("key,value", SECRETS)
def test_a_secret_is_scrubbed_under_its_own_key(key, value):
    scrubbed = obs.scrub({key: value})
    assert value not in json.dumps(scrubbed)


@pytest.mark.parametrize("_key,value", SECRETS)
def test_a_secret_is_scrubbed_even_under_an_innocent_key(_key, value):
    """A key with a harmless name must not become a bypass."""
    scrubbed = obs.scrub({"note": f"the value is {value} here"})
    if re.search(r"(nvapi-|gsk_|sk-|rz_pat_|npg_|Bearer\s)", value):
        assert value not in json.dumps(scrubbed), value


def test_a_secret_nested_in_a_structure_is_scrubbed():
    payload = {
        "outer": [{"inner": {"NVIDIA_API_KEY": "nvapi-deadbeefdeadbeef"}}],
        "list": ["nvapi-anotheronehere00"],
    }
    rendered = json.dumps(obs.scrub(payload))
    assert "nvapi-" not in rendered


def test_a_connection_string_password_is_removed_but_the_host_survives():
    """Diagnosing a database failure needs the host; it never needs the password."""
    password = "npg_secret_for_scrub_test"
    # Concatenated rather than interpolated, so this file holds no `scheme://user:pass@`
    # literal for the committed-secret scan below to flag.
    dsn = "postgresql://rzuser:" + password + "@db.example/rz"
    scrubbed = obs.scrub({"note": "connecting to " + dsn})
    rendered = json.dumps(scrubbed)
    assert password not in rendered
    assert "db.example" in rendered


def test_the_log_formatter_scrubs_every_field(caplog):
    formatter = obs.JsonFormatter()
    record = logging.LogRecord(
        name="residual_zero", level=logging.INFO, pathname=__file__, lineno=1,
        msg="http.request", args=(), exc_info=None,
    )
    record.fields = {
        "authorization": "Bearer rz_pat_leakleakleakleak",
        "credit_id": "crd_001_acc_01_2025-01-09",
        "status": 200,
        "note": "key nvapi-zzzzzzzzzzzzzzzz was used",
    }
    line = formatter.format(record)
    assert "rz_pat_" not in line
    assert "nvapi-" not in line
    # The diagnostic content survives, or the log is useless.
    assert "crd_001_acc_01_2025-01-09" in line
    assert '"status":200' in line
    assert json.loads(line)["event"] == "http.request"


def test_an_exception_is_logged_as_type_and_message_not_frames():
    formatter = obs.JsonFormatter()
    try:
        raise RuntimeError("provider failed with key nvapi-secretsecretsecret")
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            name="residual_zero", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="provider.failed", args=(), exc_info=sys.exc_info(),
        )
    line = formatter.format(record)
    parsed = json.loads(line)
    assert parsed["error_type"] == "RuntimeError"
    assert "nvapi-" not in line
    assert "Traceback" not in line
    assert "test_observability" not in line, "a frame path reached the log line"


def test_configure_logging_is_idempotent():
    """Import order must not multiply handlers."""
    first = obs.configure_logging()
    count = len(first.handlers)
    obs.configure_logging()
    obs.configure_logging()
    assert len(obs.logger().handlers) == count


def test_the_logged_events_cover_the_failures_worth_diagnosing():
    """Authentication, authorisation, CSRF, provider, database and reconciliation."""
    sources = "\n".join(
        Path(p).read_text(encoding="utf-8")
        for p in (
            "src/residual_zero/console/security.py",
            "src/residual_zero/console/auth_routes.py",
            "src/residual_zero/console/app.py",
            "src/residual_zero/qa/investigation_log.py",
        )
    )
    for event in (
        "auth.rejected", "authz.rejected", "csrf.rejected", "auth.login_failed",
        "request.unhandled", "readyz.database_unreachable", "ai.investigation",
        "http.request",
    ):
        assert event in sources, f"nothing logs {event}"


# ---------------------------------------------------------------- committed secrets

TRACKED_TEXT_SUFFIXES = (".py", ".js", ".json", ".yaml", ".yml", ".md", ".html", ".toml",
                         ".sql", ".sh", ".cfg", ".txt", ".example", "Dockerfile",
                         "docker-compose.yml", ".gitignore")

SECRET_PATTERNS = [
    (r"nvapi-[A-Za-z0-9_\-]{12,}", "an NVIDIA API key"),
    (r"gsk_[A-Za-z0-9]{16,}", "a Groq API key"),
    (r"sk-[A-Za-z0-9]{20,}", "an OpenAI-style API key"),
    (r"rzp_(?:live|test)_[A-Za-z0-9]{10,}", "a Razorpay key"),
    (r"rz_pat_[A-Za-z0-9_\-]{12,}", "a Residual Zero access token"),
    (r"npg_[A-Za-z0-9]{12,}", "a Neon database password"),
    (r"postgres(?:ql)?://[^\s:@/'\"]+:[^\s@/'\"]{6,}@", "a database URL with a password"),
]

# Every credential-SHAPED string that is allowed to exist in a committable file, listed
# exactly. Provider code cannot be tested without key-shaped fixtures, and redaction cannot
# be tested without something to redact — but an allowlist of literals means adding one is a
# deliberate edit to this file, which is the review gate. A real key would not be on it.
ALLOWED_LITERALS = {
    # Test fixtures for the provider and the agent loop.
    "nvapi-test_fixture_not_a_real_key",
    # Redaction fixtures: strings whose whole purpose is to be scrubbed.
    "nvapi-abcdefghijklmnopqrstuvwxyz",
    "nvapi-0123456789abcdefghij",
    "nvapi-deadbeefdeadbeef",
    "nvapi-anotheronehere00",
    "nvapi-zzzzzzzzzzzzzzzz",
    "nvapi-secretsecretsecret",
    "rz_pat_not_a_real_token",
    "rz_pat_missing_the_scheme",
    "rz_pat_abcdefghijklmnopqrstuv",
    "rz_pat_leakleakleakleak",
    "npg_realpassword",
    "npg_secret_for_scrub_test",
    "sk-abcdefghijklmnopqrstuvwx",
    "postgresql://u:npg_realpassword@",
    "postgresql://rzuser:npg_secret@",
    "postgresql://user:sup3rs3cret@",
    # Documentation placeholders.
    "postgresql://user:password@",
    "postgresql://USER:PASSWORD@",
    "postgres://user:password@",
    # docker-compose's local-only database password. The compose file is a local rehearsal
    # stack; the name says so and the port is not published outside the compose network.
    "postgresql://residual:residual_local_only@",
    # The CI service container's throwaway credential, on 127.0.0.1 inside the runner.
    "postgresql://residual:residual_ci@",
}


def _committable_files() -> list[Path]:
    """Tracked files plus new files that are not gitignored.

    Scanning only ``git ls-files`` would miss exactly the risky case: a brand-new file
    holding a real credential, which is committable but not yet committed.
    """
    import subprocess

    def run(args: list[str]) -> list[str]:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False,
        ).stdout.splitlines()

    names = set(run(["ls-files"])) | set(run(["ls-files", "--others", "--exclude-standard"]))
    return [
        Path(name) for name in sorted(names)
        if name.endswith(TRACKED_TEXT_SUFFIXES) and Path(name).is_file()
    ]


@pytest.mark.parametrize("pattern,what", SECRET_PATTERNS)
def test_no_committable_file_contains_a_real_credential(pattern, what):
    offenders = []
    for path in _committable_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in re.finditer(pattern, text):
            if match.group(0) in ALLOWED_LITERALS:
                continue
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path}:{line} looks like {what}: {match.group(0)[:40]}")
    assert not offenders, offenders


def test_the_secret_scan_can_actually_see_a_new_file(tmp_path, monkeypatch):
    """The scan must cover new files, not only committed ones.

    Written because the first version of this test scanned `git ls-files` only, which would
    have said "clean" about a brand-new file containing a live key.
    """
    planted = Path("tests/deployment/_planted_secret_scan_probe.txt")
    # Assembled from parts so this test file does not itself contain a matchable literal —
    # otherwise the scan flags the test that verifies the scan.
    probe = "RZ_DATABASE_URL=" + "postgresql://u:" + "npg_" + "th1sisnotreal" + "@h/db\n"
    planted.write_text(probe, encoding="utf-8")
    try:
        found = [p for p in _committable_files() if p == planted]
        assert found, "a new, non-ignored file was invisible to the scan"
        offenders = []
        for pattern, what in SECRET_PATTERNS:
            for match in re.finditer(pattern, planted.read_text(encoding="utf-8")):
                if match.group(0) not in ALLOWED_LITERALS:
                    offenders.append(what)
        assert offenders, "the planted credential was not detected"
    finally:
        planted.unlink()


def test_the_env_file_is_ignored_and_the_template_is_not():
    """A real .env must never be committable; .env.example must be.

    Asserted as a property of .gitignore rather than of the index, so the test does not
    depend on whether a particular change has been committed yet.
    """
    import subprocess

    def ignored(path: str) -> bool:
        return subprocess.run(
            ["git", "check-ignore", "-q", path], capture_output=True, check=False,
        ).returncode == 0

    assert ignored(".env"), ".env is not gitignored"
    assert not ignored(".env.example"), ".env.example must be committable"
    assert Path(".env.example").is_file()
    # And no real .env is in the index.
    tracked = {
        line for line in subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=False,
        ).stdout.splitlines()
    }
    assert ".env" not in tracked


def test_the_env_example_has_no_filled_in_values():
    text = Path(".env.example").read_text(encoding="utf-8")
    for name in ("NVIDIA_API_KEY", "AI_API_KEY", "RZ_SESSION_SECRET", "RZ_DATABASE_URL"):
        assert re.search(rf"^{name}=\s*$", text, re.M), f"{name} has a value in .env.example"


def test_the_env_example_documents_every_variable_the_code_reads():
    """A variable the code depends on but nobody knows to set is a deployment trap."""
    text = Path(".env.example").read_text(encoding="utf-8")
    read = set()
    for path in Path("src/residual_zero").rglob("*.py"):
        read |= set(re.findall(
            r'os\.environ\.get\(\s*"([A-Z][A-Z0-9_]+)"', path.read_text(encoding="utf-8"),
        ))
    # Internal switches that are not part of a deployment's configuration surface.
    internal = {"PYTEST_CURRENT_TEST", "RZ_EXTRACT_CACHE", "RZ_AI_AUDIT", "RZ_LLM_TEST",
                "RZ_DEFAULT_SCHEMA", "RZ_ADMIN_PASSWORD", "PORT"}
    missing = sorted(name for name in read - internal if name not in text)
    assert not missing, f"undocumented in .env.example: {missing}"
