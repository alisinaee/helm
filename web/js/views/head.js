// Head screen (R7.31 H8, docs/HEAD-SPEC.md sections 5 and 10). One row per logged message on the shared row grid
// (UI rule 0): the header uses the same tracks, numbers sit right-aligned, the copy and menu buttons stay at the
// right edge. It renders the snapshot the server folds (head: {now, prev, counts, rows}) and sends nothing by itself.
// Filters and the open row live in the page hash (#head?f=open&id=H12), so each view is a deep link.
// Every value goes through esc(); the commands are head.accept, head.set, head.bind, head.split, head.merge (the row
// menu and suggestion buttons, and the forms they open) and the copy button.

import { esc } from "../dom.js";
import { emptyHtml as pageEmpty } from "../dom.js";
import { MISSING, fmtPercent } from "../format.js";
import { copyButton } from "../ref.js";
import { run } from "../cmd.js";
import { buildHash } from "../router.js";
import { showToast } from "./toast.js";
import { pageState } from "./inbox.js";

export const FILTERS = [["open", "Open"], ["unhandled", "Unhandled"], ["doing", "Doing"], ["needs", "Needs you"],
  ["done", "Done"], ["all", "All"]];
const KINDS = ["ask", "decision", "rule", "bug", "preference", "question", "review", "info"];
const STATUS_WORDS = { new: "new", understood: "understood", bound: "bound", doing: "doing", done: "done ✓",
  declined: "declined", "needs-you": "needs you", merged: "merged" };
const STATUS_TONE = { new: "neutral", understood: "neutral", bound: "neutral", doing: "success", done: "success",
  declined: "neutral", "needs-you": "warning", merged: "neutral" };
const CLOSED = ["done", "declined", "merged"];
const UNHANDLED = ["new", "understood"];
const BOUND_MAX = 2;

function rowsOf(vm) {
  const head = vm && vm.head ? vm.head : {};
  return Array.isArray(head.rows) ? head.rows : [];
}

function passes(row, opts) {
  const f = opts.f || "open";
  const st = row.status;
  if (f === "open" && CLOSED.indexOf(st) >= 0) return false;
  if (f === "unhandled" && UNHANDLED.indexOf(st) < 0) return false;
  if (f === "doing" && st !== "doing") return false;
  if (f === "needs" && st !== "needs-you") return false;
  if (f === "done" && st !== "done") return false;
  if (opts.kind && row.kind !== opts.kind) return false;
  if (opts.sid && String(row.acct || row.sid || "") !== opts.sid) return false;
  if (opts.q) {
    const text = (String(row.id) + " " + String(row.sum || "")).toLowerCase();
    if (text.indexOf(String(opts.q).toLowerCase()) < 0) return false;
  }
  return true;
}

// The counts line: the server's counts when present, else the same numbers from the rows it sent.
function countsOf(head, rows) {
  const c = head.counts || {};
  const count = function (test) {
    return rows.filter(test).length;
  };
  return {
    unhandled: c.unhandled != null ? c.unhandled : count(function (r) {
      return UNHANDLED.indexOf(r.status) >= 0;
    }),
    needs: c.needs != null ? c.needs : count(function (r) {
      return r.status === "needs-you";
    }),
    doneUnacc: c.doneUnacc != null ? c.doneUnacc : count(function (r) {
      return r.status === "done" && !r.acc;
    }),
  };
}

function nowHtml(head) {
  const now = head.now || {};
  const usage = now.usage || {};
  const parts = [now.model, now.acct ? "acct " + now.acct : null, now.since ? "since " + now.since : null,
    usage.h5 != null ? "5h " + fmtPercent(usage.h5) : null, usage.wk != null ? "week " + fmtPercent(usage.wk) : null];
  const prev = (head.prev || []).slice(0, 3).map(function (p) {
    return [p.model, p.acct ? "acct " + p.acct : null, p.until ? "until " + p.until : null]
      .filter(Boolean).join(" ");
  });
  return '<section class="hd-now" aria-label="Head now"><p class="hd-now-line">' +
    esc(parts.filter(Boolean).join(" · ") || MISSING) + "</p>" +
    (prev.length ? '<p class="page-note">prev: ' + esc(prev.join(", ")) + "</p>" : "") + "</section>";
}

function alertsHtml(counts) {
  const items = [];
  if (counts.unhandled > 0) {
    items.push('<a class="hd-alert" href="#head?f=unhandled">' + esc(counts.unhandled + " unhandled") +
      " <span>Show</span></a>");
  }
  if (counts.needs > 0) {
    items.push('<a class="hd-alert" href="#head?f=needs">' + esc(counts.needs + " needs you") +
      " <span>Show</span></a>");
  }
  if (counts.doneUnacc > 0) {
    items.push('<a class="hd-alert" href="#head?f=done">' + esc(counts.doneUnacc + " done, not accepted") +
      " <span>Review</span></a>");
  }
  return items.length ? '<nav class="hd-alerts" aria-label="Needs attention">' + items.join("") + "</nav>" : "";
}

function filterHtml(opts) {
  const active = opts.f || "open";
  const links = FILTERS.map(function (pair) {
    const cur = pair[0] === active ? ' aria-current="page"' : "";
    return '<a class="hd-filter" href="' + esc(hashOf({ f: pair[0], kind: opts.kind, sid: opts.sid, q: opts.q })) +
      '"' + cur + ">" + esc(pair[1]) + "</a>";
  });
  return links.join("");
}

// The page hash for one filter state. Empty values are left out, so the hash stays short.
export function hashOf(state) {
  const keys = ["f", "q", "kind", "sid", "id"];
  const parts = [];
  for (const key of keys) {
    if (state[key]) parts.push(key + "=" + encodeURIComponent(String(state[key])));
  }
  return "#head" + (parts.length ? "?" + parts.join("&") : "");
}

function optionsHtml(values, current, allText) {
  return ['<option value=""' + (current ? "" : " selected") + ">" + esc(allText) + "</option>"]
    .concat(values.map(function (v) {
      return '<option value="' + esc(v) + '"' + (v === current ? " selected" : "") + ">" + esc(v) + "</option>";
    })).join("");
}

function barHtml(vm, opts) {
  const accts = [];
  for (const row of rowsOf(vm)) {
    const label = String(row.acct || row.sid || "");
    if (label && accts.indexOf(label) < 0) accts.push(label);
  }
  return '<div class="hd-bar" data-f="' + esc(opts.f || "open") + '">' +
    '<label class="hd-search"><span class="hd-lbl">Search</span><input type="search" data-field="q" value="' +
    esc(opts.q || "") + '" placeholder="/ search" aria-label="Search the log"></label>' +
    '<label class="hd-sel"><span class="hd-lbl">Kind</span><select data-field="kind">' +
    optionsHtml(KINDS, opts.kind, "all") + "</select></label>" +
    '<label class="hd-sel"><span class="hd-lbl">Session</span><select data-field="sid">' +
    optionsHtml(accts, opts.sid, "all") + "</select></label>" +
    '<button type="button" class="btn hd-log" data-action="head-log">+ Log</button>' +
    '<nav class="hd-filters" aria-label="Filter">' + filterHtml(opts) + "</nav></div>";
}

function ageText(minutes) {
  if (typeof minutes !== "number" || !isFinite(minutes)) return MISSING;
  if (minutes < 60) return Math.max(0, Math.round(minutes)) + "m";
  if (minutes < 1440) return Math.floor(minutes / 60) + "h";
  return Math.floor(minutes / 1440) + "d";
}

// The section that shows each linked kind; the ref's id is the item selected there. Other kinds stay plain chips.
const LINK_SECTION = { task: "work", issue: "issues", job: "agents", rule: "rules" };
const ITEM_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$/;

// The hash a bound-to chip opens: the item in its section (ask: this screen, on that entry), or "" for no link.
function refHref(ref, pid) {
  const at = String(ref).indexOf(":");
  const kind = at > 0 ? String(ref).slice(0, at) : "";
  const id = at > 0 ? String(ref).slice(at + 1) : "";
  if (!ITEM_ID.test(id)) return "";
  if (kind === "ask") return hashOf({ id: id });
  const section = LINK_SECTION[kind];
  if (!section) return "";
  return pid ? buildHash({ name: "project", id: pid, section: section, item: id }) : "#/all/" + section;
}

function boundHtml(links, pid) {
  const list = Array.isArray(links) ? links : [];
  const chips = list.slice(0, BOUND_MAX).map(function (ref) {
    const label = String(ref).split(":").pop();
    const href = refHref(ref, pid);
    if (href) {
      return '<a class="chip chip-neutral" href="' + esc(href) + '" title="' + esc(ref) + '">' + esc(label) + "</a>";
    }
    return '<span class="chip chip-neutral" title="' + esc(ref) + '">' + esc(label) + "</span>";
  });
  if (list.length > BOUND_MAX) chips.push('<span class="chip chip-neutral">+' + (list.length - BOUND_MAX) + "</span>");
  return chips.join("");
}

function statusHtml(row) {
  const st = row.status;
  if (st === "done" && row.auto) {
    return '<span class="chip chip-neutral hd-outline" title="Auto-done: waiting for the person">done?</span>';
  }
  return '<span class="chip chip-' + esc(STATUS_TONE[st] || "neutral") + '">' + esc(STATUS_WORDS[st] || st) +
    "</span>";
}

function rowHtml(vm, row, opts) {
  const id = String(row.id);
  const open = opts.id === id;
  const pid = opts.project || null;
  const acc = row.acc === true;
  const carried = row.carried ? ' <span class="hd-carried" title="Carried over">↺</span>' : "";
  const accCell = opts.readOnly ? '<span class="hd-c hd-acc-cell">' + (acc ? "✓" : MISSING) + "</span>" :
    '<span class="hd-c hd-acc-cell"><button type="button" class="hd-acc" role="checkbox" aria-checked="' +
    (acc ? "true" : "false") + '" aria-label="' + esc("Accepted, " + id) + '" data-action="head-accept" data-id="' +
    esc(id) + '">' + (acc ? "☑" : "☐") + "</button></span>";
  const more = opts.readOnly ? "" : '<details class="hd-c hd-more"><summary aria-label="' + esc("More for " + id) +
    '">⋯</summary><div class="hd-menu">' +
    '<button type="button" class="btn" data-action="head-set" data-id="' + esc(id) +
    '" data-status="needs-you">Needs you</button>' +
    '<button type="button" class="btn" data-action="head-set" data-id="' + esc(id) +
    '" data-status="declined">Decline</button>' +
    '<button type="button" class="btn" data-action="head-form" data-form="bind" data-id="' + esc(id) +
    '">Bind...</button>' +
    '<button type="button" class="btn" data-action="head-form" data-form="split" data-id="' + esc(id) +
    '">Split...</button>' +
    '<button type="button" class="btn" data-action="head-form" data-form="merge" data-id="' + esc(id) +
    '">Merge...</button></div></details>';
  const row1 = '<div class="row-grid hd-row" data-id="' + esc(id) + '">' +
    '<button type="button" class="hd-c hd-chev" aria-expanded="' + (open ? "true" : "false") +
    '" aria-controls="hd-p-' + esc(id) + '" data-action="head-toggle" data-id="' + esc(id) + '" aria-label="' +
    esc((open ? "Hide " : "Show ") + id) + '">' + (open ? "▾" : "▸") + "</button>" +
    '<span class="hd-c hd-id">' + esc(id) + "</span>" +
    '<span class="hd-c hd-kind">' + esc(row.kind || "") + "</span>" +
    '<span class="hd-c hd-sum rg-t" title="' + esc(row.sum || "") + '">' + esc(row.sum || "") + "</span>" +
    '<span class="hd-c hd-bound">' + boundHtml(row.links, opts.project) +
      (row.more ? ' <span class="chip chip-neutral">+' + esc(row.more) + "</span>" : "") + "</span>" +
    '<span class="hd-c hd-status">' + statusHtml(row) + "</span>" +
    '<span class="hd-c hd-age rg-num' + (row.stale ? " hd-stale" : row.amber ? " hd-amber" : "") + '"' +
    (row.stale ? ' title="Stale"' : "") + ">" + esc(ageText(row.age)) + "</span>" +
    '<span class="hd-c hd-s">' + esc(row.acct || row.sid || MISSING) + carried + "</span>" +
    accCell +
    '<span class="hd-c hd-copy">' + copyButton("ask", id, id, { project: pid,
      sum: row.sum || "" }) + "</span>" + more + "</div>";
  return '<li class="hd-item">' + row1 + panelHtml(vm, row, opts, open) + "</li>";
}

// The expanded part: the verbatim text (fetched by the route, passed as vm.head.full), one history line,
// and the person's decisions for a done row. Hidden until the row opens.
function panelHtml(vm, row, opts, open) {
  const id = String(row.id);
  const full = vm && vm.head && vm.head.full && vm.head.full.id === id ? vm.head.full : null;
  const text = full && full.text ? full.text : "";
  const hist = full && Array.isArray(full.history) ? full.history.join(" · ") : "";
  const actions = [];
  if (!opts.readOnly && row.status === "done" && !row.acc) {
    actions.push('<button type="button" class="btn" data-action="head-accept" data-id="' + esc(id) +
      '">Confirm done</button>');
  }
  if (!opts.readOnly && row.status === "done") {
    actions.push('<button type="button" class="btn" data-action="head-reopen" data-id="' + esc(id) +
      '">Reopen</button>');
  }
  // Suggestions from the snapshot: a duplicate (row.dup = {id, score}) and up to two bind refs (row.suggest).
  if (!opts.readOnly && row.dup && row.dup.id) {
    actions.push('<button type="button" class="btn" data-action="head-merge" data-id="' + esc(id) +
      '" data-into="' + esc(row.dup.id) + '">Merge into ' + esc(row.dup.id) + " (dup " + esc(row.dup.score) +
      ")</button>");
  }
  if (!opts.readOnly && Array.isArray(row.suggest)) {
    row.suggest.slice(0, 2).forEach(function (ref) {
      actions.push('<button type="button" class="btn" data-action="head-bind-sug" data-id="' + esc(id) +
        '" data-ref="' + esc(ref) + '">Bind ' + esc(ref) + "</button>");
    });
  }
  const textHtml = text ? '<pre class="hd-text">' + esc(text) + "</pre>" +
    '<button type="button" class="btn hd-showall" data-action="head-text">Show all</button>' : "";
  const forms = opts.readOnly ? "" : formsHtml(id);
  return '<div class="hd-panel" id="hd-p-' + esc(id) + '"' + (open ? "" : " hidden") + ">" + textHtml +
    (hist ? '<p class="hd-hist">' + esc(hist) + "</p>" : "") +
    (actions.length ? '<div class="hd-acts">' + actions.join("") + "</div>" : "") + forms + "</div>";
}

// The Bind, Split and Merge forms. Hidden until the row menu opens one; the submit listener sends them.
function formsHtml(id) {
  const eid = esc(id);
  return '<form class="hd-form" data-op="head.bind" data-id="' + eid + '" data-form="bind" hidden>' +
    '<label><span class="hd-lbl">Bind to</span><input name="refs" placeholder="task:R7.31" required></label>' +
    '<button type="submit" class="btn">Bind</button></form>' +
    '<form class="hd-form" data-op="head.split" data-id="' + eid + '" data-form="split" hidden>' +
    '<label><span class="hd-lbl">Part 1</span><input name="a" required></label>' +
    '<label><span class="hd-lbl">Part 2</span><input name="b" required></label>' +
    '<button type="submit" class="btn">Split</button></form>' +
    '<form class="hd-form" data-op="head.merge" data-id="' + eid + '" data-form="merge" hidden>' +
    '<label><span class="hd-lbl">Merge into</span><input name="into" placeholder="H9" required></label>' +
    '<button type="submit" class="btn">Merge</button></form>';
}

function headerHtml() {
  return '<div class="row-grid hd-row hd-head rg-head" aria-hidden="true">' +
    '<span class="hd-c"></span><span class="hd-c">ID</span><span class="hd-c">Kind</span>' +
    '<span class="hd-c">Summary</span><span class="hd-c">Bound to</span><span class="hd-c">Status</span>' +
    '<span class="hd-c hd-age">Age</span><span class="hd-c">S</span><span class="hd-c">Acc</span>' +
    '<span class="hd-c">Ref</span><span class="hd-c"></span></div>';
}

function emptyHtml(vm, opts) {
  const none = rowsOf(vm).length === 0;
  if (none) {
    return '<div class="hd-empty"><p>Nothing logged yet. Every message you type is logged here.</p>' +
      '<button type="button" class="btn" data-action="head-log">+ Log</button></div>';
  }
  return '<div class="hd-empty"><p>Nothing in this view.</p><a class="btn" href="' +
    esc(hashOf({ f: "all" })) + '">Show all</a></div>';
}

// The whole screen for one view model. opts: {f, q, kind, sid, id (open row), project, readOnly}.
export function headHtml(vm, opts) {
  const o = opts || {};
  const head = vm && vm.head ? vm.head : {};
  const rows = rowsOf(vm).filter(function (row) {
    return passes(row, o);
  });
  const counts = countsOf(head, rowsOf(vm));
  const body = rows.length ? '<ul class="hd-list" aria-label="Logged messages">' +
    headerHtml() + rows.map(function (row) {
      return rowHtml(vm, row, o);
    }).join("") + "</ul>" : emptyHtml(vm, o);
  return '<section class="hd-screen" data-project="' + esc(o.project || "") + '" aria-labelledby="hd-h">' +
    '<h2 id="hd-h" class="hd-title">Head</h2>' + nowHtml(head) + alertsHtml(counts) + barHtml(vm, o) + body +
    "</section>";
}

function projectOf(btn) {
  const screen = btn.closest ? btn.closest(".hd-screen") : null;
  return screen && screen.getAttribute("data-project") ? screen.getAttribute("data-project") : null;
}

function setField(bar, key, value) {
  const f = bar.getAttribute("data-f") || "open";
  const state = { f: f, q: "", kind: "", sid: "" };
  for (const el of bar.querySelectorAll("[data-field]")) {
    state[el.getAttribute("data-field")] = el.value || "";
  }
  state[key] = value;
  return hashOf(state);
}

let listening = false;

// Wires the row buttons, the open-row toggle and the search and select fields. Call once after the screen renders.
export function attachHeadListeners() {
  if (listening || typeof document === "undefined") return;
  const main = document.getElementById("main");
  if (!main) return;
  listening = true;
  main.addEventListener("click", function (event) {
    // Filter, alert and ask-chip links keep the project scope: their hash is rewritten before the browser follows it.
    const link = event.target && event.target.closest ? event.target.closest("a[href^='#head']") : null;
    if (link) {
      const pid = projectOf(link);
      if (pid) {
        event.preventDefault();
        window.location.hash = scopedHash(link.getAttribute("href"), pid);
      }
      return;
    }
    const btn = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!btn) return;
    const action = btn.getAttribute("data-action");
    const id = btn.getAttribute("data-id");
    const project = projectOf(btn);
    if (action === "head-toggle") {
      const panel = document.getElementById("hd-p-" + id);
      if (!panel) return;
      panel.hidden = !panel.hidden;
      btn.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
    } else if (action === "head-text") {
      const pre = btn.parentNode.querySelector(".hd-text");
      if (pre) pre.classList.toggle("hd-text-open");
    } else if (action === "head-accept") {
      run("head.accept", { id: id }, { project: project, label: "Accepted " + id });
    } else if (action === "head-reopen") {
      run("head.set", { id: id, set: { status: "open" } }, { project: project, label: "Reopened " + id });
    } else if (action === "head-set") {
      const status = btn.getAttribute("data-status");
      run("head.set", { id: id, set: { status: status } }, { project: project, label: id + " " + status });
    } else if (action === "head-log") {
      showToast({ text: "Type in the chat. Every message is logged here." });
    } else if (action === "head-merge") {
      const into = btn.getAttribute("data-into");
      run("head.merge", { id: id, into: into }, { project: project, label: id + " merged into " + into });
    } else if (action === "head-bind-sug") {
      const ref = btn.getAttribute("data-ref");
      run("head.bind", { id: id, refs: [ref] }, { project: project, label: "Bound " + id + " to " + ref });
    } else if (action === "head-form") {
      // Opens the row and shows one form (a second click on the same menu item hides it).
      const name = btn.getAttribute("data-form");
      const panel = document.getElementById("hd-p-" + id);
      if (!panel) return;
      if (panel.hidden) {
        const chev = document.querySelector('[data-action="head-toggle"][data-id="' + id + '"]');
        if (chev) chev.click();
      }
      for (const form of panel.querySelectorAll(".hd-form")) {
        const show = form.getAttribute("data-form") === name && form.hidden;
        form.hidden = !show;
        const input = show ? form.querySelector("input") : null;
        if (input) input.focus();
      }
      const menu = btn.closest ? btn.closest("details") : null;
      if (menu) menu.open = false;
    }
  });
  main.addEventListener("submit", function (event) {
    const form = event.target;
    const op = form && form.getAttribute ? form.getAttribute("data-op") : null;
    if (!op) return;
    event.preventDefault();
    const id = form.getAttribute("data-id");
    const project = projectOf(form);
    const field = function (name) {
      const el = form.elements.namedItem(name);
      return el ? String(el.value || "").trim() : "";
    };
    if (op === "head.bind") {
      const refs = field("refs").split(",").map(function (ref) {
        return ref.trim();
      }).filter(Boolean);
      run("head.bind", { id: id, refs: refs }, { project: project, label: "Bound " + id });
    } else if (op === "head.split") {
      run("head.split", { id: id, sums: [field("a"), field("b")] }, { project: project, label: "Split " + id });
    } else if (op === "head.merge") {
      run("head.merge", { id: id, into: field("into") }, { project: project, label: id + " merged" });
    }
  });
  main.addEventListener("change", function (event) {
    const el = event.target;
    const bar = el && el.closest ? el.closest(".hd-bar") : null;
    const key = el && el.getAttribute ? el.getAttribute("data-field") : null;
    if (!bar || !key) return;
    window.location.hash = scopedHash(setField(bar, key, el.value || ""), projectOf(el));
  });
}

// The Head hash is project-scoped in the app ("#/p/<id>/head?..."); hashOf() gives the bare "#head?..." form.
function scopedHash(hash, project) {
  return project ? hash.replace(/^#head/, "#/p/" + project + "/head") : hash;
}

// The query of the current page hash, read with the same keys hashOf() writes.
function queryOf() {
  const raw = String(window.location.hash || "");
  const at = raw.indexOf("?");
  return new URLSearchParams(at >= 0 ? raw.slice(at + 1) : "");
}

function pick(value, allowed, max) {
  const text = value == null ? "" : String(value);
  return text && text.length <= max && allowed.indexOf(text) >= 0 ? text : "";
}

// The screen for the project route. Head belongs to one project; the snapshot's head key is the only data it reads.
export function sectionView(vm) {
  if (vm.route.name !== "project") {
    return pageEmpty("Head belongs to one project.", '<a href="#/all/overview">Go to All projects</a>');
  }
  const state = pageState(vm);
  if (state) return state;
  attachHeadListeners();
  const params = queryOf();
  const text = params.get("q") || "";
  const sid = params.get("sid") || "";
  const id = params.get("id") || "";
  const opts = {
    f: pick(params.get("f"), FILTERS.map(function (pair) {
      return pair[0];
    }), 20) || "open",
    q: text.length <= 200 ? text : "",
    kind: pick(params.get("kind"), KINDS, 20),
    sid: sid.length <= 60 ? sid : "",
    id: ITEM_ID.test(id) ? id : "",
    project: vm.route.id,
    readOnly: false,
  };
  return headHtml({ head: vm.project.snapshot.head || null }, opts);
}
