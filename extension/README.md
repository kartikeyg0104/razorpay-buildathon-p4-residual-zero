# Residual Zero — Chrome extension (MV3)

A standalone reconciliation desk in the browser. Every feature runs **inside** the
extension against the local desk's read-only JSON APIs. No button opens the web app.

## Load it

    chrome://extensions → Developer mode → Load unpacked → this folder

## Point it at a desk

Open the extension's **options page** and set the desk URL, plus a token if that desk
requires authentication.

**A local development desk** needs no token:

    .venv/bin/python -m residual_zero.console
    # desk URL: http://127.0.0.1:8765

**A deployed desk** must be `https://` and needs a personal access token:

1. Open the desk in a browser and sign in.
2. Go to `/tokens` and create a token.
3. Paste it into the options page alongside the desk URL.

Chrome asks for permission to talk to that origin at the moment you save it — the manifest
requests only loopback up front (`optional_host_permissions`), so no production domain is
baked into the shipped package.

## What this extension holds

**No secrets.** No NVIDIA key, no database credential, no shared token. The model is called
server-side and its key never reaches the browser. The only credential stored here is the
token *you* minted for yourself, kept in `chrome.storage.local` (not `sync`, so it is not
replicated to your other machines) and sent only to the desk URL you configured.

The token carries your own permissions and nothing more. No role in Residual Zero can
authorise a clear.

## Views

| View | Backed by |
|---|---|
| Dashboard | `/api/desk`, `/api/t04`, `/api/health` |
| Exceptions (class filter) | `get_exceptions` |
| Investigate (8 filters + free text) | `explorer_query`, `get_ambiguous_transactions`, … |
| Transaction detail | `/api/credit/{id}`, `/api/finance/evidence`, `get_audit_trail` |
| Proof explorer (A/B diff) | `/api/finance/proof` |
| Ask AI | `/api/ask` |
| Human review | `get_exceptions`, `get_exposure_queue` |
| What-if | `/api/whatif` |
| Close & books | `/api/close`, `/api/journal` |
| Audit | `/api/health`, `get_batch_summary` |
| Data sources | `/api/recon`, `/api/mcp/tool` |
| Safety | `/api/health`, `/api/mcp/tools` |

`popup.html` is the 780×600 popup; `panel.html` is the same app full-width in a tab
(Expand). Both are extension pages — `chrome-extension://<id>/…`, never a desk URL.

## Safety

- **Read-only.** No write verb, no call to the desk's two write routes.
- **Cannot write CLEARED.** Every payload passes `assertReadOnly`, which refuses to render
  anything reporting `writes_cleared: true`.
- **No financial arithmetic.** Amounts arrive already rendered from integer paise. The
  extension formats nothing and computes nothing.
- **AI cannot clear.** `/api/ask` answers are validated server-side against engine state.
  AMBIGUOUS / NONE_FOUND / BUDGET_EXCEEDED stay unresolved.
- **Validated origin.** A loopback development desk, or an `https://` origin. Plain HTTP to
  a deployed desk is refused, because it would put the token and the organisation's
  financial data on the wire in clear text. Only the origin is kept — a path, query or
  fragment in a stored preference is discarded.
- **Confined to one organisation.** The token identifies a user, and the backend binds that
  user's organisation before any route runs. The extension cannot address another
  organisation's records even by asking for their ids.
- **No secrets.** No key material is bundled; the server holds provider credentials. The
  only credential here is the user's own token, in `chrome.storage.local`.
- **Inert strings.** DOM is built with `textContent`, so desk text can never become markup.
- Service worker rejects messages from foreign senders, unknown ops, and malformed ids.

## Tests

    pytest -q tests/test_extension.py tests/test_extension_parity.py
    RZ_E2E=1 pytest -q tests/e2e/test_extension_chromium.py
