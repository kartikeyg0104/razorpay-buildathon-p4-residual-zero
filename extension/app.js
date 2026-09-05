"use strict";
/**
 * Extension shell: navigation, routing, and view mounting.
 *
 * Routing is hash-based and entirely inside the extension page, so back/forward work and
 * no route ever leaves for the web app. The only `chrome.tabs.create` in this extension
 * opens the extension's OWN panel page (chrome.runtime.getURL), never a desk URL.
 */

import { api, deskUrl } from "./lib/api.js";
import { el, errorState, loading } from "./lib/ui.js";
import {
  askView, auditView, closeView, creditView, dashboardView, exceptionsView, explorerView,
  humanView, proofView, safetyView, searchView, sourcesView, whatifView,
} from "./lib/views.js";

const NAV = [
  ["#/", "Dashboard", "D"],
  ["#/exceptions", "Exceptions", "E"],
  ["#/explorer", "Investigate", "I"],
  ["#/human", "Human review", "H"],
  ["#/ask", "Ask AI", "A"],
  ["#/proof", "Proof explorer", "P"],
  ["#/whatif", "What-if", "W"],
  ["#/close", "Close & books", "C"],
  ["#/audit", "Audit", "U"],
  ["#/sources", "Data sources", "S"],
  ["#/safety", "Safety", "Y"],
];

/** Per-route query state held in the hash, so filters survive back/forward. */
function makeState(params, onChange) {
  return {
    get: (k) => params.get(k),
    set: (k, v) => {
      const next = new URLSearchParams(params);
      if (v === "" || v == null) next.delete(k);
      else next.set(k, v);
      onChange(next);
    },
  };
}

const ROUTES = [
  [/^#?\/?$/, (nav, state) => dashboardView(nav, state), "Dashboard"],
  [/^#\/exceptions/, (nav, state) => exceptionsView(nav, state), "Exceptions"],
  [/^#\/explorer/, (nav, state) => explorerView(nav, state), "Investigate"],
  [/^#\/human/, (nav, state) => humanView(nav, state), "Human review"],
  [/^#\/ask\/([^?]+)/, (nav, state, m) => askView(nav, state, decodeURIComponent(m[1])), "Ask AI"],
  [/^#\/ask/, (nav, state) => askView(nav, state, ""), "Ask AI"],
  [/^#\/credit\/([^?]+)/, (nav, state, m) => creditView(nav, state, decodeURIComponent(m[1])), "Transaction"],
  [/^#\/proof\/([^?]+)/, (nav, state, m) => proofView(nav, state, decodeURIComponent(m[1])), "Proof explorer"],
  [/^#\/proof/, (nav, state) => proofPicker(nav), "Proof explorer"],
  [/^#\/whatif\/([^?]+)/, (nav, state, m) => whatifView(nav, state, decodeURIComponent(m[1])), "What-if"],
  [/^#\/whatif/, (nav, state) => whatifView(nav, state, ""), "What-if"],
  [/^#\/close/, () => closeView(), "Close & books"],
  [/^#\/audit/, () => auditView(), "Audit"],
  [/^#\/sources/, () => sourcesView(), "Data sources"],
  [/^#\/safety/, () => safetyView(), "Safety"],
  [/^#\/search/, (nav, state) => searchView(nav, state), "Search"],
];

async function proofPicker(nav) {
  const desk = await api.desk();
  return el("div", {}, [
    el("p", { class: "muted" }, "Open a transaction to compare its candidate explanations."),
    el("button", { class: "btn primary", type: "button", onclick: () => nav(`#/proof/${desk.demo_credit}`) },
      `Open ${desk.demo_credit}`),
    el("button", { class: "btn", type: "button", onclick: () => nav("#/exceptions") }, "Pick from exceptions"),
  ]);
}

function currentRoute() {
  const raw = location.hash || "#/";
  const [pathPart, queryPart] = raw.split("?");
  const params = new URLSearchParams(queryPart || "");
  for (const [re, build, title] of ROUTES) {
    const m = pathPart.match(re);
    if (m) return { build, title, match: m, params, pathPart };
  }
  return { build: () => el("div", { class: "state empty" }, "Unknown view."), title: "Not found", match: null, params, pathPart };
}

function navigate(hash) {
  if (typeof hash !== "string" || !hash.startsWith("#")) return;
  location.hash = hash;
}

function renderNav(host, activePath) {
  host.replaceChildren(...NAV.map(([href, label, key]) => {
    const on = activePath === href || (href !== "#/" && activePath.startsWith(href));
    return el("button", {
      class: `navb ${on ? "on" : ""}`, type: "button", "data-href": href,
      "aria-current": on ? "page" : null, accesskey: key.toLowerCase(),
      onclick: () => navigate(href),
    }, label);
  }));
}

async function boot() {
  const navHost = document.getElementById("nav");
  const view = document.getElementById("view");
  const title = document.getElementById("view-title");
  const statusEl = document.getElementById("status");
  const search = document.getElementById("search");

  document.getElementById("desk-url").textContent = await deskUrl();

  // Expanding into the extension's own full-tab page. This is the extension's UI, not
  // the web app: the URL is chrome-extension://<id>/panel.html.
  const expand = document.getElementById("expand");
  if (expand) {
    expand.addEventListener("click", () => {
      chrome.tabs.create({ url: chrome.runtime.getURL("panel.html") + (location.hash || "#/") });
    });
  }

  search.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = search.querySelector("input").value.trim();
    if (q) navigate(`#/search?q=${encodeURIComponent(q)}`);
  });

  async function refreshStatus() {
    try {
      const desk = await api.desk();
      statusEl.textContent = `desk live · ${desk.human} need human · auto-clear ${desk.cleared}`;
      statusEl.className = "status ok";
      chrome.runtime.sendMessage({ op: "badge", human: desk.human, cleared: desk.cleared });
    } catch (err) {
      // Say which failure it is. "desk offline" for a 401 sent a real debugging session
      // down the wrong path: the desk was up, reachable and answering — it just had no
      // token to identify the extension with.
      const kind = err && err.kind;
      statusEl.textContent =
        kind === "unauthenticated" ? "desk needs a token · options → paste it"
        : kind === "forbidden" ? "desk refused this token"
        : kind === "timeout" ? "desk did not answer"
        : "desk offline";
      statusEl.className = "status err";
    }
  }

  let token = 0;
  async function render() {
    const { build, title: t, match, params, pathPart } = currentRoute();
    const mine = ++token;
    renderNav(navHost, pathPart);
    title.textContent = t;
    view.replaceChildren(loading(t.toLowerCase()));
    const state = makeState(params, (next) => {
      const s = next.toString();
      navigate(pathPart + (s ? `?${s}` : ""));
    });
    try {
      const node = await build(navigate, state, match);
      if (mine !== token) return; // a newer navigation won
      view.replaceChildren(node);
      view.scrollTop = 0;
      const focusable = view.querySelector("input, button, a, [tabindex]");
      if (focusable && document.activeElement === document.body) focusable.focus();
    } catch (err) {
      if (mine !== token) return;
      view.replaceChildren(errorState(err, render));
    }
  }

  window.addEventListener("hashchange", render);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && location.hash && location.hash !== "#/") history.back();
  });

  await refreshStatus();
  await render();
}

boot();
