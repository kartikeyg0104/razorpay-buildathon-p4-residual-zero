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


# Anything on these lists makes a blueprint refuse to apply without billing details.
PAID_ONLY_KEYS = frozenset({
    "disk",                      # persistent disks are paid
    "numInstances", "scaling",   # scaling is paid
    "preDeployCommand",          # paid plans only
    "maxShutdownDelaySeconds",   # paid plans only
})
PAID_SERVICE_TYPES = frozenset({"pserv", "worker", "cron", "redis", "keyvalue"})
PAID_PLANS = frozenset({
    "starter", "standard", "standard plus",
    "pro", "pro plus", "pro max", "pro ultra",
})


def test_the_service_runs_on_the_free_plan(service):
    """REGRESSION: `plan: starter` made Render demand a card before it would deploy.

    That plan was chosen on an unmeasured guess about ortools/scipy/pandas memory. Measured
    under a hard 512 MiB limit the service peaks at 103.6 MiB - about 20% - after all 19
    surfaces, five close-pack and journal builds, an AI investigation and five
    solver-backed proof pages, with no OOM kill. Those libraries are never even mapped into
    the serving process.
    """
    assert service.get("plan") == "free", (
        "a non-free plan makes the blueprint require payment details"
    )
    assert service["plan"] not in PAID_PLANS


def test_no_paid_only_resource_is_declared(service):
    """Every remaining reason a blueprint can demand billing details."""
    spec = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    assert "databases" not in spec, "a Render PostgreSQL instance is a paid resource"
    present = PAID_ONLY_KEYS & set(service)
    assert not present, f"paid-only settings in the blueprint: {sorted(present)}"
    for s in spec["services"]:
        assert s["type"] not in PAID_SERVICE_TYPES, (
            f"service type {s['type']!r} is not available on the free plan"
        )
    # One free web service; a second would exceed what a card-less account can run.
    assert len(spec["services"]) == 1


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


# ---------------------------------------------------------------- Railway

RAILWAY_JSON = Path("railway.json")


def test_railway_uses_the_same_dockerfile_and_health_path():
    """Railway is the deployment platform; the blueprint must agree with it."""
    import json

    cfg = json.loads(RAILWAY_JSON.read_text(encoding="utf-8"))
    assert cfg["build"]["builder"] == "DOCKERFILE"
    assert cfg["build"]["dockerfilePath"] == "Dockerfile"
    assert cfg["deploy"]["healthcheckPath"] == "/healthz"
    # Same path the Render blueprint uses, and the one exempted from the HTTPS redirect.
    from residual_zero.console.security import HEALTH_PATHS

    assert cfg["deploy"]["healthcheckPath"] in HEALTH_PATHS


def test_railway_config_declares_no_secret():
    text = RAILWAY_JSON.read_text(encoding="utf-8")
    for pattern in (r"nvapi-", r"npg_", r"postgres(ql)?://"):
        assert not re.search(pattern, text), f"railway.json contains {pattern}"


@pytest.mark.parametrize("bad", [
    "razorpay-buildathon-p4-residual-zero.railway.internal",
    "https://residual-zero-production.up.railway.app",
    "residual-zero-production.up.railway.app",
    "http://example.invalid",
])
def test_a_hostname_in_rz_host_is_refused_with_a_useful_message(monkeypatch, bad):
    """REGRESSION: this crashed Railway with a bare `[Errno -2] Name or service not known`.

    RZ_HOST is a bind address. Set to a public hostname, uvicorn passed it to getaddrinfo,
    which failed *after* "Application startup complete" - so the log said the app had
    started, then died, naming neither the variable nor the value. Reproduced exactly in
    the built image (exit 3, no "Uvicorn running on" line).
    """
    from residual_zero.console.__main__ import BindAddressError, _host

    monkeypatch.setenv("RZ_HOST", bad)
    with pytest.raises(BindAddressError) as exc:
        _host()
    message = str(exc.value)
    assert "RZ_HOST" in message, "the error must name the variable"
    assert bad in message, "the error must show the offending value"
    assert "0.0.0.0" in message, "the error must say what the value should be"
    assert "RZ_PUBLIC_ORIGIN" in message, "it must point at the right variable for a URL"


@pytest.mark.parametrize("good", ["0.0.0.0", "127.0.0.1", "localhost", "::"])
def test_a_real_bind_address_is_accepted(monkeypatch, good):
    from residual_zero.console.__main__ import _host

    monkeypatch.setenv("RZ_HOST", good)
    assert _host() == good


def test_the_public_origin_falls_back_to_the_platform_domain(monkeypatch):
    """Railway publishes a bare hostname; Render publishes a full URL. Both work.

    Deliberately no importlib.reload here. `load_config()` reads the environment on every
    call, so a reload buys nothing - and it swaps out the AuthMode/Env enum members, after
    which an `is` comparison in another test module compares a pre-reload member against a
    post-reload one and silently inverts an authorisation check. That cost a debugging pass
    once already.
    """
    from residual_zero.appconfig import load_config

    for k in ("RZ_PUBLIC_ORIGIN", "RENDER_EXTERNAL_URL", "RAILWAY_PUBLIC_DOMAIN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("RZ_ENV", "production")
    monkeypatch.setenv("RZ_AUTH_MODE", "required")
    monkeypatch.setenv("RZ_SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("RZ_DATABASE_URL", "postgresql://u:p@h/db")

    # Nothing published: production refuses, naming the variable.
    assert any("RZ_PUBLIC_ORIGIN" in e for e in load_config()._errors)

    # Railway publishes a bare hostname; the scheme is added.
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "app-production.up.railway.app")
    config = load_config()
    assert config.public_origin == "https://app-production.up.railway.app"
    assert config.https_only is True
    assert not config._errors, "the platform domain must satisfy the production origin check"

    # Render publishes a full URL and takes precedence in the lookup order.
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://x.onrender.com")
    assert load_config().public_origin == "https://x.onrender.com"

    # An explicit value always wins, which is what a custom domain needs.
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "https://custom.example")
    assert load_config().public_origin == "https://custom.example"
