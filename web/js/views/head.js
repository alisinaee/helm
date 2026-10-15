// Head screen (R7.31 H8, docs/HEAD-SPEC.md sections 5 and 10). One row per logged message on the shared row grid
// (UI rule 0): the header uses the same tracks, numbers sit right-aligned, the copy and menu buttons stay at the
// right edge. It renders the snapshot the server folds (head: {now, prev, counts, rows}) and sends nothing by itself.
// Filters and the open row live in the page hash (#head?f=open&id=H12), so each view is a deep link.
// Every value goes through esc(); the only commands are head.accept, head.set and the copy button.

import { esc } from "../dom.js";
import { MISSING, fmtPercent } from "../format.js";
import { copyButton } from "../ref.js";
import { run } from "../cmd.js";
import { showToast } from "./toast.js";

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

function boundHtml(links) {
  const list = Array.isArray(links) ? links : [];
  const chips = list.slice(0, BOUND_MAX).map(function (ref) {
    const label = String(ref).split(":").pop();
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
    '" data-status="declined">Decline</button></div></details>';
  const row1 = '<div class="row-grid hd-row" data-id="' + esc(id) + '">' +
    '<button type="button" class="hd-c hd-chev" aria-expanded="' + (open ? "true" : "false") +
    '" aria-controls="hd-p-' + esc(id) + '" data-action="head-toggle" data-id="' + esc(id) + '" aria-label="' +
    esc((open ? "Hide " : "Show ") + id) + '">' + (open ? "▾" : "▸") + "</button>" +
    '<span class="hd-c hd-id">' + esc(id) + "</span>" +
    '<span class="hd-c hd-kind">' + esc(row.kind || "") + "</span>" +
    '<span class="hd-c hd-sum rg-t" title="' + esc(row.sum || "") + '">' + esc(row.sum || "") + "</span>" +
    '<span class="hd-c hd-bound">' + boundHtml(row.links) + (row.more ? ' <span class="chip chip-neutral">+' +
      esc(row.more) + "</span>" : "") + "</span>" +
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
  const textHtml = text ? '<pre class="hd-text">' + esc(text) + "</pre>" +
    '<button type="button" class="btn hd-showall" data-action="head-text">Show all</button>' : "";
  return '<div class="hd-panel" id="hd-p-' + esc(id) + '"' + (open ? "" : " hidden") + ">" + textHtml +
    (hist ? '<p class="hd-hist">' + esc(hist) + "</p>" : "") +
    (actions.length ? '<div class="hd-acts">' + actions.join("") + "</div>" : "") + "</div>";
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
    }
  });
  main.addEventListener("change", function (event) {
    const el = event.target;
    const bar = el && el.closest ? el.closest(".hd-bar") : null;
    const key = el && el.getAttribute ? el.getAttribute("data-field") : null;
    if (!bar || !key) return;
    window.location.hash = setField(bar, key, el.value || "").slice(1);
  });
}
