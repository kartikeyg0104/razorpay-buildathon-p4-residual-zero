"use strict";

const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "NOSCRIPT", "CODE"]);
const TOKEN = /\b(crd_[A-Za-z0-9_\-]+|setlod_[A-Za-z0-9_]+|setl_[A-Za-z0-9_]+)\b/g;

/**
 * A chip opens the EXTENSION's own view for the token. It never navigates the user to the
 * desk web app: the service worker resolves these to chrome-extension://<id>/panel.html.
 * Settlement ids (setlod_ / setl_) land on the extension's data-sources view, where
 * fetch_instant_settlement_with_id / fetch_settlement_with_id are read-only MCP tools.
 */
function messageFor(token) {
  if (token.indexOf("crd_") === 0) return { op: "open-credit", id: token };
  return { op: "open-settlement", id: token };
}

function wrap(node) {
  const text = node.nodeValue;
  if (!text || !TOKEN.test(text)) return;
  TOKEN.lastIndex = 0;
  const frag = document.createDocumentFragment();
  let last = 0;
  let match;
  while ((match = TOKEN.exec(text))) {
    if (match.index > last) {
      frag.appendChild(document.createTextNode(text.slice(last, match.index)));
    }
    const token = match[0];
    const wrapEl = document.createElement("span");
    wrapEl.className = "rz-id";
    wrapEl.appendChild(document.createTextNode(token));
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "rz-chip";
    btn.textContent = "0";
    btn.title = "Open in the Residual Zero extension";
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      chrome.runtime.sendMessage(messageFor(token));
    });
    wrapEl.appendChild(btn);
    frag.appendChild(wrapEl);
    last = match.index + token.length;
  }
  if (last < text.length) {
    frag.appendChild(document.createTextNode(text.slice(last)));
  }
  node.parentNode.replaceChild(frag, node);
}

function walk(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: function (node) {
      const parent = node.parentElement;
      if (!parent || SKIP.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
      if (parent.closest(".rz-id, .rz-chip")) return NodeFilter.FILTER_REJECT;
      TOKEN.lastIndex = 0;
      return TOKEN.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  const nodes = [];
  let current;
  while ((current = walker.nextNode())) nodes.push(current);
  nodes.forEach(wrap);
}

if (document.body) walk(document.body);
