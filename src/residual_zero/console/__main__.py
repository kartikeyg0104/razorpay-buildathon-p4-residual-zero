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


# Every "listen on all interfaces" guide writes the IPv6 wildcard this way, so treat both
# spellings as the same request.
WILDCARD_V6 = frozenset({"::", "0:0:0:0:0:0:0:0"})


def _listen_socket(host: str, port: int) -> socket.socket | None:
    """A dual-stack listening socket for the IPv6 wildcard, else ``None`` to let uvicorn bind.

    ``asyncio.BaseEventLoop.create_server`` sets ``IPV6_V6ONLY`` on every ``AF_INET6``
    socket it binds. So ``RZ_HOST=::`` — the value that reads as "all interfaces" and that
    platform docs hand you — listens on IPv6 *only* and answers an IPv4 connection with
    ECONNREFUSED. That failure is invisible from inside the process: startup completes,
    uvicorn logs ``Uvicorn running on http://[::]:8080``, and nothing ever arrives.
    Observed on Railway, where the health probe connects over IPv4: the deploy was killed
    on healthcheck timeout with not one request line in the log.

    Binding here, before uvicorn, is the only place the option can be cleared. Wildcard
    only — a specific address means the operator picked a family on purpose.
    """
    if host not in WILDCARD_V6:
        return None
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            # Some kernels refuse to serve both families on one socket (OpenBSD forbids it
            # outright). Bind IPv6-only rather than fail to start; the operator can set
            # RZ_HOST=0.0.0.0 if IPv4 is the family that matters there.
            pass
        # Not listen() — asyncio calls that itself with the configured backlog.
        sock.bind((host, port))
    except BaseException:
        sock.close()
        raise
    return sock


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

    host, port = _host(), _port()
    sock = _listen_socket(host, port)
    obs.event(
        "console.starting",
        host=host,
        port=port,
        dual_stack=sock is not None,
        **config.redacted_summary(),
    )
    settings = uvicorn.Config(
        "residual_zero.console.app:app",
        host=host,
        port=port,
        log_level=(os.environ.get("RZ_LOG_LEVEL") or "info").lower(),
        reload=False,
        # Behind a TLS-terminating proxy, uvicorn must read X-Forwarded-* to know the
        # request was HTTPS and who the client was. Off when no proxy is declared, so a
        # client cannot forge its own scheme or address.
        proxy_headers=config.trust_proxy,
        forwarded_allow_ips="*" if config.trust_proxy else None,
    )
    # Config/Server rather than uvicorn.run() only so a pre-bound socket can be handed
    # over; every other argument is unchanged. sockets=None is uvicorn's own default path.
    uvicorn.Server(settings).run(sockets=[sock] if sock else None)


if __name__ == "__main__":
    main()
