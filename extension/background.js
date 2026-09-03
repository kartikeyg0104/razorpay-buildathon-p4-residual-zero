"use strict";
/**
 * Service worker: action badge, context menu, and message routing.
 *
 * Every navigation this worker performs opens the EXTENSION's own panel page
 * (chrome.runtime.getURL). It never opens a desk/web-app URL — looking a credit up from a
 * page context lands in the extension's transaction view, not on the website.
 */

import { api, deskUrl } from "./lib/api.js";

const CREDIT_RE = /^crd_[A-Za-z0-9_\-]{1,120}$/;
const SETTLEMENT_RE = /^(setlod_|setl_)[A-Za-z0-9_\-]{1,120}$/;

function setBadge(human, cleared) {
  const text = cleared === 0 ? String(human || 0) : "!";
  chrome.action.setBadgeText({ text: text.slice(0, 4) });
  chrome.action.setBadgeBackgroundColor({ color: cleared === 0 ? "#f0b429" : "#ff6b7a" });
}

async function refreshBadge() {
  try {
    const desk = await api.desk();
    setBadge(desk.human, desk.cleared);
  } catch {
    chrome.action.setBadgeText({ text: "?" });
    chrome.action.setBadgeBackgroundColor({ color: "#6b7388" });
  }
}

/** Open a route inside the extension's own panel. Never a desk URL. */
function openPanel(hash) {
  const safe = typeof hash === "string" && hash.startsWith("#/") ? hash : "#/";
  chrome.tabs.create({ url: chrome.runtime.getURL("panel.html") + safe });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "rz-lookup",
      title: "Open in Residual Zero",
      contexts: ["selection"],
    });
  });
  refreshBadge();
});

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId !== "rz-lookup") return;
  const selected = String(info.selectionText || "").trim().slice(0, 200);
  const credit = selected.match(/crd_[A-Za-z0-9_\-]+/);
  openPanel(credit ? `#/credit/${encodeURIComponent(credit[0])}`
                   : `#/search?q=${encodeURIComponent(selected)}`);
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Only accept messages from this extension's own pages and content scripts.
  if (!sender || sender.id !== chrome.runtime.id) {
    sendResponse({ ok: false, error: "rejected: foreign sender" });
    return false;
  }
  if (!msg || typeof msg.op !== "string") {
    sendResponse({ ok: false, error: "rejected: malformed message" });
    return false;
  }
  if (msg.op === "badge") {
    setBadge(Number(msg.human) || 0, Number(msg.cleared) || 0);
    sendResponse({ ok: true });
    return false;
  }
  if (msg.op === "open-credit") {
    const id = String(msg.id || "");
    if (!CREDIT_RE.test(id)) {
      sendResponse({ ok: false, error: "rejected: not a credit id" });
      return false;
    }
    openPanel(`#/credit/${encodeURIComponent(id)}`);
    sendResponse({ ok: true });
    return false;
  }
  if (msg.op === "open-settlement") {
    const id = String(msg.id || "");
    if (!SETTLEMENT_RE.test(id)) {
      sendResponse({ ok: false, error: "rejected: not a settlement id" });
      return false;
    }
    openPanel(`#/sources?settlement=${encodeURIComponent(id)}`);
    sendResponse({ ok: true });
    return false;
  }
  sendResponse({ ok: false, error: "rejected: unknown op" });
  return false;
});

chrome.runtime.onStartup.addListener(refreshBadge);
refreshBadge();
