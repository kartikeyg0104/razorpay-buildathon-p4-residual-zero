"use strict";
/**
 * Reusable extension components.
 *
 * Everything is built with createElement + textContent. No innerHTML anywhere, so desk
 * strings (narrations, AI prose, tool output) can never become markup in the extension.
 */

export function el(tag, attrs, children) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === false) return;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else node.setAttribute(key, value === true ? "" : String(value));
  });
  (Array.isArray(children) ? children : children != null ? [children] : [])
    .filter((c) => c !== null && c !== undefined && c !== false)
    .forEach((c) => node.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
  return node;
}

export const frag = (children) => {
  const f = document.createDocumentFragment();
  (children || []).filter(Boolean).forEach((c) => f.appendChild(c));
  return f;
};

/** Long em dash for "the desk did not produce this", never a zero. */
export const dash = (v) => (v === 0 ? "0" : v === false ? "false" : v ? String(v) : "—");

/* ------------------------------------------------------------------ primitives */

export function section(title, children, extra) {
  return el("section", { class: "card" }, [
    title ? el("h2", { class: "card-h" }, [title, extra || null]) : null,
    ...(Array.isArray(children) ? children : [children]),
  ]);
}

const BADGE_TONE = {
  UNIQUE: "ok",
  VERIFIED: "ok",
  ACCEPT: "ok",
  GATE_A: "ok",
  CLEARED: "ok",
  YES: "ok",
  AMBIGUOUS: "warn",
  REVIEW_REQUIRED: "warn",
  FLAGGED: "warn",
  BUDGET_EXCEEDED: "warn",
  PENDING: "warn",
  NONE_FOUND: "bad",
  UNMATCHED: "bad",
  NOT_RECONCILED: "bad",
  REFUSE: "bad",
  REFUSED: "bad",
  NO: "bad",
};

export function badge(value, toneOverride) {
  const text = String(value == null || value === "" ? "—" : value);
  const tone = toneOverride || BADGE_TONE[text.toUpperCase()] || "neutral";
  return el("span", { class: `badge ${tone}`, title: text }, text);
}

export function kpi({ label, value, sub, tone }) {
  return el("article", { class: `kpi ${tone || ""}`.trim() }, [
    el("div", { class: "kpi-l" }, String(label)),
    el("div", { class: "kpi-v" }, dash(value)),
    sub ? el("div", { class: "kpi-s" }, String(sub)) : null,
  ]);
}

export const kpiGrid = (cards) => el("div", { class: "kpis" }, cards.filter(Boolean));

export function field(label, value, mono) {
  return el("div", { class: "field" }, [
    el("dt", {}, String(label)),
    el("dd", { class: mono ? "mono" : "" }, dash(value)),
  ]);
}

export const fields = (rows) =>
  el("dl", { class: "fields" }, rows.filter(Boolean).map(([l, v, m]) => field(l, v, m)));

/**
 * A transaction row. `onOpen` navigates inside the extension — these are never links to
 * the web app.
 */
export function txnRow(row, onOpen) {
  const id = String(row.id || row.transaction_id || "");
  const node = el(
    "button",
    {
      class: "row",
      type: "button",
      "data-id": id,
      onclick: () => onOpen && onOpen(id),
    },
    [
      el("span", { class: "row-main" }, [
        el("span", { class: "row-id mono" }, id),
        el("span", { class: "row-sub" }, [
          row.account ? `${row.account} · ` : "",
          row.date || row.value_date || "",
          row.utr ? ` · ${row.utr}` : "",
        ].join("")),
      ]),
      el("span", { class: "row-right" }, [
        row.amount ? el("span", { class: "row-amt mono" }, String(row.amount)) : null,
        row.uniqueness ? badge(row.uniqueness) : null,
        row.cls || row.exception_class ? badge(row.cls || row.exception_class, "neutral") : null,
        row.gate ? badge(row.gate) : null,
      ]),
    ],
  );
  return node;
}

export const rowList = (rows, onOpen, emptyText) =>
  rows && rows.length
    ? el("div", { class: "rows" }, rows.map((r) => txnRow(r, onOpen)))
    : empty(emptyText || "Nothing here.");

export function evidenceItem(ev) {
  const label = ev.field || ev.label || ev.kind || ev.evidence_type || "evidence";
  const value = ev.value != null ? ev.value : ev.detail != null ? ev.detail : ev.text;
  return el("li", { class: "ev" }, [
    el("span", { class: "ev-k" }, String(label)),
    el("span", { class: "ev-v mono" }, dash(value)),
    ev.source_record_id || ev.source ? el("span", { class: "ev-src" }, String(ev.source_record_id || ev.source)) : null,
    ev.verified === true ? badge("verified", "ok") : ev.verified === false ? badge("unverified", "warn") : null,
  ]);
}

export const evidenceList = (items) =>
  items && items.length
    ? el("ul", { class: "evs" }, items.map(evidenceItem))
    : empty("No evidence rows returned.");

/* ------------------------------------------------------------------ states */

export const loading = (what) =>
  el("div", { class: "state loading", role: "status", "aria-live": "polite" }, [
    el("span", { class: "spinner", "aria-hidden": "true" }),
    el("span", {}, what ? `Loading ${what}…` : "Loading…"),
  ]);

export const empty = (text) => el("div", { class: "state empty" }, String(text));

export function errorState(err, onRetry) {
  const kind = (err && err.kind) || "error";
  const message =
    kind === "offline"
      ? "Desk offline."
      : kind === "timeout"
        ? "The desk timed out."
        : String((err && err.message) || err);
  return el("div", { class: "state error", role: "alert" }, [
    el("strong", {}, message),
    kind === "offline"
      ? el("code", { class: "hint" }, ".venv/bin/python -m residual_zero.console")
      : kind === "offline" || kind === "timeout"
        ? null
        : el("span", { class: "hint" }, String((err && err.message) || "")),
    // An unauthenticated desk needs one specific action, so offer it here rather than
    // naming a page the reader then has to go hunting for in Chrome's own menus.
    kind === "unauthenticated"
      ? el("button", {
          class: "btn", type: "button",
          onclick: () => {
            if (globalThis.chrome && chrome.runtime && chrome.runtime.openOptionsPage) {
              chrome.runtime.openOptionsPage();
            }
          },
        }, "Open settings")
      : null,
    onRetry ? el("button", { class: "btn", type: "button", onclick: onRetry }, "Retry") : null,
  ]);
}

/** Render an async producer into a host node with loading and error states. */
export async function mount(host, producer, what, onRetry) {
  host.replaceChildren(loading(what));
  try {
    const node = await producer();
    host.replaceChildren(node);
  } catch (err) {
    host.replaceChildren(errorState(err, onRetry));
  }
}

/* ------------------------------------------------------------------ disclosure */

export function disclosure(summaryText, build, open) {
  const d = el("details", { class: "disc" }, [el("summary", {}, String(summaryText))]);
  if (open) d.setAttribute("open", "");
  let built = false;
  const fill = () => {
    if (built || !d.open) return;
    built = true;
    d.appendChild(build());
  };
  d.addEventListener("toggle", fill);
  if (open) fill();
  return d;
}

/* ------------------------------------------------------------------ proof compare */

/**
 * Solution A / B comparison. Purely a rendering of the deterministic
 * `/api/finance/proof` payload — the extension does not decide anything here.
 */
export function proofCompare(p) {
  const sols = Array.isArray(p.solutions) ? p.solutions : [];
  const diff = p.difference || {};
  const only = (k) => (Array.isArray(diff[k]) ? diff[k] : []);
  const idList = (ids) =>
    ids.length
      ? el("ul", { class: "idlist" }, ids.map((i) => el("li", { class: "mono" }, String(i))))
      : el("p", { class: "muted" }, "none");

  return el("div", { class: "proof" }, [
    kpiGrid([
      kpi({ label: "bank amount", value: p.bank_display }),
      kpi({ label: "candidates", value: sols.length || p.n_solutions }),
      kpi({ label: "decision", value: p.decision, tone: "warn" }),
      kpi({ label: "can auto-select", value: p.choose_one ? "YES" : "NO", tone: p.choose_one ? "ok" : "warn" }),
    ]),
    el("div", { class: "sols" }, sols.slice(0, 2).map((s, i) =>
      el("div", { class: "sol" }, [
        el("h3", {}, `Explanation ${String.fromCharCode(65 + i)}`),
        fields([
          ["members", (s.member_ids || s.members || []).length],
          ["total", s.total_display || s.total, true],
          ["residual", s.residual_display != null ? s.residual_display : s.residual, true],
          ["source", s.source],
        ]),
        idList(s.member_ids || s.members || []),
      ]),
    )),
    section("Comparison", [
      fields([
        ["shared records", (diff.common || diff.shared || []).length],
        ["residual A / B", p.residual_pair || (sols[0] && sols[1] ? `${sols[0].residual_display} / ${sols[1].residual_display}` : "—"), true],
        ["distinguishing evidence", p.distinguishing_authoritative_evidence || "NONE"],
        ["decision", p.decision],
      ]),
      el("div", { class: "cols2" }, [
        el("div", {}, [el("h4", {}, "only in A"), idList(only("only_a"))]),
        el("div", {}, [el("h4", {}, "only in B"), idList(only("only_b"))]),
      ]),
    ]),
    el("p", { class: "verdict-note" },
      p.choose_one
        ? "The deterministic engine reports a single explanation."
        : "Both explanations satisfy the financial equation. No authoritative evidence distinguishes them. Human review is required — the extension cannot pick a winner."),
  ]);
}

/* ------------------------------------------------------------------ AI answer */

export function aiAnswer(payload) {
  const tools = payload.tools_called || payload.investigation_steps || [];
  return el("div", { class: "ai" }, [
    el("div", { class: "ai-meta" }, [
      badge(payload.provider_used || payload.llm_used ? "live model" : "deterministic template",
            payload.provider_used || payload.llm_used ? "ok" : "neutral"),
      payload.intent ? badge(payload.intent, "neutral") : null,
      payload.decision ? badge(payload.decision) : null,
      el("span", { class: "ai-flag" }, "writes CLEARED: false"),
    ]),
    el("div", { class: "ai-body" }, String(payload.answer || "").trim() || "(no answer)"),
    payload.recommended_action
      ? el("p", { class: "ai-next" }, [el("b", {}, "Next: "), String(payload.recommended_action)])
      : null,
    payload.provider_error
      ? el("p", { class: "muted" }, `provider: ${payload.provider_error}`)
      : null,
    tools.length
      ? disclosure(`Investigation trace · ${tools.length} step${tools.length === 1 ? "" : "s"}`, () =>
          el("ol", { class: "trace" }, tools.map((t) =>
            el("li", {}, [
              el("span", { class: "mono" }, String(t.tool || t.label || t)),
              t.ok === false ? badge("failed", "bad") : null,
            ]),
          )))
      : null,
    Array.isArray(payload.citations) && payload.citations.length
      ? disclosure(`Citations · ${payload.citations.length}`, () =>
          el("ul", { class: "idlist" }, payload.citations.map((c) => el("li", { class: "mono" }, String(c)))))
      : null,
  ]);
}
