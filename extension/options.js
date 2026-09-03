"use strict";
/**
 * Options: which desk, and which token.
 *
 * The token is the user's own personal access token, minted on the desk's `/tokens` page.
 * Nothing here is shipped with the extension — this page is where a credential enters, and
 * it never leaves except as an `Authorization` header to the desk the user named.
 *
 * Host permission for a deployed desk is requested at this point rather than granted at
 * install: the manifest asks only for loopback up front, and `optional_host_permissions`
 * lets the user grant exactly the one origin they entered. `permissions.request` needs a
 * user gesture, and a form submit is one.
 */
import { DEFAULT_DESK, LOOPBACK, deskConfig, normaliseDesk, saveDeskConfig } from "./lib/api.js";

const deskInput = document.getElementById("desk");
const tokenInput = document.getElementById("token");
const msg = document.getElementById("msg");
const who = document.getElementById("who");

function say(text, ok) {
  msg.textContent = text;
  msg.className = ok ? "muted ok" : "muted warn";
}

deskConfig().then(({ desk, token }) => {
  deskInput.value = desk || DEFAULT_DESK;
  // The stored token is never rendered back. Showing only whether one is set means this
  // page cannot leak the credential to anything that can read the DOM.
  tokenInput.placeholder = token ? "a token is saved — type to replace it" : "rz_pat_…";
});

function requestHostPermission(origin) {
  return new Promise((resolve) => {
    // A loopback development desk is already in the manifest, so it needs no request.
    if (!globalThis.chrome || !chrome.permissions || LOOPBACK.includes(origin)) {
      resolve(true);
      return;
    }
    chrome.permissions.request({ origins: [origin + "/*"] }, (granted) => resolve(!!granted));
  });
}

document.getElementById("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const wanted = deskInput.value.trim();
  const safe = normaliseDesk(wanted);
  if (!safe) {
    say(`${wanted || "(empty)"} is not a usable desk URL — it must be https:// ` +
        "or a loopback development desk.", false);
    return;
  }
  const granted = await requestHostPermission(safe);
  if (!granted) {
    say(`Permission to talk to ${safe} was declined, so nothing was saved.`, false);
    return;
  }
  const typed = tokenInput.value.trim();
  try {
    const stored = await deskConfig();
    await saveDeskConfig(safe, typed || stored.token);
  } catch (err) {
    say(err.message, false);
    return;
  }
  deskInput.value = safe;
  tokenInput.value = "";
  say(`Saved ${safe}.`, true);
  verify();
});

/** Confirm the saved credential works, and name the organisation it reads. */
async function verify() {
  who.textContent = "checking…";
  const { api, DeskError } = await import("./lib/api.js");
  try {
    const session = await api.session();
    if (!session.auth_required) {
      who.textContent = "This desk runs in local single-tenant mode and needs no token.";
      return;
    }
    who.textContent = session.authenticated
      ? `Signed in as ${session.email} · organisation ${session.org_id} · role ${session.role}`
      : "The desk did not recognise this token.";
  } catch (err) {
    who.textContent = err && err.message ? err.message : "Could not reach the desk.";
  }
}

document.getElementById("verify").addEventListener("click", (e) => {
  e.preventDefault();
  verify();
});
