"use strict";
/**
 * Desk API client.
 *
 * Every number this extension renders comes from here. The extension performs no financial
 * arithmetic of its own: the deterministic engine behind these endpoints is the authority,
 * and amounts arrive already rendered from integer paise by the backend formatter.
 *
 * All endpoints used are read-only. `/api/finance/tool` and `/api/mcp/tool` are POSTs only
 * because they carry a tool name and arguments; both are enforced server-side against a
 * read-only allowlist and both report `writes_cleared: false`.
 *
 * ## Credentials
 *
 * The extension ships with NO secret. It holds no NVIDIA key, no database credential and no
 * shared token — the model is called server-side and its key never leaves the server. What
 * the extension does hold is a personal access token the *user* minted for themselves on the
 * desk's `/tokens` page and pasted into the options page. That token carries exactly the
 * user's own permissions, and no permission in the system authorises a financial clear.
 *
 * A bearer token rather than the desk's session cookie, for two reasons: a cookie would have
 * to be sent cross-origin from an extension page, which requires relaxing `SameSite` on the
 * desk's session cookie for everybody; and a bearer token is not a CSRF vector, so the desk
 * can keep its origin check strict.
 *
 * The token lives in `chrome.storage.local`, not `chrome.storage.sync`: a credential should
 * not be replicated to the user's other machines as a side effect of being saved.
 */

export const DEFAULT_DESK = "https://residual-zero-production.up.railway.app";
// The hosted desk, because that is the one a person who installs this can
// actually reach. It used to default to loopback, which is only useful to
// somebody already running a console — everyone else installed the extension and
// got "Desk offline" against a port with nothing behind it. Loopback is still one
// click away in the options page, and is still a permitted origin.

/** Keys in chrome.storage.local. */
const DESK_KEY = "desk";
const TOKEN_KEY = "apiToken";

/**
 * Which desk URLs are acceptable.
 *
 * Loopback is allowed so a local development desk still works. Anything else must be
 * `https://` — an extension that would talk to a deployed desk over plain HTTP would put
 * the user's token and their organisation's financial data on the wire in clear text.
 */
export const LOOPBACK = ["http://127.0.0.1:8765", "http://localhost:8765"];

export class DeskError extends Error {
  constructor(message, kind) {
    super(message);
    this.name = "DeskError";
    this.kind = kind || "error";
  }
}

/**
 * Normalise a desk origin, or return "" when it is not usable.
 *
 * Returning "" rather than silently falling back to the default matters now that the desk
 * can be a real deployment: quietly rewriting a mistyped production URL to `127.0.0.1`
 * would show the operator an empty local desk and look like missing data.
 */
export function normaliseDesk(raw) {
  const value = String(raw || "").trim().replace(/\/+$/, "");
  if (!value) return "";
  if (LOOPBACK.includes(value)) return value;
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return "";
  }
  if (parsed.protocol !== "https:") return "";
  // Origin only. A path, query or fragment in a stored preference would be prepended to
  // every request path.
  return parsed.origin;
}

function storage() {
  return globalThis.chrome && chrome.storage && chrome.storage.local
    ? chrome.storage.local
    : null;
}

/** Read the configured desk origin and token. Never logged, never rendered. */
export function deskConfig() {
  return new Promise((resolve) => {
    const store = storage();
    if (!store) {
      resolve({ desk: DEFAULT_DESK, token: "" });
      return;
    }
    store.get({ [DESK_KEY]: DEFAULT_DESK, [TOKEN_KEY]: "" }, (got) => {
      resolve({
        desk: normaliseDesk(got && got[DESK_KEY]) || DEFAULT_DESK,
        token: String((got && got[TOKEN_KEY]) || ""),
      });
    });
  });
}

export function saveDeskConfig(desk, token) {
  return new Promise((resolve, reject) => {
    const store = storage();
    const safe = normaliseDesk(desk);
    if (!safe) {
      reject(new DeskError(
        "A desk URL must be https:// (or a loopback development desk).", "config",
      ));
      return;
    }
    if (!store) {
      resolve(safe);
      return;
    }
    store.set({ [DESK_KEY]: safe, [TOKEN_KEY]: String(token || "").trim() }, () => resolve(safe));
  });
}

export function deskUrl() {
  return deskConfig().then((c) => c.desk);
}

const TIMEOUT_MS = 30000;

async function request(path, init) {
  const { desk, token } = await deskConfig();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const headers = { ...((init && init.headers) || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(desk + path, { ...(init || {}), headers, signal: controller.signal });
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new DeskError("The desk did not answer within 30s.", "timeout");
    }
    throw new DeskError(
      `Cannot reach the desk at ${desk}. Check the URL on the extension's options page; ` +
      "for a local desk, start it with:  python -m residual_zero.console",
      "offline",
    );
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new DeskError(`The desk returned ${res.status} but not JSON.`, "malformed");
    }
  }
  if (res.status === 401) {
    throw new DeskError(
      "The desk did not accept this token. Open the desk in a browser, sign in, create a " +
      "token on its /tokens page, and paste it into the extension's options page.",
      "unauthenticated",
    );
  }
  if (res.status === 403) {
    const detail = (data && (data.detail || data.error)) || "This account may not do that.";
    throw new DeskError(String(detail), "forbidden");
  }
  if (!res.ok) {
    const detail = (data && (data.error || data.detail)) || `HTTP ${res.status}`;
    throw new DeskError(String(detail), res.status === 404 ? "not_found" : "http");
  }
  return data;
}

const qs = (params) => {
  const out = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") out.set(k, String(v));
  });
  const s = out.toString();
  return s ? `?${s}` : "";
};

const getJson = (path, params) => request(path + qs(params), { method: "GET" });
const postJson = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body || {}),
  });

export const api = {
  health: () => getJson("/api/health"),
  /** Who the token belongs to, and which organisation this extension is reading. */
  session: () => getJson("/api/session"),
  desk: () => getJson("/api/desk"),
  track04: () => getJson("/api/t04"),
  ops: () => getJson("/api/ops"),
  close: () => getJson("/api/close"),
  journal: () => getJson("/api/journal"),
  whatif: (credit_id, reserve_bps) => getJson("/api/whatif", { credit_id, reserve_bps }),
  lookup: (q) => getJson("/api/lookup", { q }),
  credit: (id) => getJson(`/api/credit/${encodeURIComponent(id)}`),
  evidence: (transaction_id) => getJson("/api/finance/evidence", { transaction_id }),
  proof: (transaction_id) => getJson("/api/finance/proof", { transaction_id }),
  ask: (question, credit_id) => postJson("/api/ask", { question, credit_id }),
  /** Read-only allowlisted finance tool. The server rejects anything off the 43-name list. */
  tool: (name, args) => postJson("/api/finance/tool", { name, arguments: args || {} }),
  mcpTools: () => getJson("/api/mcp/tools"),
  mcpTool: (tool, args) => postJson("/api/mcp/tool", { tool, arguments: args || {} }),
  reconPreview: (payload) => postJson("/api/recon", payload),
};

/**
 * A response that claims a clear is a backend contract violation, not something the
 * extension should render. Every payload is checked before it reaches a view.
 */
export function assertReadOnly(payload, where) {
  if (payload && payload.writes_cleared === true) {
    throw new DeskError(
      `Refusing to render ${where}: the desk reported writes_cleared=true.`,
      "invariant",
    );
  }
  return payload;
}
