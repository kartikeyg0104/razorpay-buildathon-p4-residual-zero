"use strict";
/**
 * Extension views. Each returns a DOM node built from an authoritative desk payload.
 *
 * No view computes a financial value, decides a disposition, or alters engine state. Where
 * a view shows a verdict it is rendering `decision` / `uniqueness` / `residual` exactly as
 * the deterministic backend returned them.
 */

import { api, assertReadOnly } from "./api.js";
import {
  aiAnswer, badge, disclosure, el, empty, errorState, evidenceList, field, fields, frag,
  kpi, kpiGrid, loading, mount, proofCompare, rowList, section, dash,
} from "./ui.js";

/* ------------------------------------------------------------------ dashboard */

export async function dashboardView(nav) {
  const [desk, t04, health] = await Promise.all([
    api.desk().then((d) => assertReadOnly(d, "desk")),
    api.track04().catch(() => null),
    api.health().catch(() => null),
  ]);
  const stats = (t04 && t04.stats) || {};
  return frag([
    kpiGrid([
      kpi({ label: "posted credits", value: desk.posted }),
      kpi({ label: "gate A verified", value: desk.gate_a, tone: "ok", sub: `${dash(desk.journalable)} journal-ready` }),
      kpi({ label: "needs human", value: desk.human, tone: "warn", sub: `${dash(desk.mismatch)} posted-mismatch` }),
      kpi({ label: "auto-cleared", value: desk.cleared, tone: "ok", sub: "guesses refused — the product" }),
    ]),
    t04
      ? section("Evaluation card", [
          kpiGrid([
            kpi({ label: "residual-zero", value: t04.residual_zero }),
            kpi({ label: "settlement-linked", value: t04.settlement_linked }),
            kpi({ label: "unreconciled", value: t04.unreconciled, tone: "warn" }),
            kpi({ label: "ambiguous", value: stats.ambiguous, tone: "warn" }),
          ]),
          el("p", { class: "muted" }, String(t04.note || "")),
        ])
      : null,
    section("Go to", [
      el("div", { class: "quick" }, [
        ["Exceptions queue", "#/exceptions"],
        ["Human review", "#/human"],
        ["Investigate", "#/explorer"],
        ["Ask AI", "#/ask"],
        ["Month-end close", "#/close"],
        ["Audit", "#/audit"],
      ].map(([label, href]) =>
        el("button", { class: "btn", type: "button", onclick: () => nav(href) }, label))),
    ]),
    health
      ? disclosure("Desk status", () =>
          fields([
            ["engine", health.DETERMINISTIC_CONTROLLER],
            ["audit chain", health.chain ? "intact" : "BROKEN"],
            ["live provider", health.LIVE_PROVIDER],
            ["provider", health.provider],
            ["writes cleared", String(health.writes_cleared)],
          ]))
      : null,
    el("p", { class: "honesty" }, String(desk.honesty || "")),
  ]);
}

/* ------------------------------------------------------------------ exceptions */

export async function exceptionsView(nav, state) {
  const wanted = state.get("cls") || "";
  const data = assertReadOnly(await api.tool("get_exceptions", wanted ? { exception_type: wanted } : {}), "exceptions");
  const rows = (data.rows || []).map((r) => ({ ...r, id: r.id || r.transaction_id }));
  const classes = Object.entries(data.by_class || {}).sort((a, b) => b[1] - a[1]);

  const chips = el("div", { class: "chips" }, [
    el("button", {
      class: `chip ${wanted ? "" : "on"}`, type: "button",
      onclick: () => state.set("cls", ""),
    }, `all · ${dash(data.count)}`),
    ...classes.map(([name, n]) =>
      el("button", {
        class: `chip ${wanted === name ? "on" : ""}`, type: "button",
        onclick: () => state.set("cls", name),
      }, `${name.toLowerCase().replace(/_/g, " ")} · ${n}`)),
  ]);

  return frag([
    kpiGrid([
      kpi({ label: "exceptions", value: data.count, tone: "warn" }),
      kpi({ label: "official ambiguous", value: data.official_ambiguous }),
      kpi({ label: "official none-found", value: data.official_none_found }),
    ]),
    chips,
    rowList(rows, (id) => nav(`#/credit/${id}`), "No exceptions in this class."),
  ]);
}

/* ------------------------------------------------------------------ credit */

const REASON = {
  AMBIGUOUS: "More than one member set reconciles to the same bank amount. The engine will not choose between them.",
  NONE_FOUND: "No permitted combination of ledger records equals this bank credit. Nothing was invented to close the gap.",
  BUDGET_EXCEEDED: "The search did not finish inside its budget, so uniqueness was never established.",
  UNIQUE: "Exactly one member set reconciles. Auto-clear additionally requires FULL pool scope and the ordering threshold.",
};

export async function creditView(nav, state, id) {
  const [credit, ev] = await Promise.all([
    api.credit(id).then((d) => assertReadOnly(d, "credit")),
    api.evidence(id).then((d) => assertReadOnly(d, "evidence")).catch(() => null),
  ]);
  if (!credit || credit.ok === false) {
    return frag([
      empty(`No credit named ${id}.`),
      el("button", { class: "btn", type: "button", onclick: () => nav("#/exceptions") }, "Back to exceptions"),
    ]);
  }
  const recon = (ev && ev.reconciliation) || {};
  const uniq = String(recon.uniqueness || credit.uniqueness || "").toUpperCase();

  return frag([
    el("div", { class: "cred-head" }, [
      el("h2", { class: "mono id" }, String(credit.id)),
      el("div", { class: "cred-badges" }, [
        badge(uniq || "—"),
        badge(credit.gate),
        credit.gate_a_ok ? badge("settlement verified", "ok") : badge("not verified", "warn"),
      ]),
    ]),

    kpiGrid([
      kpi({ label: "bank amount", value: credit.amount }),
      kpi({ label: "residual", value: recon.residual_display != null ? recon.residual_display : credit.residual_paise === 0 ? "0.00" : dash(credit.residual_paise), tone: credit.residual_paise === 0 ? "ok" : "warn" }),
      kpi({ label: "explanations found", value: recon.solution_count }),
      kpi({ label: "matched records", value: recon.matched_count }),
    ]),

    section("Authoritative facts", fields([
      ["account", credit.account, true],
      ["value date", credit.date, true],
      ["UTR / reference", credit.utr || (ev && ev.settlement && ev.settlement.reference), true],
      ["uniqueness", uniq, true],
      ["disposition", recon.disposition || credit.gate, true],
      ["status", recon.status, true],
      ["exception class", credit.cls, true],
      ["journalable", String(Boolean(credit.journalable))],
      ["posted mismatch", String(Boolean(credit.posted_mismatch))],
    ])),

    section("Why this is in front of you", [
      el("p", {}, REASON[uniq] || "The deterministic engine has not established a unique verified explanation."),
      ev && ev.next_best_action
        ? el("p", { class: "next" }, [el("b", {}, "Next action: "),
            String(ev.next_best_action.action || ev.next_best_action)])
        : null,
      el("p", { class: "muted" }, "The extension is read-only. It cannot clear this transaction."),
    ]),

    el("div", { class: "quick" }, [
      el("button", { class: "btn", type: "button", onclick: () => nav(`#/proof/${credit.id}`) }, "Proof explorer"),
      el("button", { class: "btn", type: "button", onclick: () => nav(`#/ask/${credit.id}`) }, "Ask AI about this"),
      el("button", { class: "btn", type: "button", onclick: () => nav(`#/whatif/${credit.id}`) }, "What-if"),
    ]),

    ev && Array.isArray(ev.candidates) && ev.candidates.length
      ? disclosure(`Candidate members · ${ev.candidates.length}`, () =>
          el("ul", { class: "idlist" }, ev.candidates.slice(0, 60).map((c) =>
            el("li", { class: "mono" }, String(c.item_id || c.id || c)))))
      : null,

    ev && ev.evidence
      ? disclosure("Evidence", () => evidenceList(
          Array.isArray(ev.evidence) ? ev.evidence : Object.entries(ev.evidence).map(([k, v]) => ({ field: k, value: v }))))
      : null,

    ev && ev.forensic
      ? disclosure("Forensic bucket", () => fields(Object.entries(ev.forensic).map(([k, v]) => [k, String(v), true])))
      : null,

    disclosure("Audit trail", () => {
      const host = el("div", {});
      mount(host, async () => {
        const trail = assertReadOnly(await api.tool("get_audit_trail", { transaction_id: credit.id }), "audit trail");
        const events = trail.events || [];
        return events.length
          ? el("ol", { class: "trace" }, events.map((e) =>
              el("li", {}, [el("span", { class: "mono" }, String(e.event || e.kind || "")),
                            el("span", { class: "muted" }, ` ${e.detail || e.at || ""}`)])))
          : empty("No audit events for this credit.");
      }, "audit trail");
      return host;
    }),
  ]);
}

/* ------------------------------------------------------------------ proof */

export async function proofView(nav, state, id) {
  const p = assertReadOnly(await api.proof(id), "proof");
  if (!p || p.found === false) return empty(`No proof available for ${id}.`);
  return frag([
    el("div", { class: "cred-head" }, [
      el("h2", { class: "mono id" }, String(id)),
      el("button", { class: "btn", type: "button", onclick: () => nav(`#/credit/${id}`) }, "Back to credit"),
    ]),
    proofCompare(p),
  ]);
}

/* ------------------------------------------------------------------ ask AI */

export function askView(nav, state, presetCredit) {
  const out = el("div", { class: "ask-out" });
  const input = el("input", {
    id: "ask-q", type: "search", placeholder: "Why did this not auto-clear?",
    autocomplete: "off", "aria-label": "Question for the AI finance controller",
  });
  const cid = el("input", {
    id: "ask-cid", type: "text", placeholder: "crd_… (optional)",
    value: presetCredit || "", "aria-label": "Credit id",
  });

  const run = async (question) => {
    if (!question.trim()) return;
    out.replaceChildren(loading("the AI finance controller"));
    try {
      const res = assertReadOnly(await api.ask(question, cid.value.trim()), "AI answer");
      out.replaceChildren(aiAnswer(res));
    } catch (err) {
      out.replaceChildren(errorState(err, () => run(question)));
    }
  };

  const form = el("form", {
    class: "ask-form",
    onsubmit: (e) => { e.preventDefault(); run(input.value); },
  }, [input, cid, el("button", { class: "btn primary", type: "submit" }, "Ask")]);

  const suggestions = [
    "Why did this transaction not auto-clear?",
    "Clear this transaction.",
    "What is the batch summary?",
    "Show me the exceptions.",
  ];

  return frag([
    section("AI finance controller", [
      el("p", { class: "muted" },
        "The model explains deterministic results and picks the next read-only tool. It cannot clear anything, and its answer is validated against engine state before it is shown."),
      form,
      el("div", { class: "chips" }, suggestions.map((s) =>
        el("button", { class: "chip", type: "button", onclick: () => { input.value = s; run(s); } }, s))),
    ]),
    out,
  ]);
}

/* ------------------------------------------------------------------ explorer */

const EXPLORER_CHIPS = [
  ["ambiguous", "get_ambiguous_transactions", {}],
  ["unmatched", "get_unmatched_transactions", {}],
  ["verified", "get_verified_transactions", {}],
  ["recoverable", "get_potentially_recoverable", {}],
  ["missing records", "get_missing_records", {}],
  ["top exceptions", "get_top_exceptions", {}],
  ["duplicate UTRs", "get_duplicate_utrs", {}],
  ["exposure queue", "get_exposure_queue", {}],
];

export async function explorerView(nav, state) {
  const active = state.get("f") || "ambiguous";
  const host = el("div", {});
  const chips = el("div", { class: "chips" }, EXPLORER_CHIPS.map(([label]) =>
    el("button", {
      class: `chip ${active === label ? "on" : ""}`, type: "button",
      onclick: () => state.set("f", label),
    }, label)));

  const search = el("form", {
    class: "ask-form",
    onsubmit: (e) => {
      e.preventDefault();
      const q = e.target.querySelector("input").value.trim();
      if (!q) return;
      mount(host, async () => {
        const res = assertReadOnly(await api.tool("explorer_query", { q }), "explorer");
        return rowList((res.rows || []).map((r) => ({ ...r, id: r.id || r.transaction_id })),
                       (id) => nav(`#/credit/${id}`), `Nothing matched “${q}”.`);
      }, "results");
    },
  }, [
    el("input", { type: "search", placeholder: "free-text query (account, id, class…)", "aria-label": "Explorer query" }),
    el("button", { class: "btn", type: "submit" }, "Query"),
  ]);

  const entry = EXPLORER_CHIPS.find(([l]) => l === active) || EXPLORER_CHIPS[0];
  mount(host, async () => {
    const res = assertReadOnly(await api.tool(entry[1], entry[2]), "explorer");
    const rows = (res.rows || res.transactions || []).map((r) =>
      typeof r === "string" ? { id: r } : { ...r, id: r.id || r.transaction_id });
    return frag([
      el("p", { class: "muted" }, `${dash(res.n != null ? res.n : rows.length)} row(s) · ${entry[1]}`),
      rowList(rows, (id) => nav(`#/credit/${id}`), "No rows for this filter."),
    ]);
  }, active);

  return frag([section("Investigate", [search, chips]), host]);
}

/* ------------------------------------------------------------------ human review */

export async function humanView(nav) {
  const [exc, exposure] = await Promise.all([
    api.tool("get_exceptions", {}).then((d) => assertReadOnly(d, "queue")),
    api.tool("get_exposure_queue", { limit: 12 }).then((d) => assertReadOnly(d, "exposure")).catch(() => null),
  ]);
  const rows = (exc.rows || []).map((r) => ({ ...r, id: r.id || r.transaction_id }));
  return frag([
    section("Human review queue", [
      el("p", { class: "muted" },
        "These need a person because the engine refused to guess. The extension shows the evidence; it does not record decisions — resolution is a desk write path and stays there."),
      kpiGrid([
        kpi({ label: "awaiting review", value: exc.count, tone: "warn" }),
        kpi({ label: "ambiguous", value: exc.official_ambiguous }),
        kpi({ label: "none found", value: exc.official_none_found }),
      ]),
    ]),
    exposure && (exposure.rows || []).length
      ? section("Highest exposure first", rowList(
          exposure.rows.map((r) => ({ ...r, id: r.id || r.transaction_id })),
          (id) => nav(`#/credit/${id}`), "No exposure rows."))
      : null,
    section("Queue", rowList(rows, (id) => nav(`#/credit/${id}`), "Queue is empty.")),
  ]);
}

/* ------------------------------------------------------------------ what-if */

export async function whatifView(nav, state, id) {
  const credit = id || "crd_001_acc_01_2025-01-09";
  const bps = state.get("bps");
  const data = await api.whatif(credit, bps === "" || bps == null ? undefined : bps);
  assertReadOnly(data, "what-if");
  const presets = (data.presets || [0, 300, 500, 700]);

  const body = data.ok
    ? frag([
        kpiGrid([
          kpi({ label: "baseline reserve", value: `${data.baseline.bps} bps`, sub: `residual ${data.baseline.residual}` }),
          kpi({ label: "scenario reserve", value: `${data.scenario.bps} bps`, sub: `residual ${data.scenario.residual}`,
                tone: data.scenario.ok ? "ok" : "warn" }),
          kpi({ label: "members", value: data.members }),
          kpi({ label: "identical", value: data.scenario.same ? "YES" : "NO", tone: data.scenario.same ? "ok" : "warn" }),
        ]),
        fields([
          ["baseline verifies", String(data.baseline.ok)],
          ["scenario verifies", String(data.scenario.ok)],
          ["baseline line deltas", data.baseline.deltas],
          ["scenario line deltas", data.scenario.deltas],
        ]),
      ])
    : empty(data.error === "no_declared_member_set"
        ? "This credit has no declared member set. What-if does not invent one."
        : `What-if unavailable: ${data.error}`);

  return frag([
    section("Scenario analysis", [
      el("p", { class: "muted" }, String(data.note || "")),
      el("div", { class: "chips" }, presets.map((p) =>
        el("button", {
          class: `chip ${String(data.scenario && data.scenario.bps) === String(p) ? "on" : ""}`,
          type: "button", onclick: () => state.set("bps", String(p)),
        }, `${p} bps`))),
      el("p", { class: "mono muted" }, credit),
    ]),
    body,
  ]);
}

/* ------------------------------------------------------------------ close / books */

export async function closeView() {
  const [close, journal] = await Promise.all([
    api.close().then((d) => assertReadOnly(d, "close")),
    api.journal().then((d) => assertReadOnly(d, "journal")).catch(() => null),
  ]);
  const checklist = close.checklist || [];
  return frag([
    kpiGrid([
      kpi({ label: "as of", value: close.as_of }),
      kpi({ label: "auto-clear", value: close.auto_clear, tone: "ok" }),
      kpi({ label: "needs human", value: close.n_human, tone: "warn" }),
      kpi({ label: "bank uncovered", value: close.n_bank_uncovered }),
    ]),
    journal && journal.ok
      ? section("Books & journal", [
          kpiGrid([
            kpi({ label: "debits", value: journal.debits }),
            kpi({ label: "credits", value: journal.credits }),
            kpi({ label: "balanced", value: journal.balanced ? "YES" : "NO", tone: journal.balanced ? "ok" : "bad" }),
            kpi({ label: "control residual", value: journal.control_residual, tone: journal.control_residual_paise === 0 ? "ok" : "bad" }),
          ]),
          el("p", { class: "muted" }, `${journal.n_lines} journal lines · ${journal.note}`),
        ])
      : null,
    checklist.length
      ? section("Close checklist", el("ul", { class: "evs" }, checklist.map((c) =>
          el("li", { class: "ev" }, [
            el("span", { class: "ev-k" }, String(c.name || c.label || "")),
            badge(c.ok ? "ok" : "attention", c.ok ? "ok" : "warn"),
          ]))))
      : null,
    close.certificate_sha256
      ? disclosure("Batch certificate", () => fields([["sha256", close.certificate_sha256, true]]))
      : null,
  ]);
}

/* ------------------------------------------------------------------ audit */

export async function auditView() {
  const [health, summary] = await Promise.all([
    api.health(),
    api.tool("get_batch_summary", {}).then((d) => assertReadOnly(d, "summary")).catch(() => null),
  ]);
  return frag([
    kpiGrid([
      kpi({ label: "audit chain", value: health.chain ? "INTACT" : "BROKEN", tone: health.chain ? "ok" : "bad" }),
      kpi({ label: "credits", value: health.n_credits }),
      kpi({ label: "gate A", value: health.n_gate_a, tone: "ok" }),
      kpi({ label: "auto-clear", value: health.auto_clear, tone: "ok" }),
    ]),
    summary
      ? section("Batch summary", fields([
          ["ambiguous", summary.ambiguous],
          ["none found", summary.none_found],
          ["budget exceeded", summary.budget_exceeded],
          ["flagged", summary.flagged],
          ["false clears", summary.false_clears],
          ["auto clear", summary.auto_clear],
        ]))
      : null,
    el("p", { class: "honesty" }, String(health.note || "")),
  ]);
}

/* ------------------------------------------------------------------ safety */

export async function safetyView() {
  const [health, mcp] = await Promise.all([api.health(), api.mcpTools().catch(() => null)]);
  return frag([
    section("Safety controls", [
      kpiGrid([
        kpi({ label: "extension writes CLEARED", value: "NEVER", tone: "ok" }),
        kpi({ label: "desk writes_cleared", value: String(health.writes_cleared), tone: health.writes_cleared ? "bad" : "ok" }),
        kpi({ label: "auto-clear", value: health.auto_clear, tone: "ok" }),
        kpi({ label: "controller", value: health.DETERMINISTIC_CONTROLLER, tone: "ok" }),
      ]),
      el("p", { class: "muted" },
        "The deterministic engine is the only financial authority. AI explains and selects read-only tools; it never authorises a clear. AMBIGUOUS, NONE_FOUND and BUDGET_EXCEEDED stay unresolved."),
    ]),
    mcp
      ? section("Read-only tool allowlist", [
          fields([["adapter enabled", String(mcp.enabled)], ["source", mcp.source], ["written", String(mcp.written)]]),
          disclosure(`Allowed · ${(mcp.allowed || []).length}`, () =>
            el("ul", { class: "idlist" }, (mcp.allowed || []).map((t) => el("li", { class: "mono" }, t)))),
          disclosure(`Refused · ${(mcp.refused || []).length}`, () =>
            el("ul", { class: "idlist bad" }, (mcp.refused || []).map((t) => el("li", { class: "mono" }, t)))),
        ])
      : null,
  ]);
}

/* ------------------------------------------------------------------ data sources */

export function sourcesView() {
  const out = el("div", {});
  const ta = el("textarea", {
    id: "recon-json", rows: "6",
    placeholder: '{"entity":"collection","items":[...]}',
    "aria-label": "Recon JSON to preview",
  });

  const preview = async () => {
    let payload;
    try {
      payload = JSON.parse(ta.value || "{}");
    } catch {
      out.replaceChildren(errorState(new Error("That is not valid JSON."), null));
      return;
    }
    await mount(out, async () => {
      const d = assertReadOnly(await api.reconPreview(payload), "recon preview");
      return fields([
        ["rows parsed", d.n], ["ledger hits", d.ledger_hits],
        ["written", String(d.written)], ["cleared", d.cleared],
      ]);
    }, "preview");
  };

  const runFixture = () =>
    mount(out, async () => {
      const d = assertReadOnly(
        await api.mcpTool("fetch_settlement_recon_details", { year: 2025, month: 1 }),
        "MCP recon");
      return fields([
        ["rows", d.n], ["source", d.source], ["ledger hits", d.ledger_hits],
        ["written", String(d.written)], ["cleared", d.cleared],
      ]);
    }, "MCP recon");

  return frag([
    section("Data sources", [
      el("p", { class: "muted" },
        "Preview settlement recon payloads. Parsing writes nothing — no ledger row, no disposition, no clear."),
      ta,
      el("div", { class: "quick" }, [
        el("button", { class: "btn", type: "button", onclick: preview }, "Preview pasted JSON"),
        el("button", { class: "btn", type: "button", onclick: runFixture }, "Run fixture MCP recon"),
      ]),
    ]),
    out,
  ]);
}

/* ------------------------------------------------------------------ search */

export async function searchView(nav, state) {
  const q = state.get("q") || "";
  if (!q) return empty("Type a credit id, account or UTR above.");
  const res = assertReadOnly(await api.lookup(q), "lookup");
  return frag([
    el("p", { class: "muted" }, `${dash(res.n)} match(es) for “${q}”`),
    rowList(res.rows || [], (id) => nav(`#/credit/${id}`), `Nothing matched “${q}”.`),
  ]);
}
