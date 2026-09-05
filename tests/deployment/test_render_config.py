"""The Render blueprint and the container's port contract.

Four faults in this area only appeared when the production image was actually built and
run - every unit test passed straight through them. These tests encode each one, so the
next person to edit the Dockerfile or the blueprint finds out from pytest rather than from
a deploy that comes up "healthy" on the wrong port.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

RENDER_YAML = Path("render.yaml")
DOCKERFILE = Path("Dockerfile")


@pytest.fixture(scope="module")
def service() -> dict:
    spec = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    assert spec["services"], "render.yaml declares no service"
    return spec["services"][0]


@pytest.fixture(scope="module")
def env_vars(service) -> dict:
    return {e["key"]: e for e in service["envVars"]}


# ---------------------------------------------------------------- blueprint shape


def test_the_blueprint_is_a_docker_web_service(service):
    """Docker, not the Python runtime: production needs the `postgres` extra.

    A buildpack running a bare `pip install .` would omit psycopg, and the app would then
    refuse to start - correctly, since production rejects a non-PostgreSQL database, but
    for a reason that reads like a configuration bug.
    """
    assert service["type"] == "web"
    assert service["runtime"] == "docker"
    assert service["dockerfilePath"] == "./Dockerfile"
    assert Path(service["dockerfilePath"]).is_file()
    assert service["branch"] == "main"


def test_the_service_is_co_located_with_the_database(service):
    """REGRESSION: distance is the dominant cost in this application.

    Measured on the production image: one fresh connection to Neon costs 2550 ms from
    ~12,000 km away and 2.1 ms on the same host, and a credit page opens six connections -
    24,021 ms versus 94 ms for byte-identical code. Neon's endpoint is us-east-2, so the
    service must be in Render's `ohio`.
    """
    assert service["region"] == "ohio", (
        "the service must sit in the same region as the Neon database (us-east-2)"
    )


def test_the_blueprint_declares_no_database(service):
    """Neon is the production store. A Render database would be a second, empty one."""
    spec = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    assert "databases" not in spec, "the production database is Neon and is external"


def test_the_health_check_points_at_a_real_public_route(service):
    """A health check on a route that needs a credential can never return 200."""
    from residual_zero.console.security import HEALTH_PATHS, is_public

    path = service["healthCheckPath"]
    assert path == "/healthz"
    assert is_public(path), "the health check path must not require authentication"
    assert path in HEALTH_PATHS, "the health check path must be exempt from the HTTPS redirect"


def test_the_health_endpoint_touches_nothing_expensive():
    """It must not open a database connection, call the provider, or read financial state."""
    src = Path("src/residual_zero/console/app.py").read_text(encoding="utf-8")
    body = src[src.index("def healthz("):]
    body = body[: body.index("\n@app.get")]
    for forbidden in ("_db(", "_split(", "_overlay(", "provider", "load_config"):
        assert forbidden not in body, f"/healthz touches {forbidden}"


# ---------------------------------------------------------------- the port contract


def test_the_dockerfile_does_not_pin_rz_port():
    """REGRESSION: a baked RZ_PORT makes the container ignore the platform's port.

    `_port()` prefers RZ_PORT over PORT. With RZ_PORT=8765 in the image the container
    bound 8765 while Render's router probed $PORT - the health check fails while the
    process looks perfectly healthy.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert not re.search(r"^\s*(ENV\s+)?RZ_PORT\s*=", code, re.M), (
        "Dockerfile must not set RZ_PORT; PORT from the platform has to win"
    )


def test_the_container_healthcheck_honours_port():
    text = DOCKERFILE.read_text(encoding="utf-8")
    healthcheck = text[text.index("HEALTHCHECK"):]
    assert "PORT" in healthcheck, "the container healthcheck must use the assigned port"
    assert "/healthz" in healthcheck


def test_port_resolution_prefers_the_platform_port_when_rz_port_is_unset(monkeypatch):
    from residual_zero.console.__main__ import _host, _port

    monkeypatch.delenv("RZ_PORT", raising=False)
    monkeypatch.setenv("PORT", "10000")
    assert _port() == 10000, "the platform's PORT must be honoured"
    monkeypatch.setenv("RZ_HOST", "0.0.0.0")
    assert _host() == "0.0.0.0"
    # And an explicit RZ_PORT still wins, for anyone who needs to pin it.
    monkeypatch.setenv("RZ_PORT", "9999")
    assert _port() == 9999


def test_the_start_command_runs_the_guarded_entry_point():
    """CMD must go through __main__, which validates configuration before serving.

    Both guards fire either way - the import-time check covers a raw uvicorn command too -
    but the entry point is the one that also bootstraps identity and configures logging.
    """
    text = DOCKERFILE.read_text(encoding="utf-8")
    cmd = [l for l in text.splitlines() if l.startswith("CMD")][-1]
    assert "residual_zero.console" in cmd
    assert "-m" in cmd


# ---------------------------------------------------------------- environment


def test_every_variable_production_requires_is_declared(env_vars):
    """If the blueprint omits one, the first deploy fails the startup check."""
    for key in ("RZ_ENV", "RZ_AUTH_MODE", "RZ_SESSION_SECRET", "RZ_DATABASE_URL"):
        assert key in env_vars, f"{key} is required in production but not in render.yaml"
    assert env_vars["RZ_ENV"]["value"] == "production"
    assert env_vars["RZ_AUTH_MODE"]["value"] == "required"
    # Render terminates TLS; without this the app cannot tell it is on HTTPS.
    assert env_vars["RZ_TRUST_PROXY"]["value"] == "1"
    # A container must bind all interfaces.
    assert env_vars["RZ_HOST"]["value"] == "0.0.0.0"


def test_the_public_origin_is_not_hardcoded(env_vars):
    """The service URL is not knowable before the service exists.

    RZ_PUBLIC_ORIGIN falls back to RENDER_EXTERNAL_URL, which the platform sets to this
    service's own https URL, so the first deploy of a new service can satisfy the
    production origin check without anybody guessing a hostname.
    """
    assert "RZ_PUBLIC_ORIGIN" not in env_vars
    from residual_zero.appconfig import PLATFORM_ORIGIN_VAR

    assert PLATFORM_ORIGIN_VAR == "RENDER_EXTERNAL_URL"


def test_rz_port_is_not_declared_in_the_blueprint_either(env_vars):
    assert "RZ_PORT" not in env_vars, "declaring RZ_PORT would override the platform's PORT"


def test_no_secret_value_appears_in_the_blueprint(env_vars):
    """Secrets are prompted for or generated; none is written down here."""
    text = RENDER_YAML.read_text(encoding="utf-8")
    for pattern in (r"nvapi-[A-Za-z0-9_-]{10,}", r"npg_[A-Za-z0-9]{8,}",
                    r"postgres(ql)?://[^\s:@/]+:[^\s@/]{4,}@", r"sk-[A-Za-z0-9]{16,}"):
        assert not re.search(pattern, text), f"render.yaml contains something matching {pattern}"
    assert env_vars["RZ_DATABASE_URL"].get("sync") is False
    assert env_vars["NVIDIA_API_KEY"].get("sync") is False
    assert env_vars["RZ_SESSION_SECRET"].get("generateValue") is True
    assert "value" not in env_vars["RZ_DATABASE_URL"]
    assert "value" not in env_vars["NVIDIA_API_KEY"]


def test_the_provider_is_nvidia_and_groq_is_absent(env_vars):
    assert env_vars["AI_PROVIDER"]["value"] == "nvidia"
    assert "groq" not in RENDER_YAML.read_text(encoding="utf-8").casefold()


def test_the_ai_budget_is_not_widened_to_hide_latency(env_vars):
    """A measured 61 s provider call is reported, not papered over with a bigger budget."""
    assert int(env_vars["AI_TIMEOUT_S"]["value"]) <= 30
    assert int(env_vars["AI_TOTAL_BUDGET_S"]["value"]) <= 40
