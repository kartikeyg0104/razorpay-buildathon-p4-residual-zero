"""Sign in, sign up, sign out, and personal access tokens for the extension.

Deliberately plain: a form, a cookie, and a page that mints a token. There is no email
verification, no password reset and no SSO, because none of that is what makes the
deployment safe — confining a signed-in user to their own organisation is, and that lives
in :mod:`residual_zero.console.security` and :mod:`residual_zero.tenancy`.

The session cookie is ``HttpOnly`` (script cannot read it), ``SameSite=Lax`` (it does not
ride along on a cross-site POST) and ``Secure`` whenever the public origin is HTTPS.
"""

from __future__ import annotations

from html import escape

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from residual_zero import obs
from residual_zero.appconfig import load_config
from residual_zero.console.security import principal_of
from residual_zero.identity.store import (
    SESSION_COOKIE,
    AuthError,
    IdentityStore,
    Role,
    normalise_email,
    session_ttl,
    slug_from_email,
)

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Residual Zero</title>
<link rel="stylesheet" href="/static/app.css">
<style>
 body{{font:14px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif;margin:0;
   background:#0f1117;color:#e6e8ee;display:flex;min-height:100vh;align-items:center;
   justify-content:center}}
 .card{{width:min(24rem,92vw);background:#171a23;border:1px solid #262b38;
   border-radius:10px;padding:1.75rem}}
 h1{{font-size:1.05rem;margin:0 0 .35rem}}
 p.sub{{margin:0 0 1.25rem;color:#8b93a7;font-size:.82rem}}
 label{{display:block;font-size:.75rem;color:#8b93a7;margin:.85rem 0 .3rem;
   text-transform:uppercase;letter-spacing:.04em}}
 input{{width:100%;box-sizing:border-box;padding:.55rem .65rem;border-radius:6px;
   border:1px solid #2d3342;background:#0f1117;color:#e6e8ee;font:inherit}}
 button{{margin-top:1.25rem;width:100%;padding:.6rem;border:0;border-radius:6px;
   background:#3d6fe0;color:#fff;font:inherit;font-weight:600;cursor:pointer}}
 .err{{margin-top:1rem;padding:.55rem .65rem;border-radius:6px;background:#3a1d22;
   border:1px solid #6b2b35;color:#ffb3bd;font-size:.82rem}}
 .alt{{margin-top:1.1rem;font-size:.8rem;color:#8b93a7}}
 a{{color:#7fa4f5}}
 .note{{margin-top:1.25rem;font-size:.74rem;color:#6b7388;line-height:1.5}}
</style></head><body><div class="card">
<h1>{title}</h1><p class="sub">{subtitle}</p>
{error}
{body}
<p class="note">The deterministic reconciliation engine is the only financial authority.
Signing in decides which organisation's records you may read — never what the numbers are.</p>
</div></body></html>
"""


def _page(title: str, subtitle: str, body: str, error: str = "", status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        _PAGE.format(
            title=escape(title), subtitle=escape(subtitle), body=body,
            error=f'<p class="err">{escape(error)}</p>' if error else "",
        ),
        status_code=status,
    )


def _safe_next(raw: str) -> str:
    """Only a path on this site. An absolute URL here would be an open redirect."""
    target = (raw or "/").strip()
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


def _set_session_cookie(response: Response, raw_token: str) -> None:
    config = load_config()
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=int(session_ttl().total_seconds()),
        httponly=True,
        secure=config.https_only,
        samesite="lax",
        path="/",
    )


def mount_auth(app: FastAPI) -> None:
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, next: str = "/", error: str = ""):
        config = load_config()
        if not config.auth_required:
            return RedirectResponse("/", status_code=303)
        target = _safe_next(next)
        signup = (
            f'<p class="alt">No account? <a href="/signup?next={escape(target)}">'
            "Create one</a>.</p>"
            if config.allow_signup
            else '<p class="alt">Accounts are created by an administrator.</p>'
        )
        return _page(
            "Sign in", "Residual Zero reconciliation desk",
            f'<form method="post" action="/login">'
            f'<input type="hidden" name="next" value="{escape(target)}">'
            '<label for="email">Email</label>'
            '<input id="email" name="email" type="email" autocomplete="username" required>'
            '<label for="password">Password</label>'
            '<input id="password" name="password" type="password" '
            'autocomplete="current-password" required>'
            "<button type=submit>Sign in</button></form>" + signup,
            error=error,
        )

    @app.post("/login")
    def login_submit(
        request: Request,
        email: str = Form(""),
        password: str = Form(""),
        next: str = Form("/"),
    ):
        store = IdentityStore()
        try:
            principal = store.authenticate(email, password)
        except AuthError as exc:
            obs.event("auth.login_failed", reason=str(exc))
            try:
                store.log_event("login", "failed", detail=str(exc))
            except Exception:
                pass
            return login_form(request, next=next, error=str(exc))
        raw = store.create_session(principal)
        store.log_event(
            "login", "ok", user_id=principal.user_id, org_id=principal.org_id,
        )
        obs.event("auth.login", org=principal.org_id, user=principal.user_id)
        response = RedirectResponse(_safe_next(next), status_code=303)
        _set_session_cookie(response, raw)
        return response

    @app.get("/signup", response_class=HTMLResponse)
    def signup_form(request: Request, next: str = "/", error: str = ""):
        config = load_config()
        if not config.auth_required:
            return RedirectResponse("/", status_code=303)
        if not config.allow_signup:
            return _page(
                "Sign up closed", "Ask an administrator for an account",
                '<p class="alt"><a href="/login">Back to sign in</a></p>',
                status=403,
            )
        return _page(
            "Create an organisation",
            "A new organisation starts empty. Your records are visible only to your own users.",
            f'<form method="post" action="/signup">'
            f'<input type="hidden" name="next" value="{escape(_safe_next(next))}">'
            '<label for="email">Email</label>'
            '<input id="email" name="email" type="email" autocomplete="username" required>'
            '<label for="org">Organisation name</label>'
            '<input id="org" name="org" type="text" placeholder="acme-payments">'
            '<label for="password">Password (12+ characters)</label>'
            '<input id="password" name="password" type="password" '
            'autocomplete="new-password" minlength="12" required>'
            "<button type=submit>Create organisation</button></form>"
            '<p class="alt">Already have an account? <a href="/login">Sign in</a>.</p>',
            error=error,
        )

    @app.post("/signup")
    def signup_submit(
        request: Request,
        email: str = Form(""),
        password: str = Form(""),
        org: str = Form(""),
        next: str = Form("/"),
    ):
        config = load_config()
        if not config.allow_signup:
            return _page("Sign up closed", "Ask an administrator for an account", "", status=403)
        store = IdentityStore()
        try:
            clean_email = normalise_email(email)
            slug = (org or "").strip() or slug_from_email(clean_email)
            if store.find_organization(slug) is not None:
                raise AuthError(
                    f"organisation {slug!r} is taken; choose another name"
                )
            # A self-service organisation starts with no financial data. It does not
            # inherit the demo corpus: another tenant's records are never a starting point.
            tenant = store.create_organization(slug, org or slug, dataset_kind="sql")
            principal = store.create_user(clean_email, password, tenant.org_id, Role.OWNER)
        except AuthError as exc:
            return signup_form(request, next=next, error=str(exc))
        raw = store.create_session(principal)
        store.log_event(
            "signup", "ok", user_id=principal.user_id, org_id=principal.org_id,
        )
        obs.event("auth.signup", org=principal.org_id)
        response = RedirectResponse(_safe_next(next), status_code=303)
        _set_session_cookie(response, raw)
        return response

    @app.get("/logout")
    @app.post("/logout")
    def logout(request: Request):
        cookie = request.cookies.get(SESSION_COOKIE) or ""
        if cookie:
            IdentityStore().revoke_session(cookie)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    # ------------------------------------------------------------ extension tokens

    @app.get("/tokens", response_class=HTMLResponse)
    def tokens_page(request: Request):
        return _render_tokens(request, "")

    def _render_tokens(request: Request, created: str):
        """Render the token page. ``created`` is shown once and never put in a URL."""
        principal = principal_of(request)
        if principal is None:
            return _page(
                "Extension tokens",
                "Authentication is off in local mode, so the extension needs no token.",
                '<p class="alt"><a href="/">Back to the desk</a></p>',
            )
        store = IdentityStore()
        rows = store.list_api_tokens(principal)
        listing = "".join(
            f'<li>{escape(r["label"] or r["token_id"])}'
            f'{" · revoked" if r["revoked"] else ""}</li>'
            for r in rows
        ) or "<li>none yet</li>"
        minted = ""
        if created:
            minted = (
                '<p class="err" style="background:#1d3a26;border-color:#2b6b3c;color:#b3ffc6">'
                "Copy this now — it is not shown again:<br><code style='word-break:break-all'>"
                + escape(created) + "</code></p>"
            )
        return _page(
            "Extension tokens",
            f"Signed in as {principal.email} ({principal.org_id})",
            minted
            + '<form method="post" action="/tokens">'
            '<label for="label">Label</label>'
            '<input id="label" name="label" type="text" placeholder="my laptop chrome">'
            "<button type=submit>Create token</button></form>"
            f"<ul style='font-size:.8rem;color:#8b93a7'>{listing}</ul>"
            '<p class="alt">Paste the token into the extension\'s options page. '
            "It carries your own permissions and nothing more — the extension cannot clear "
            'a transaction. <a href="/">Back to the desk</a></p>',
        )

    @app.post("/tokens", response_class=HTMLResponse)
    def tokens_create(request: Request, label: str = Form("")):
        """Mint a token and render it once, in the response body.

        Deliberately NOT a redirect carrying the token in a query string. A credential in a
        URL lands in the browser's history, in any intermediate proxy's access log, and in
        the server log of whatever handles the redirect target — none of which is a place a
        long-lived credential should come to rest.
        """
        principal = principal_of(request)
        if principal is None:
            return RedirectResponse("/tokens", status_code=303)
        raw = IdentityStore().create_api_token(principal, label)
        IdentityStore().log_event(
            "token_created", "ok", user_id=principal.user_id, org_id=principal.org_id,
        )
        obs.event("auth.token_created", org=principal.org_id, user=principal.user_id)
        return _render_tokens(request, raw)

    @app.get("/api/session")
    def api_session(request: Request):
        """Who am I, for the extension's connection check. Never returns a credential."""
        principal = principal_of(request)
        if principal is None:
            return JSONResponse({
                "ok": True, "authenticated": False, "auth_required": False,
                "mode": "local-single-tenant", "writes_cleared": False,
            })
        return JSONResponse({
            "ok": True, "authenticated": True, "auth_required": True,
            "email": principal.email, "org_id": principal.org_id,
            "role": principal.role.value, "credential": principal.credential,
            "permissions": sorted(
                p for p in ("read_financial", "read_ai", "review_exception", "export",
                            "administer") if principal.can(p)
            ),
            "can_clear": False,
            "note": "No role can authorise CLEARED. That gate is the deterministic engine's.",
            "writes_cleared": False,
        })
