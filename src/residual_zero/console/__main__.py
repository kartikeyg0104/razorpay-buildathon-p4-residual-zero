"""Serve the ops console.

Local default is unchanged: loopback, port 8765, no authentication, the committed dev
corpus. A deployment overrides host, port and mode through the environment, and
:func:`validate_for_startup` refuses to serve financial data over a public origin without
authentication and a session secret — so the dangerous configuration cannot boot quietly.
"""

from __future__ import annotations

import os
import socket
import sys

from residual_zero.runtime.envfile import load_env_file

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class BindAddressError(RuntimeError):
    """RZ_HOST is not an address this process can bind. Names the variable and the value."""


def _host() -> str:
    """Bind address. ``0.0.0.0`` is required inside a container, so it is configurable.

    Validated, because the failure mode otherwise is genuinely undiagnosable. RZ_HOST is a
    *bind address*, but on a hosting platform whose UI offers variables like
    ``RAILWAY_PUBLIC_DOMAIN`` it is natural to set it to the service's public hostname.
    uvicorn then hands that name to ``getaddrinfo``, which fails with a bare
    ``[Errno -2] Name or service not known`` - no variable named, no value shown, logged
    *after* "Application startup complete" so the app looks like it booted fine. Observed
    on Railway; reproduced exactly with RZ_HOST set to both a ``.railway.internal`` name
    and an ``https://`` URL.
    """
    raw = (os.environ.get("RZ_HOST") or DEFAULT_HOST).strip() or DEFAULT_HOST
    # `[::]` is how RFC 3986 writes an IPv6 host inside a URL, and it is what Railway's own
    # guidance shows for "listen on all interfaces". getaddrinfo does not accept the
    # brackets, so uvicorn turned a correct-looking value into
    # `[Errno -2] Name or service not known` and the container crash-looped. Stripping them
    # is not a guess: bracket notation has exactly one meaning, and `[::]` is the address
    # `::`. Observed on Railway with RZ_HOST='[::]'.
    if len(raw) > 2 and raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    if "://" in raw:
        raise BindAddressError(
            f"RZ_HOST={raw!r} looks like a URL. RZ_HOST is the address the server binds "
            f"to, not the address people reach it on. Inside a container it must be "
            f"'0.0.0.0'. Set the public URL in RZ_PUBLIC_ORIGIN instead."
        )
    # Try an actual bind on an ephemeral port. Resolution alone is not enough: a public
    # hostname like `app-production.up.railway.app` resolves perfectly well and is still
    # unbindable, because the address belongs to a load balancer and not to any interface
    # on this container. That case fails later with EADDRNOTAVAIL rather than gaierror, so
    # checking only getaddrinfo would let the more confusing of the two mistakes through.
    try:
        family = socket.AF_INET6 if ":" in raw else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.bind((raw, 0))
    except OSError as exc:
        raise BindAddressError(
            f"RZ_HOST={raw!r} is not an address this container can bind to ({exc}). "
            f"RZ_HOST is the bind address, not the address people reach the service on. "
            f"Inside a container it must be '0.0.0.0'; leave it unset to use the image "
            f"default. The service's public URL belongs in RZ_PUBLIC_ORIGIN."
        ) from None
    return raw


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
        _host()  # validate the bind address here, not inside uvicorn's socket setup
    except (ConfigError, BindAddressError) as exc:
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
