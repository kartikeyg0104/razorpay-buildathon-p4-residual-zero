(function () {
  "use strict";

  // ---------------------------------------------------------------- page bindings
  // Everything in here is re-run after a client-side navigation, because the swapped
  // markup carries new nodes. State that must not survive a page change lives here too.

  let klass = "";

  function bindFilter() {
    const table = document.querySelector("[data-table]");
    const search = document.querySelector("[data-filter]");
    const chips = document.querySelectorAll("[data-chip]");
    const countEl = document.querySelector("[data-visible]");

    function apply() {
      if (!table) return;
      const q = (search && search.value ? search.value : "").trim().toLowerCase();
      let n = 0;
      const nodes = table.querySelectorAll("tbody tr");
      const rows = nodes.length ? nodes : table.querySelectorAll("[data-search]");
      rows.forEach(function (row) {
        const hay = (row.getAttribute("data-search") || "").toLowerCase();
        const rowClass = row.getAttribute("data-class") || "";
        const ok =
          (!q || hay.indexOf(q) !== -1) &&
          (!klass || (" " + rowClass + " ").indexOf(" " + klass + " ") !== -1);
        row.classList.toggle("hidden", !ok);
        if (ok) n += 1;
      });
      if (countEl) countEl.textContent = String(n);
    }

    if (search) search.addEventListener("input", apply);
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        const value = chip.getAttribute("data-chip") || "";
        klass = klass === value ? "" : value;
        chips.forEach(function (c) {
          const v = c.getAttribute("data-chip") || "";
          c.classList.toggle("on", v === klass);
        });
        apply();
      });
    });
    apply();
  }

  function bindCopy(triggerSel, sourceSel, idleLabel) {
    const btn = document.querySelector(triggerSel);
    if (!btn) return;
    btn.addEventListener("click", function () {
      const block = document.querySelector(sourceSel);
      if (!block) return;
      navigator.clipboard.writeText(block.textContent || "").then(function () {
        btn.textContent = "copied";
        setTimeout(function () {
          btn.textContent = idleLabel;
        }, 1200);
      });
    });
  }

  function bindResolve() {
    document.querySelectorAll("[data-resolve]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const id = btn.getAttribute("data-id");
        const resolution = btn.getAttribute("data-resolve");
        if (!id || !resolution) return;
        fetch(
          "/exceptions/" + encodeURIComponent(id) + "/resolve?resolution=" +
            encodeURIComponent(resolution),
          { method: "POST" }
        )
          .then(function (res) { return res.text(); })
          .then(function (html) {
            const note = document.querySelector("[data-resolve-note]");
            if (note) note.innerHTML = html;
            btn.textContent = resolution + " · saved";
          });
      });
    });
  }

  function bindWorkSave() {
    const workSave = document.querySelector("[data-work-save]");
    if (!workSave) return;
    workSave.addEventListener("click", function () {
      const id = workSave.getAttribute("data-id");
      if (!id) return;
      const assigneeEl = document.querySelector("[data-work-assignee]");
      const noteEl = document.querySelector("[data-work-note]");
      const statusEl = document.querySelector("[data-work-status]");
      const assignee = assigneeEl && "value" in assigneeEl ? assigneeEl.value : "";
      const note = noteEl && "value" in noteEl ? noteEl.value : "";
      const status = statusEl && "value" in statusEl ? statusEl.value : "open";
      fetch(
        "/exceptions/" + encodeURIComponent(id) + "/work?assignee=" +
          encodeURIComponent(assignee) + "&note=" + encodeURIComponent(note) +
          "&status=" + encodeURIComponent(status),
        { method: "POST" }
      )
        .then(function (res) { return res.text(); })
        .then(function (html) {
          const out = document.querySelector("[data-work-note-out]");
          if (out) out.innerHTML = html;
          workSave.textContent = "saved";
          setTimeout(function () {
            workSave.textContent = "save work";
          }, 1200);
        });
    });
  }

  function bindEvidenceToggle() {
    document.querySelectorAll("[data-evidence-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const drawer = document.querySelector("[data-evidence-drawer]");
        if (!drawer) return;
        drawer.hidden = !drawer.hidden;
      });
    });
  }

  function bindAiAsk() {
    document.querySelectorAll("[data-ai-ask]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const id = btn.getAttribute("data-id") || "";
        const question =
          btn.getAttribute("data-q") || "Why wasn't this transaction cleared?";
        const out = document.querySelector("[data-ai-out]");
        if (!out) return;
        out.hidden = false;
        out.textContent = "Loading structured evidence…";
        fetch("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: question, credit_id: id }),
        })
          .then(function (res) { return res.json(); })
          .then(function (got) {
            const mode = got.llm_used ? "LLM explanation" : "fallback template";
            const checks = (got.checks || [])
              .map(function (c) { return (c.ok ? "✓ " : "✗ ") + c.label + ": " + c.value; })
              .join("\n");
            const steps = (got.investigation_steps || [])
              .map(function (s) {
                const ms = s.duration != null ? Math.max(0, Math.round(Number(s.duration) / 1e6)) : null;
                const ids = (s.evidence_ids || []).join(",");
                return (
                  (s.ok ? "✓ " : "✗ ") + "Step " + s.n +
                  " · " + (s.label || s.tool) +
                  (s.tool ? " [" + s.tool + "]" : "") +
                  (ms != null ? " " + ms + "ms" : "") +
                  (ids ? " evidence=" + ids : "")
                );
              })
              .join("\n");
            out.textContent = [
              "AI investigated transaction " + id,
              "USER → INTENT → INVESTIGATION → TOOLS → OBSERVATIONS → EVIDENCE → DETERMINISTIC VALIDATION → FINAL RESPONSE",
              "",
              "AI INVESTIGATION TRACE",
              steps || "(single-step)",
              "",
              "CONCLUSION (" + mode + ")",
              got.answer || "",
              "",
              "EVIDENCE",
              checks || "(see View evidence)",
              "",
              "Deterministic engine established: " + (got.decision || "—"),
              "DECISION STATE: " + (got.decision || "—"),
              "NEXT BEST ACTION: " + (got.recommended_action || "—"),
              "writes_cleared=" + String(got.writes_cleared === true),
            ].join("\n");
          })
          .catch(function () {
            out.textContent = "The AI finance controller could not reach /api/ask.";
          });
      });
    });
  }

  function bindPage() {
    klass = "";
    bindFilter();
    bindCopy("[data-copy]", "pre.proof", "copy proof");
    bindCopy("[data-copy-dispute]", "[data-dispute]", "copy draft");
    bindResolve();
    bindWorkSave();
    bindEvidenceToggle();
    bindAiAsk();
  }

  // ------------------------------------------------------------ client-side router
  // Sidebar and in-page links swap the main region instead of reloading the document.
  // Downloads, external links, new-tab clicks and hash links keep native behaviour.

  const DOWNLOAD_SUFFIXES = [".zip", ".csv", ".md", ".tally", ".json", ".png", ".pdf"];

  function isSwappable(anchor, ev) {
    if (!anchor || ev.defaultPrevented) return false;
    if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return false;
    if (anchor.hasAttribute("download") || anchor.hasAttribute("data-no-swap")) return false;
    const target = anchor.getAttribute("target");
    if (target && target !== "_self") return false;
    const href = anchor.getAttribute("href") || "";
    if (!href || href.charAt(0) === "#") return false;
    let url;
    try {
      url = new URL(anchor.href, window.location.href);
    } catch (err) {
      return false;
    }
    if (url.origin !== window.location.origin) return false;
    const path = url.pathname.toLowerCase();
    for (let i = 0; i < DOWNLOAD_SUFFIXES.length; i += 1) {
      if (path.endsWith(DOWNLOAD_SUFFIXES[i])) return false;
    }
    // API and docs surfaces are not page shells.
    if (path.startsWith("/api/") || path === "/docs" || path === "/redoc" || path === "/metrics") {
      return false;
    }
    return true;
  }

  let navToken = 0;

  function swapIn(doc) {
    const nextMain = doc.querySelector("main.main");
    const currentMain = document.querySelector("main.main");
    if (!nextMain || !currentMain) return false;
    currentMain.replaceWith(nextMain);
    // The server decides the active item and which nav groups are open, so take its nav.
    const nextNav = doc.querySelector("nav.nav");
    const currentNav = document.querySelector("nav.nav");
    if (nextNav && currentNav) currentNav.replaceWith(nextNav);
    if (doc.title) document.title = doc.title;
    return true;
  }

  function navigate(href, push) {
    const token = ++navToken;
    const shell = document.querySelector(".main");
    if (shell) shell.setAttribute("aria-busy", "true");
    return fetch(href, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "residual-zero-console" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("status " + res.status);
        const type = res.headers.get("content-type") || "";
        if (type.indexOf("text/html") === -1) throw new Error("not html");
        return res.text();
      })
      .then(function (html) {
        if (token !== navToken) return;
        const doc = new DOMParser().parseFromString(html, "text/html");
        if (!swapIn(doc)) throw new Error("no main region");
        if (push) window.history.pushState({ rz: true }, "", href);
        window.scrollTo(0, 0);
        bindPage();
        const heading = document.querySelector("main.main h1");
        if (heading) {
          heading.setAttribute("tabindex", "-1");
          heading.focus({ preventScroll: true });
        }
      })
      .catch(function () {
        // Any doubt at all falls back to a real navigation rather than a broken view.
        window.location.href = href;
      })
      .then(function () {
        const el = document.querySelector(".main");
        if (el) el.removeAttribute("aria-busy");
      });
  }

  function go(href) {
    navigate(href, true);
  }

  document.addEventListener("click", function (ev) {
    const anchor = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
    if (!isSwappable(anchor, ev)) return;
    const url = new URL(anchor.href, window.location.href);
    if (url.pathname === window.location.pathname && url.search === window.location.search) {
      return; // same page; let the hash or default behaviour stand
    }
    ev.preventDefault();
    go(url.pathname + url.search + url.hash);
  });

  window.addEventListener("popstate", function () {
    navigate(window.location.pathname + window.location.search, false);
  });

  // ------------------------------------------------------------------ global chrome
  // Bound once. These nodes live outside the swapped region.

  const palette = document.getElementById("palette");
  const scrim = document.getElementById("palette-scrim");

  function paletteOpen() {
    return !!(palette && palette.classList.contains("is-open"));
  }

  function setPalette(open) {
    if (!palette) return;
    palette.classList.toggle("is-open", open);
    palette.setAttribute("aria-hidden", open ? "false" : "true");
    if (scrim) {
      scrim.classList.toggle("is-open", open);
      scrim.setAttribute("aria-hidden", open ? "false" : "true");
    }
    if (open) {
      const q = document.getElementById("palette-q");
      if (q) window.setTimeout(function () { q.focus(); }, 40);
    }
  }

  if (scrim) {
    scrim.addEventListener("click", function () { setPalette(false); });
  }

  document.addEventListener("keydown", function (ev) {
    const tag = (ev.target && ev.target.tagName) || "";
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault();
      setPalette(!paletteOpen());
      return;
    }
    if (ev.key === "Escape" && paletteOpen()) {
      setPalette(false);
      return;
    }
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const search = document.querySelector("[data-filter]");
    if (ev.key === "/" && search) {
      ev.preventDefault();
      search.focus();
      return;
    }
    if (ev.key === "j" || ev.key === "k") {
      const next = document.querySelector(ev.key === "j" ? "[data-next]" : "[data-prev]");
      if (next && next.getAttribute("href")) go(next.getAttribute("href"));
      return;
    }
    if (ev.key === "b") go("/");
    if (ev.key === "m") go("/close");
    if (ev.key === "q") go("/exceptions");
    if (ev.key === "a") go("/audit");
  });

  (function paletteList() {
    const root = document.getElementById("palette");
    const input = document.getElementById("palette-q");
    const list = document.getElementById("palette-list");
    if (!root || !input || !list) return;
    const pages = [
      { id: "Demo tour", href: "/demo", extra: "pitch" },
      { id: "Mixed uniqueness", href: "/mixed", extra: "UNIQUE AMBIGUOUS NONE_FOUND constructed" },
      { id: "Proof explorer twins", href: "/proof/crd_mix_ambiguous_twins", extra: "two explanations" },
      { id: "Proof explorer official", href: "/proof/crd_001_acc_01_2025-01-09", extra: "59645.39 AMBIGUOUS" },
      { id: "Evidence", href: "/evidence", extra: "arms" },
      { id: "Challenge", href: "/challenge", extra: "fixtures" },
      { id: "Safety", href: "/safety", extra: "pii" },
      { id: "Batch", href: "/", extra: "close" },
      { id: "Month-end close", href: "/close", extra: "cash-bridge tax radar exposure standup" },
      { id: "Standup", href: "/standup.md", extra: "close-day briefing" },
      { id: "Close zip", href: "/close.zip", extra: "certificate exceptions" },
      { id: "Queue", href: "/exceptions", extra: "exceptions" },
      { id: "Audit", href: "/audit", extra: "hash" },
      { id: "AI controller", href: "/ask", extra: "finance Q&A" },
      { id: "Explorer", href: "/explorer", extra: "recoverable queue" },
      { id: "What-if", href: "/whatif", extra: "f43" },
      { id: "Books", href: "/books", extra: "f33" },
      { id: "Journal", href: "/journal", extra: "f40" },
      { id: "Clusters", href: "/clusters", extra: "f37" },
      { id: "Controller", href: "/controller", extra: "leakage" },
      { id: "As-of", href: "/asof", extra: "f46" },
      { id: "Alts", href: "/alts", extra: "f36 rivals" },
      { id: "Human study", href: "/human", extra: "f56" },
      { id: "Recon", href: "/recon", extra: "mcp razorpay" },
      { id: "Extension", href: "/extension", extra: "chrome" },
      { id: "MIXED_N_M proof", href: "/credit/crd_001_acc_01_2025-01-09", extra: "59,645.39" },
    ];
    let extra = [];
    fetch("/api/credits")
      .then(function (r) { return r.json(); })
      .then(function (rows) { extra = rows || []; })
      .catch(function () { extra = []; });
    function render() {
      const q = input.value.trim().toLowerCase();
      const hits = pages
        .concat(
          extra.map(function (c) {
            return { id: c.id, href: c.href, extra: (c.amount || "") + " " + (c.cls || "") };
          })
        )
        .filter(function (item) {
          if (!q) return true;
          return (item.id + " " + (item.extra || "")).toLowerCase().indexOf(q) !== -1;
        })
        .slice(0, 12);
      list.innerHTML = hits
        .map(function (item) {
          return (
            '<a href="' + item.href + '"><span>' + item.id + "</span><small>" +
            (item.extra || "") + "</small></a>"
          );
        })
        .join("");
    }
    input.addEventListener("input", render);
    input.addEventListener("focus", render);
    list.addEventListener("click", function () { setPalette(false); });
  })();

  bindPage();
})();
