"""Deployment configuration, and the checks that refuse to start without it.

The dangerous failure for a publicly deployed finance console is not a crash — it is
booting *successfully* with authentication switched off. So the two settings that decide
whether the deployment is safe are read here, together, and
:func:`validate_for_startup` refuses to return when production is asked for without them.

Everything is read from the environment. No secret has a default, and no secret is ever
rendered: :func:`redacted_summary` is the only printable view and it reports presence, not
value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class Env(str, Enum):
    LOCAL = "local"
    PRODUCTION = "production"


class AuthMode(str, Enum):
    OFF = "off"
    """Single-tenant local mode. No login; the desk serves the committed dev corpus.

    This is the historical behaviour and the default, which is what keeps the CLI, the eval
    harness, ``make demo`` and the test suite working unchanged. It is refused in
    production.
    """

    REQUIRED = "required"
    """Every route except the login pages and the liveness probe needs a credential."""


class ConfigError(RuntimeError):
    """The process must not start. Message names the variable, never its value."""


ENV_VAR = "RZ_ENV"
AUTH_VAR = "RZ_AUTH_MODE"
SECRET_VAR = "RZ_SESSION_SECRET"
ORIGIN_VAR = "RZ_PUBLIC_ORIGIN"
# Hosting platforms that publish the service's own address. Used only when
# RZ_PUBLIC_ORIGIN is unset, because the URL is not knowable before the service exists.
# Render gives a full URL; Railway gives a bare hostname, so the scheme is added.
PLATFORM_ORIGIN_VAR = "RENDER_EXTERNAL_URL"
PLATFORM_ORIGIN_VARS: tuple[tuple[str, str], ...] = (
    ("RENDER_EXTERNAL_URL", ""),          # already https://host
    ("RAILWAY_PUBLIC_DOMAIN", "https://"),  # bare host, e.g. app-production.up.railway.app
)
EXTRA_ORIGINS_VAR = "RZ_ALLOWED_ORIGINS"
EXT_IDS_VAR = "RZ_EXTENSION_IDS"
TRUST_PROXY_VAR = "RZ_TRUST_PROXY"
SIGNUP_VAR = "RZ_ALLOW_SIGNUP"

# Minimum length for the session secret. Short enough to type, long enough that a guessed
# value is not a realistic attack.
MIN_SECRET_LEN = 32


@dataclass(frozen=True)
class AppConfig:
    env: Env
    auth_mode: AuthMode
    public_origin: str
    allowed_origins: tuple[str, ...] = ()
    extension_ids: tuple[str, ...] = ()
    trust_proxy: bool = False
    allow_signup: bool = True
    session_secret_present: bool = False
    _errors: tuple[str, ...] = field(default=(), repr=False)

    @property
    def is_production(self) -> bool:
        return self.env is Env.PRODUCTION

    @property
    def auth_required(self) -> bool:
        return self.auth_mode is AuthMode.REQUIRED

    @property
    def https_only(self) -> bool:
        """Whether cookies get ``Secure`` and HSTS is sent.

        Tied to the public origin's scheme rather than to ``RZ_ENV``, so a production
        deployment that has not been given an ``https://`` origin does not silently mark
        cookies ``Secure`` and lock itself out — it fails the startup check instead.
        """
        return self.public_origin.startswith("https://")

    def write_origins(self) -> frozenset[str]:
        """Origins allowed to make a cookie-authenticated write. See ``console.security``."""
        origins = {o for o in (self.public_origin, *self.allowed_origins) if o}
        if not self.auth_required:
            # Local single-tenant mode keeps the historical loopback allowlist.
            origins |= {"http://127.0.0.1:8765", "http://localhost:8765"}
        return frozenset(origins)

    def cors_origins(self) -> tuple[str, ...]:
        """Browser origins allowed to read a response. Extensions are listed explicitly."""
        out = [o for o in (self.public_origin, *self.allowed_origins) if o]
        out += [f"chrome-extension://{i}" for i in self.extension_ids]
        return tuple(dict.fromkeys(out))

    def redacted_summary(self) -> dict[str, object]:
        """Safe to log and safe to serve. Reports presence of secrets, never their value."""
        from residual_zero.storage.config import storage_config

        cfg = storage_config()
        return {
            "env": self.env.value,
            "auth_mode": self.auth_mode.value,
            "public_origin": self.public_origin,
            "allowed_origins": list(self.allowed_origins),
            "extension_ids": list(self.extension_ids),
            "trust_proxy": self.trust_proxy,
            "allow_signup": self.allow_signup,
            "https_only": self.https_only,
            "session_secret_present": self.session_secret_present,
            "database_backend": cfg.backend.value,
            "database": cfg.safe_dsn(),
        }


def _split_csv(raw: str | None) -> tuple[str, ...]:
    return tuple(part.strip().rstrip("/") for part in (raw or "").split(",") if part.strip())


def _flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().casefold()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def load_config() -> AppConfig:
    """Read configuration from the environment. Collects problems; does not raise.

    Separating "read" from "refuse" lets ``/readyz`` and the startup log report *every*
    missing variable at once instead of one per restart.
    """
    raw_env = (os.environ.get(ENV_VAR) or "local").strip().casefold()
    env = Env.PRODUCTION if raw_env in {"production", "prod"} else Env.LOCAL

    raw_auth = (os.environ.get(AUTH_VAR) or "").strip().casefold()
    if raw_auth in {"required", "on", "1", "true"}:
        auth_mode = AuthMode.REQUIRED
    elif raw_auth in {"off", "0", "false", ""}:
        auth_mode = AuthMode.OFF
    else:
        auth_mode = AuthMode.OFF

    secret = (os.environ.get(SECRET_VAR) or "").strip()
    origin = (os.environ.get(ORIGIN_VAR) or "").strip().rstrip("/")
    if not origin:
        # A platform that publishes the service's own address can supply it: the URL is not
        # knowable before the service exists, so without this the first deploy could not
        # satisfy the production origin check no matter what the operator typed. An
        # explicit RZ_PUBLIC_ORIGIN still wins, which is what a custom domain needs.
        for name, scheme in PLATFORM_ORIGIN_VARS:
            supplied = (os.environ.get(name) or "").strip().rstrip("/")
            if supplied:
                origin = supplied if "://" in supplied else scheme + supplied
                break
    if not origin and env is Env.LOCAL:
        origin = "http://127.0.0.1:8765"

    errors: list[str] = []
    if env is Env.PRODUCTION:
        if auth_mode is not AuthMode.REQUIRED:
            errors.append(
                f"{ENV_VAR}=production requires {AUTH_VAR}=required; refusing to serve "
                "financial data without authentication"
            )
        if len(secret) < MIN_SECRET_LEN:
            errors.append(
                f"{SECRET_VAR} must be set to at least {MIN_SECRET_LEN} characters in production"
            )
        if not origin:
            errors.append(f"{ORIGIN_VAR} must name the public HTTPS origin in production")
        elif not origin.startswith("https://"):
            errors.append(
                f"{ORIGIN_VAR} must be https:// in production (got the scheme "
                f"{origin.partition('://')[0]!r})"
            )
        from residual_zero.storage.config import URL_ENV, storage_config

        try:
            if not storage_config().is_postgres:
                errors.append(
                    f"{URL_ENV} must name a PostgreSQL database in production; "
                    "SQLite is a development backend"
                )
        except Exception as exc:  # unparseable URL
            errors.append(str(exc))

    return AppConfig(
        env=env,
        auth_mode=auth_mode,
        public_origin=origin,
        allowed_origins=_split_csv(os.environ.get(EXTRA_ORIGINS_VAR)),
        extension_ids=_split_csv(os.environ.get(EXT_IDS_VAR)),
        trust_proxy=_flag(TRUST_PROXY_VAR, env is Env.PRODUCTION),
        allow_signup=_flag(SIGNUP_VAR, True),
        session_secret_present=bool(secret),
        _errors=tuple(errors),
    )


def config_errors(config: AppConfig | None = None) -> tuple[str, ...]:
    return (config or load_config())._errors


def enforce_import_time(config: AppConfig | None = None) -> None:
    """Refuse to *import* a production app that is misconfigured.

    :func:`validate_for_startup` runs in ``residual_zero.console.__main__``, which only
    executes for ``python -m residual_zero.console``. A process started as
    ``uvicorn residual_zero.console.app:app`` - the default on most hosting platforms, and
    what a Procfile or a `CMD` override typically uses - imports the module and never runs
    that check. With ``RZ_ENV=production`` and no ``RZ_DATABASE_URL`` the app then came up
    happily and served the committed development SQLite ledger as if it were production
    data (verified: 248 audit rows).

    A silent downgrade of the authoritative store is the worst failure this deployment can
    have, so the check moves to import time, where no start command can route around it.
    Local mode is unaffected: with ``RZ_ENV`` unset or ``local`` there are no required
    settings and this returns immediately.
    """
    resolved = config or load_config()
    if not resolved.is_production:
        return
    problems = resolved._errors
    if problems:
        raise ConfigError(
            "refusing to serve: RZ_ENV=production but the deployment is misconfigured:\n  - "
            + "\n  - ".join(problems)
        )


def validate_for_startup(config: AppConfig | None = None) -> AppConfig:
    """Return the config, or raise :class:`ConfigError` listing everything wrong with it."""
    resolved = config or load_config()
    problems = resolved._errors
    if problems:
        raise ConfigError(
            "refusing to start:\n  - " + "\n  - ".join(problems)
        )
    return resolved
