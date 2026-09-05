"""Authentication, authorisation, CSRF and security headers for the ops console.

**Why middleware and not a dependency on each route.** The console exposes roughly fifty
routes across three modules. A per-route ``Depends(require_user)`` would have to be added
fifty times and would silently fail open the first time somebody added route fifty-one.
This middleware inverts that: every path needs a credential unless it is on a short,
explicit public list, so a new route is protected by default and forgetting is the safe
direction.

**What a credential is.** Either a session cookie (the browser) or a
``Authorization: Bearer rz_pat_...`` personal access token (the extension, the CLI, MCP).
Both resolve to a :class:`~residual_zero.identity.store.Principal`, and resolving one binds
that principal's organisation for the rest of the request — which is what makes the desk's
data accessors return that organisation's rows and nothing else.

**What a credential is not.** It is never authority to clear. No role grants ``clear``;
``CLEARED`` requires ``UNIQUE`` + a zero-paise residual + a ``FULL`` pool + a derived
threshold, decided by the solver and the verifier. Authentication decides *whether you may
look*, never *what the answer is*.
"""

from __future__ import annotations

import re
import time
from typing import Awaitable, Callable

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from residual_zero import obs
from residual_zero.appconfig import AppConfig, load_config
from residual_zero.identity.store import SESSION_COOKIE, Principal
from residual_zero.tenancy import use_tenant

# ---------------------------------------------------------------- public surface

# Paths reachable with no credential. Deliberately tiny, and deliberately containing
# nothing financial: `/healthz` is a liveness probe that reports no counts, no amounts and
# no organisation. (`/api/health`, which does report counts, stays authenticated.)
PUBLIC_EXACT = frozenset({
    "/login", "/signup", "/logout", "/healthz", "/readyz", "/favicon.ico", "/robots.txt",
})
PUBLIC_PREFIXES = ("/static/",)

# Reachable over plain HTTP as well as HTTPS: a platform health check has no
# X-Forwarded-Proto and must receive 200, not a redirect to the public origin.
HEALTH_PATHS = frozenset({"/healthz", "/readyz"})

# Permission required per route. Anything not listed needs `read_financial`, so a new route
# is a financial read until somebody says otherwise.
#
# `review_exception` appears exactly twice: the two routes where a human records a decision.
# Neither writes CLEARED — the resolution vocabulary refuses the word (ops_pack) and the
# storage CHECK constraint refuses the value (migrations/org/0001_financial.sql).
ROUTE_PERMISSIONS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("POST", re.compile(r"^/exceptions/[^/]+/resolve$"), "review_exception"),
    ("POST", re.compile(r"^/exceptions/[^/]+/work$"), "review_exception"),
    ("GET", re.compile(r"^/journal\.csv$"), "export"),
    ("GET", re.compile(r"^/journal\.tally$"), "export"),
    ("GET", re.compile(r"^/exceptions\.csv$"), "export"),
    ("GET", re.compile(r"^/close\.zip$"), "export"),
    ("GET", re.compile(r"^/close\.md$"), "export"),
    ("GET", re.compile(r"^/standup\.md$"), "export"),
    ("GET", re.compile(r"^/extension\.zip$"), "export"),
    ("GET", re.compile(r"^/api/config$"), "administer"),
)
DEFAULT_PERMISSION = "read_financial"

# Methods that change state. Only these are subject to the origin check.
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_public(path: str) -> bool:
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES)


def required_permission(method: str, path: str) -> str:
    for want_method, pattern, permission in ROUTE_PERMISSIONS:
        if method == want_method and pattern.match(path):
            return permission
    return DEFAULT_PERMISSION


# ---------------------------------------------------------------- credential resolution


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if header[:7].casefold() == "bearer ":
        return header[7:].strip()
    return ""


def resolve_principal(request: Request) -> Principal | None:
    """Resolve a credential to a principal, or ``None``.

    A bearer token is tried first so a browser that happens to hold a stale cookie can
    still drive the API with an explicit token.
    """
    from residual_zero.identity.store import IdentityStore

    store = IdentityStore()
    token = bearer_token(request)
    if token:
        found = store.resolve_api_token(token)
        if found is not None:
            return found
        # An explicit token that does not resolve must not silently fall back to a cookie.
        return None
    cookie = request.cookies.get(SESSION_COOKIE) or ""
    return store.resolve_session(cookie) if cookie else None


def wants_json(request: Request) -> bool:
    path = request.url.path
    if path.startswith(("/api/", "/mcp")) or path.endswith((".json", ".csv", ".zip")):
        return True
    accept = request.headers.get("accept") or ""
    return "application/json" in accept and "text/html" not in accept


# ---------------------------------------------------------------- CSRF / origin


def origin_allowed(origin: str | None, config: AppConfig, principal: Principal | None) -> bool:
    """Whether a state-changing request may proceed, given who is asking.

    A **bearer token** is not a CSRF vector: a browser will not attach it to a cross-site
    request on its own, so no origin is required and none is checked. A **cookie** is
    attached automatically, so a cookie-authenticated write must come from an origin this
    deployment owns.

    The historical local-mode rule — "no Origin header means a non-browser client such as
    curl or the test suite, allow it" — is kept only while authentication is off. Under
    ``RZ_AUTH_MODE=required`` a missing Origin on a *cookie* write is refused, because in a
    public deployment "not a browser" is no longer a safe inference to draw from a header
    the caller controls.
    """
    if principal is not None and principal.is_bearer:
        return True
    allowed = config.write_origins()
    if origin is None:
        return not config.auth_required
    return origin.rstrip("/") in allowed


# ---------------------------------------------------------------- middleware


# Content-Security-Policy for the console.
#
# `script-src 'self'` is the load-bearing clause: no third-party script, no inline script,
# and no `eval`. So even if a narration string escaped Jinja's autoescaping, it could not
# execute. `'unsafe-inline'` is scoped to style-src only, because the templates carry
# inline style attributes; it does not weaken script execution.
#
# fonts.googleapis.com / fonts.gstatic.com are here because `templates/base.html` loads IBM
# Plex from Google Fonts. Omitting them blocked the stylesheet and changed how every page
# looked (caught by the browser E2E, which asserts a clean console). Self-hosting the two
# font files would remove the third-party request entirely — worth doing, and noted as such
# in docs/DEPLOYMENT.md — but silently restyling the console was not an acceptable way to
# tighten a header.
CSP = "; ".join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))


class SecurityHeadersMiddleware:
    """Response headers that a public deployment needs and a local desk does no harm with.

    ``Strict-Transport-Security`` is sent only when the public origin is HTTPS: pinning
    HSTS onto a plain-HTTP local desk would make ``127.0.0.1`` unreachable in that browser
    afterwards.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        config = load_config()

        async def send_with_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("x-content-type-options", "nosniff")
                headers.setdefault("x-frame-options", "DENY")
                headers.setdefault("referrer-policy", "no-referrer")
                headers.setdefault(
                    "permissions-policy", "geolocation=(), microphone=(), camera=()"
                )
                headers.setdefault("content-security-policy", CSP)
                if config.https_only:
                    headers.setdefault(
                        "strict-transport-security", "max-age=31536000; includeSubDomains"
                    )
                headers.setdefault("cache-control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)


class HttpsRedirectMiddleware:
    """Send plain HTTP to HTTPS in production, honouring the proxy's forwarded scheme.

    A platform terminating TLS forwards ``X-Forwarded-Proto: https``; without reading it,
    every request would look like HTTP and redirect forever. The header is only trusted
    when ``RZ_TRUST_PROXY`` says a proxy is actually in front, so a direct-to-app
    deployment cannot be told it is on HTTPS by a client that simply claims so.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        config = load_config()
        if not (config.is_production and config.https_only):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)

        # Health probes are exempt. A platform's health check reaches the container
        # directly on its private network, over plain HTTP and without X-Forwarded-Proto,
        # so redirecting it means the probe sees a 308, never a 200, and the deploy never
        # goes live while the process is in fact healthy (observed against the production
        # image before this exemption). Nothing is weakened: these two endpoints carry no
        # credential and disclose no financial data, which is exactly why they are the
        # probe targets.
        if request.url.path in HEALTH_PATHS:
            await self.app(scope, receive, send)
            return

        scheme = scope.get("scheme", "http")
        if config.trust_proxy:
            forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
            if forwarded:
                scheme = forwarded
        if scheme == "https":
            await self.app(scope, receive, send)
            return
        target = config.public_origin + request.url.path
        if request.url.query:
            target += "?" + request.url.query
        response = RedirectResponse(target, status_code=308)
        await response(scope, receive, send)


class AuthMiddleware:
    """Resolve the credential, bind the organisation, enforce the permission.

    Order matters and is fixed here: authenticate, then bind the tenant, then authorise,
    then run the route. A route body therefore never sees an unauthenticated caller and
    never sees an unbound organisation.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        config = load_config()
        request = Request(scope, receive)
        path = request.url.path
        method = request.method.upper()
        started = time.monotonic_ns()

        if not config.auth_required:
            # Single-tenant local mode: no login, no tenant, historical behaviour.
            scope["rz_principal"] = None
            await self.app(scope, receive, send)
            return

        if is_public(path):
            scope["rz_principal"] = None
            await self.app(scope, receive, send)
            return

        try:
            principal = resolve_principal(request)
        except Exception as exc:
            obs.error("auth.resolve_failed", exc, path=path)
            await _refuse(
                scope, receive, send, request, 503,
                "identity_unavailable", "Sign-in is temporarily unavailable.",
            )
            return

        if principal is None:
            obs.event("auth.rejected", path=path, method=method, reason="no_credential")
            await _refuse(
                scope, receive, send, request, 401,
                "authentication_required", "Sign in to view this organisation's data.",
                login_redirect=True,
            )
            return

        permission = required_permission(method, path)
        if not principal.can(permission):
            obs.event(
                "authz.rejected", path=path, method=method,
                permission=permission, role=principal.role.value, org=principal.org_id,
            )
            await _refuse(
                scope, receive, send, request, 403, "forbidden",
                f"Your role ({principal.role.value}) may not {permission.replace('_', ' ')}.",
            )
            return

        if method in WRITE_METHODS:
            origin = request.headers.get("origin")
            if not origin_allowed(origin, config, principal):
                obs.warn("csrf.rejected", path=path, origin=origin or "", org=principal.org_id)
                await _refuse(
                    scope, receive, send, request, 403, "foreign_origin",
                    "That origin may not write to this desk.",
                )
                return

        scope["rz_principal"] = principal
        # Bind the organisation for the whole request. Every data accessor on the desk
        # reads it from here, so a route cannot accidentally serve another tenant's rows.
        with use_tenant(principal.tenant):
            status_holder: dict[str, int] = {}

            async def send_watching(message: dict) -> None:
                if message["type"] == "http.response.start":
                    status_holder["status"] = int(message["status"])
                await send(message)

            try:
                await self.app(scope, receive, send_watching)
            finally:
                obs.event(
                    "http.request", path=path, method=method,
                    status=status_holder.get("status", 0),
                    org=principal.org_id, user=principal.user_id,
                    credential=principal.credential,
                    duration_ms=(time.monotonic_ns() - started) // 1_000_000,
                )


async def _refuse(
    scope: Scope, receive: Receive, send: Send, request: Request,
    status: int, code: str, message: str, *, login_redirect: bool = False,
) -> None:
    """One refusal shape. JSON for API callers, a redirect or a small page for a browser."""
    if wants_json(request):
        response: Response = JSONResponse(
            {"ok": False, "error": code, "detail": message, "writes_cleared": False},
            status_code=status,
        )
    elif login_redirect:
        target = "/login?next=" + request.url.path
        response = RedirectResponse(target, status_code=303)
    else:
        from html import escape

        response = Response(
            f"<!doctype html><meta charset=utf-8><title>{status}</title>"
            f"<p>{escape(message)}</p><p><a href='/login'>Sign in</a></p>",
            status_code=status,
            media_type="text/html",
        )
    if status == 401:
        response.headers["www-authenticate"] = 'Bearer realm="residual-zero"'
    await response(scope, receive, send)


# ---------------------------------------------------------------- route helpers


def principal_of(request: Request) -> Principal | None:
    """The authenticated caller, or ``None`` in single-tenant local mode."""
    return request.scope.get("rz_principal")


def actor_of(request: Request) -> str:
    """Who to record against a human decision. ``local`` when authentication is off."""
    principal = principal_of(request)
    return principal.email if principal is not None else "local"


def install_error_handlers(app) -> None:
    """Turn an unhandled exception into a generic 500 and a server-side log line.

    Without this, FastAPI's default is to let the exception propagate to the ASGI server,
    which in a debug configuration renders the traceback into the response body. A
    reconciliation traceback names table structure, file paths and query text, none of
    which belongs in a public response.
    """
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> Response:
        principal = principal_of(request)
        obs.error(
            "request.unhandled", exc,
            path=request.url.path, method=request.method,
            org=principal.org_id if principal else "",
        )
        detail = "The desk could not complete that request."
        if wants_json(request):
            return JSONResponse(
                {"ok": False, "error": "internal_error", "detail": detail,
                 "writes_cleared": False},
                status_code=500,
            )
        return Response(
            "<!doctype html><meta charset=utf-8><title>500</title>"
            f"<p>{detail}</p>",
            status_code=500, media_type="text/html",
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if wants_json(request):
            return JSONResponse(
                {"ok": False, "error": "http_error", "detail": str(exc.detail),
                 "writes_cleared": False},
                status_code=exc.status_code,
            )
        from html import escape

        return Response(
            f"<!doctype html><meta charset=utf-8><title>{exc.status_code}</title>"
            f"<p>{escape(str(exc.detail))}</p>",
            status_code=exc.status_code, media_type="text/html",
        )
