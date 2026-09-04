"""Serve the ops console.

Local default is unchanged: loopback, port 8765, no authentication, the committed dev
corpus. A deployment overrides host, port and mode through the environment, and
:func:`validate_for_startup` refuses to serve financial data over a public origin without
authentication and a session secret — so the dangerous configuration cannot boot quietly.
"""

from __future__ import annotations

import os
import sys

from residual_zero.runtime.envfile import load_env_file

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _host() -> str:
    """Bind address. ``0.0.0.0`` is required inside a container, so it is configurable."""
    return (os.environ.get("RZ_HOST") or DEFAULT_HOST).strip() or DEFAULT_HOST


def _port() -> int:
    """Port. ``PORT`` is what every PaaS injects; ``RZ_PORT`` overrides it explicitly."""
    for name in ("RZ_PORT", "PORT"):
        raw = (os.environ.get(name) or "").strip()
        if raw.isdigit() and 0 < int(raw) < 65536:
            return int(raw)
    return DEFAULT_PORT


def main() -> None:
    import uvicorn

    load_env_file()

    from residual_zero import obs
    from residual_zero.appconfig import ConfigError, validate_for_startup

    obs.configure_logging()
    try:
        config = validate_for_startup()
    except ConfigError as exc:
        # Refuse rather than serve. Printed to stderr as plain text because a config error
        # before logging is configured should still be readable in a platform's boot log.
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None

    from residual_zero.storage.engine import bootstrap_shared

    if config.auth_required:
        # Identity must exist before the first login attempt. Idempotent.
        bootstrap_shared()

    obs.event("console.starting", host=_host(), port=_port(), **config.redacted_summary())
    uvicorn.run(
        "residual_zero.console.app:app",
        host=_host(),
        port=_port(),
        log_level=(os.environ.get("RZ_LOG_LEVEL") or "info").lower(),
        reload=False,
        # Behind a TLS-terminating proxy, uvicorn must read X-Forwarded-* to know the
        # request was HTTPS and who the client was. Off when no proxy is declared, so a
        # client cannot forge its own scheme or address.
        proxy_headers=config.trust_proxy,
        forwarded_allow_ips="*" if config.trust_proxy else None,
    )


if __name__ == "__main__":
    main()
