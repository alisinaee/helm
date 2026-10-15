// Head screen (R7.31 H8, docs/HEAD-SPEC.md sections 5 and 10). One row per logged message on the shared row grid
// (UI rule 0): the header sits above the list on the same tracks, numbers are right-aligned, and the copy button
// stays at the right edge. A row is toggled by a stretched button that covers the whole row (keyboard: Enter/Space,
// aria-expanded); the buttons and links in the row sit above it. An open row shows the verbatim text (fetched once
// per row from the read route with full=H.., cached), the history, and a footer with the status, the bound-to chips
// and the actions. The screen renders the snapshot the server folds (head: {now, prev, counts, rows}).
// Filters and the deep-linked open row live in the page hash (#head?f=open&id=H12).
// Every value goes through esc() or textContent; the commands are head.accept, head.set, head.bind, head.split,
// head.merge and the copy button.

import { esc } from "../dom.js";
import { emptyHtml as pageEmpty } from "../dom.js";
import { fmtPercent } from "../format.js";
import { copyButton } from "../ref.js";
import { run } from "../cmd.js";
import { getJson } from "../api.js";
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
const FULL_CONCURRENCY = 3;
const FULL_ID = /^H\d{1,4}$/;
const SORTS = ["new", "old"];
const SUM_SHOW = 240;

// Client state: the verbatim texts fetched so far (key "project\nid"), the requests in flight, the open row ids, and
// the hash row already opened once (so a re-render does not reopen a row the person closed).
const fullCache = new Map();
const inflight = new Map();
const openSet = new Set();
const queue = [];
let active = 0;
let seededId = "";

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
  // The model acting as head, as a badge first on the line; without a claim the line says how to claim one.
  const badge = now.model ? '<strong class="hd-badge">Head: ' + esc(now.model) + "</strong>" :
    '<strong class="hd-badge hd-badge-off">Head: not claimed (run roadmap head claim)</strong>';
  const parts = [now.acct ? "acct " + now.acct : null, now.since ? "since " + now.since : null,
    usage.h5 != null ? "5h " + fmtPercent(usage.h5) : null, usage.wk != null ? "week " + fmtPercent(usage.wk) : null];
  const prev = (head.prev || []).slice(0, 3).map(function (p) {
    return [p.model, p.acct ? "acct " + p.acct : null, p.until ? "until " + p.until : null]
      .filter(Boolean).join(" ");
  });
  const rest = parts.filter(Boolean).join(" · ");
  return '<section class="hd-now" aria-label="Head now"><p class="hd-now-line">' + badge +
    (rest ? ' <span class="hd-now-rest">' + esc(rest) + "</span>" : "") + "</p>" +
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
    return '<a class="hd-filter" href="' + esc(hashOf({ f: pair[0], kind: opts.kind, sid: opts.sid, q: opts.q,
      sort: opts.sort, view: opts.view })) +
      '"' + cur + ">" + esc(pair[1]) + "</a>";
  });
  return links.join("");
}

// The page hash for one filter state. Empty values are left out, so the hash stays short; the default order
// (sort=new) is left out too.
export function hashOf(state) {
  const keys = ["f", "q", "kind", "sid", "sort", "id", "view"];
  const parts = [];
  for (const key of keys) {
    if (state[key] && !(key === "sort" && state[key] === "new")) {
      parts.push(key + "=" + encodeURIComponent(String(state[key])));
    }
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
  return '<div class="hd-bar" data-f="' + esc(opts.f || "open") + '" data-view="' +
    (opts.view === "cards" ? "cards" : "list") + '">' +
    '<label class="hd-search"><span class="hd-lbl">Search</span><input type="search" data-field="q" value="' +
    esc(opts.q || "") + '" placeholder="/ search" aria-label="Search the log"></label>' +
    '<label class="hd-sel"><span class="hd-lbl">Kind</span><select data-field="kind">' +
    optionsHtml(KINDS, opts.kind, "all") + "</select></label>" +
    '<label class="hd-sel"><span class="hd-lbl">Session</span><select data-field="sid">' +
    optionsHtml(accts, opts.sid, "all") + "</select></label>" +
    '<label class="hd-sel"><span class="hd-lbl">Order</span><select data-field="sort">' +
    '<option value="new"' + (opts.sort === "old" ? "" : " selected") + ">Newest</option>" +
    '<option value="old"' + (opts.sort === "old" ? " selected" : "") + ">Oldest</option></select></label>" +
    '<button type="button" class="btn hd-log" data-action="head-log">+ Log</button>' +
    '<nav class="hd-filters" aria-label="Filter">' + filterHtml(opts) + "</nav>" + viewHtml(opts) + "</div>";
}

// The Cards | List toggle. The hash keeps view=list or view=cards; the default (no view key) is the list.
function viewHtml(opts) {
  const current = opts.view === "cards" ? "cards" : "list";
  const links = [["list", "List"], ["cards", "Cards"]].map(function (pair) {
    const cur = pair[0] === current ? ' aria-current="page"' : "";
    return '<a class="hd-filter hd-view" href="' + esc(hashOf({ f: opts.f || "open", kind: opts.kind, sid: opts.sid,
      q: opts.q, sort: opts.sort, view: pair[0] })) + '"' + cur + ">" + esc(pair[1]) + "</a>";
  });
  return '<nav class="hd-views" aria-label="View">' + links.join("") + "</nav>";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// The local date and time of an entry's ts: "15 Oct 14:32" (full: "15 Oct 2026 14:32"), or MISSING without a ts.
export function whenText(iso, full) {
  const ms = Date.parse(String(iso || ""));
  if (!isFinite(ms)) return "";
  const d = new Date(ms);
  const pad = function (n) {
    return (n < 10 ? "0" : "") + n;
  };
  return d.getDate() + " " + MONTHS[d.getMonth()] + (full ? " " + d.getFullYear() : "") + " " +
    pad(d.getHours()) + ":" + pad(d.getMinutes());
}

function ageText(minutes) {
  if (typeof minutes !== "number" || !isFinite(minutes)) return "";
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

// A bound ref is "kind:id" (a plain string) or the snapshot object {ref, title, status, jobs}; both read the same way.
function linkOf(ref) {
  const obj = ref && typeof ref === "object" ? ref : { ref: ref };
  return { ref: String(obj.ref || ""), title: obj.title ? String(obj.title) : "",
    status: obj.status ? String(obj.status) : "", jobs: Array.isArray(obj.jobs) ? obj.jobs : [] };
}

// The chip tone of a bound task's status: a running or done task is good, a blocked one needs a look.
function taskTone(st) {
  if (st === "done" || st === "doing") return "success";
  return st === "blocked" ? "warning" : "neutral";
}

// The bound-to chips: at most max of them (the closed row shows two), each with its status when the snapshot has
// one, then +n for the rest. An entry with no bound task says so in words.
function boundHtml(links, pid, max) {
  const list = Array.isArray(links) ? links.map(linkOf) : [];
  const limit = max == null ? BOUND_MAX : max;
  if (!list.length) return '<span class="hd-none">Not bound yet</span>';
  const chips = list.slice(0, limit).map(function (link) {
    const label = link.ref.split(":").pop();
    const href = refHref(link.ref, pid);
    const chip = href ? '<a class="chip chip-neutral" href="' + esc(href) + '" title="' + esc(link.ref) + '">' +
      esc(label) + "</a>" : '<span class="chip chip-neutral" title="' + esc(link.ref) + '">' + esc(label) + "</span>";
    const st = link.status ? '<span class="chip chip-' + esc(taskTone(link.status)) + '">' + esc(link.status) +
      "</span>" : "";
    return chip + st;
  });
  if (list.length > limit) chips.push('<span class="chip chip-neutral">+' + (list.length - limit) + "</span>");
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

// The text, history, reply and attachments of one row, as the view keeps them (the text is null on the phone).
function normFull(f) {
  return { text: typeof f.text === "string" ? f.text : null, history: Array.isArray(f.history) ? f.history : [],
    reply: typeof f.reply === "string" && f.reply.trim() ? f.reply : null, assets: assetsOf(f.assets) };
}

// The attachments of one entry: names or paths, as strings or {name|path} objects. Capped at 20; [] when absent.
function assetsOf(list) {
  if (!Array.isArray(list)) return [];
  return list.map(function (a) {
    return String(a && typeof a === "object" ? a.name || a.path || "" : a || "");
  }).filter(Boolean).slice(0, 20);
}

// The verbatim text of one row: the seeded vm.head.full when it is this row, else the fetched cache, else null.
function fullOf(vm, pid, id) {
  const seeded = vm && vm.head && vm.head.full && vm.head.full.id === id ? vm.head.full : null;
  if (seeded) return normFull(seeded);
  return fullCache.get((pid || "") + "\n" + id) || null;
}

// The summary cell: the stored sum, or the first 140 characters of the verbatim text when the stored sum is only a
// short cut of it (older imports kept one clause).
function summaryText(sum, full) {
  const text = full && typeof full.text === "string" ? full.text.split(/\s+/).filter(Boolean).join(" ") : "";
  const stem = String(sum || "").replace(/…$/, "");
  if (!text || text.length <= stem.length) return String(sum || "");
  if (stem.length >= SUM_SHOW || text.indexOf(stem) !== 0) return String(sum || "");
  return text.slice(0, SUM_SHOW) + (text.length > SUM_SHOW ? "…" : "");
}

// Newest first by default (the entry's ts, then its id number); sort "old" reverses it.
function sortRows(rows, sort) {
  const when = function (row) {
    const ms = Date.parse(String(row.ts || ""));
    return isFinite(ms) ? ms : 0;
  };
  const num = function (row) {
    return parseInt(String(row.id).replace(/\D/g, ""), 10) || 0;
  };
  const sorted = rows.slice().sort(function (a, b) {
    return (when(a) - when(b)) || (num(a) - num(b));
  });
  return sort === "old" ? sorted : sorted.reverse();
}

// What the "You wrote" box says: the text, or why there is none (loading, or the phone listener gets no text).
function textNote(full) {
  if (!full) return "Loading the text…";
  if (full.text == null) return "The full text is only on this computer.";
  return full.text;
}

// What the "Head replied" box says: the captured reply, or the placeholder while loading or when none was captured.
function replyNote(full) {
  if (!full) return "Loading the reply…";
  return full.reply || "No reply captured yet";
}

// Why the row is in its state, in words. The snapshot may send a reason; otherwise it is worked out from the status.
function stateReason(row) {
  if (row.reason) return String(row.reason);
  if (row.status === "done") {
    if (row.auto) return "All bound tasks are done; waiting for you to confirm";
    return row.acc ? "Confirmed by you" : "Done; waiting for you to confirm";
  }
  const words = { doing: "A bound task or job is running", "needs-you": "The head asked for you",
    bound: "Bound to a task; not started", declined: "Declined", merged: "Merged into another entry" };
  return words[row.status] || "Not triaged yet";
}

// The "Bound to" block: each bound task with its id (a link to Work), title, status chip and running job model.
function boundBlockHtml(row, pid) {
  const items = (Array.isArray(row.links) ? row.links.map(linkOf) : []).map(function (link) {
    const label = link.ref.split(":").pop();
    const href = refHref(link.ref, pid);
    const idHtml = href ? '<a class="chip chip-neutral" href="' + esc(href) + '" title="' + esc(link.ref) + '">' +
      esc(label) + "</a>" : '<span class="chip chip-neutral">' + esc(label) + "</span>";
    const title = link.title ? '<span class="hd-title">' + esc(link.title) + "</span>" : "";
    const st = link.status ? '<span class="chip chip-' + esc(taskTone(link.status)) + '">' + esc(link.status) +
      "</span>" : "";
    const models = link.jobs.filter(function (j) {
      return j && j.model && j.state !== "done";
    }).map(function (j) {
      return esc(j.model);
    });
    const job = models.length ? '<span class="hd-job">running: ' + models.join(", ") + "</span>" : "";
    return '<li class="hd-link">' + idHtml + title + st + job + "</li>";
  });
  return '<div class="hd-blk"><p class="hd-lbl">Bound to</p>' + (items.length ? '<ul class="hd-links">' +
    items.join("") + "</ul>" : '<p class="hd-none">Not bound yet. Use Bind below.</p>') + "</div>";
}

// The attachments list: shown only when the row has attachments (filled by loadText when the text arrives).
function assetsHtml(full) {
  const list = full ? full.assets : [];
  return '<ul class="hd-assets" data-role="assets"' + (list.length ? "" : " hidden") + ">" +
    list.map(function (name) {
      return '<li class="hd-asset">' + esc(name) + "</li>";
    }).join("") + "</ul>";
}

// The closed row: one line on the fixed tracks (chevron, id, summary, state, bound tasks, age, added, copy).
function rowHtml(vm, row, opts) {
  const id = String(row.id);
  const eid = esc(id);
  const open = (opts.open || []).indexOf(id) >= 0;
  const pid = opts.project || null;
  const carried = row.carried ? ' <span class="hd-carried" title="Carried over">↺</span>' : "";
  const shown = summaryText(row.sum, fullOf(vm, pid, id));
  const line = '<div class="row-grid hd-row" data-id="' + eid + '">' +
    '<button type="button" class="hd-hit" data-action="head-toggle" data-id="' + eid + '" aria-expanded="' +
    (open ? "true" : "false") + '" aria-controls="hd-p-' + eid + '" aria-label="' +
    esc((open ? "Hide " : "Show ") + id) + '"></button>' +
    '<span class="hd-c hd-chev" aria-hidden="true">▸</span>' +
    '<span class="hd-c hd-id">' + eid + carried + "</span>" +
    '<span class="hd-c hd-sum rg-t" data-sum="' + esc(row.sum || "") + '" title="' + esc(shown) + '">' +
    esc(shown) + "</span>" +
    '<span class="hd-c hd-copy">' + copyButton("ask", id, id, { project: pid, sum: row.sum || "" }) + "</span>" +
    '<span class="hd-meta">' +
    '<span class="hd-c hd-status">' + statusHtml(row) + "</span>" +
    '<span class="hd-c hd-bound">' + boundHtml(row.links, pid, BOUND_MAX) + "</span>" +
    '<span class="hd-c hd-age rg-num' + (row.stale ? " hd-stale" : row.amber ? " hd-amber" : "") + '"' +
    (row.stale ? ' title="Stale"' : "") + ">" + esc(ageText(row.age)) + "</span>" +
    '<span class="hd-c hd-when rg-num" title="' + esc(row.ts || "") + '">' + esc(whenText(row.ts)) + "</span>" +
    "</span></div>";
  return '<li class="hd-item' + (open ? " is-open" : "") + '">' + line + panelHtml(vm, row, opts, open) + "</li>";
}

// The opened row: four labelled blocks (You wrote, Head replied, State, Bound to) and the action footer. Hidden until
// the row opens; loadText fills the text, the reply and the attachments once the full route answers.
function panelHtml(vm, row, opts, open) {
  const id = String(row.id);
  const eid = esc(id);
  const pid = opts.project || null;
  const full = fullOf(vm, pid, id);
  const hist = full && full.history.length ? full.history.join(" · ") : "";
  const wrote = '<div class="hd-blk"><p class="hd-lbl">You wrote</p>' +
    '<pre class="hd-text" data-state="' + (full ? "ready" : "loading") + '">' + esc(textNote(full)) + "</pre>" +
    assetsHtml(full) + "</div>";
  const reply = '<div class="hd-blk"><p class="hd-lbl">Head replied</p><pre class="hd-reply">' +
    esc(replyNote(full)) + "</pre></div>";
  const state = '<div class="hd-blk"><p class="hd-lbl">State</p><div class="hd-state">' + statusHtml(row) +
    '<span class="hd-reason">' + esc(stateReason(row)) + "</span></div>" +
    '<p class="hd-added" title="' + esc(row.ts || "") + '">Added ' + esc(whenText(row.ts, true)) + "</p>" +
    '<p class="hd-hist">' + esc(hist) + "</p></div>";
  const acts = [];
  if (!opts.readOnly && row.status === "done" && !row.acc) {
    acts.push('<button type="button" class="btn" data-action="head-accept" data-id="' + eid +
      '">Confirm done</button>');
  }
  if (!opts.readOnly && row.status === "done") {
    acts.push('<button type="button" class="btn" data-action="head-reopen" data-id="' + eid +
      '">Reopen</button>');
  }
  if (!opts.readOnly && row.status !== "needs-you") {
    acts.push('<button type="button" class="btn" data-action="head-set" data-id="' + eid +
      '" data-status="needs-you">Needs you</button>');
  }
  if (!opts.readOnly && row.status !== "declined") {
    acts.push('<button type="button" class="btn" data-action="head-set" data-id="' + eid +
      '" data-status="declined">Decline</button>');
  }
  // Suggestions from the snapshot: a duplicate (row.dup = {id, score}) and up to two bind refs (row.suggest).
  if (!opts.readOnly && row.dup && row.dup.id) {
    acts.push('<button type="button" class="btn" data-action="head-merge" data-id="' + eid +
      '" data-into="' + esc(row.dup.id) + '">Merge into ' + esc(row.dup.id) + " (dup " + esc(row.dup.score) +
      ")</button>");
  }
  if (!opts.readOnly && Array.isArray(row.suggest)) {
    row.suggest.slice(0, 2).forEach(function (ref) {
      acts.push('<button type="button" class="btn" data-action="head-bind-sug" data-id="' + eid +
        '" data-ref="' + esc(ref) + '">Bind ' + esc(ref) + "</button>");
    });
  }
  if (!opts.readOnly) {
    for (const name of ["bind", "split", "merge"]) {
      acts.push('<button type="button" class="btn" data-action="head-form" data-form="' + name + '" data-id="' +
        eid + '">' + esc(name[0].toUpperCase() + name.slice(1)) + "...</button>");
    }
  }
  const foot = acts.length ? '<div class="hd-foot"><div class="hd-acts">' + acts.join("") + "</div></div>" : "";
  const forms = opts.readOnly ? "" : formsHtml(id);
  return '<div class="hd-panel" id="hd-p-' + eid + '"' + (open ? "" : " hidden") + ">" + wrote + reply + state +
    boundBlockHtml(row, pid) + foot + forms + "</div>";
}

// The Bind, Split and Merge forms. Hidden until the footer opens one; the submit listener sends them.
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

// The list view: one table row per entry (columns: # Kind Summary State Bound to Age Added Acc Copy). Each entry is a
// tbody, so the row and its full-width detail row (colspan 9, the same panel as the card) open and close together.
const LIST_COLS = [["#", "hd-n"], ["Kind", "hd-kind"], ["Summary", "hd-sumc"], ["State", "hd-stc"],
  ["Bound to", "hd-bnd"], ["Age", "hd-age"], ["Added", "hd-when"], ["Acc", "hd-acc"], ["Copy", "hd-cp"]];

function listRowHtml(vm, row, opts) {
  const id = String(row.id);
  const eid = esc(id);
  const open = (opts.open || []).indexOf(id) >= 0;
  const pid = opts.project || null;
  const carried = row.carried ? ' <span class="hd-carried" title="Carried over">↺</span>' : "";
  const shown = summaryText(row.sum, fullOf(vm, pid, id));
  const cell = function (cls, html, attrs) {
    return '<td class="' + cls + '"' + (attrs || "") + ">" + html + "</td>";
  };
  const age = cell("hd-age rg-num" + (row.stale ? " hd-stale" : row.amber ? " hd-amber" : ""),
    esc(ageText(row.age)), row.stale ? ' title="Stale"' : "");
  const when = cell("hd-when rg-num", esc(whenText(row.ts)), ' title="' + esc(row.ts || "") + '"');
  const tr = '<tr class="hd-row" data-id="' + eid + '">' +
    cell("hd-n", '<button type="button" class="hd-hit" data-action="head-toggle" data-id="' + eid +
      '" aria-expanded="' + (open ? "true" : "false") + '" aria-controls="hd-p-' + eid + '" aria-label="' +
      esc((open ? "Hide " : "Show ") + id) + '">' + eid + carried + "</button>") +
    cell("hd-kind", '<span class="chip chip-neutral">' + esc(row.kind || "") + "</span>") +
    cell("hd-sumc", '<span class="hd-sum" data-sum="' + esc(row.sum || "") + '" title="' + esc(shown) + '">' +
      esc(shown) + "</span>") +
    cell("hd-stc", statusHtml(row)) +
    cell("hd-bnd", boundHtml(row.links, pid, BOUND_MAX)) +
    age + when +
    cell("hd-acc", row.acc ? '<span aria-label="Accepted" title="Accepted">✓</span>' : "") +
    cell("hd-cp", copyButton("ask", id, id, { project: pid, sum: row.sum || "" })) + "</tr>";
  const detail = '<tr class="hd-detail"><td colspan="9">' + panelHtml(vm, row, opts, open) + "</td></tr>";
  return '<tbody class="hd-item' + (open ? " is-open" : "") + '">' + tr + detail + "</tbody>";
}

function listHtml(vm, rows, opts) {
  const head = LIST_COLS.map(function (col) {
    return '<th scope="col" class="' + col[1] + '">' + esc(col[0]) + "</th>";
  }).join("");
  return '<div class="hd-list hd-tbl-wrap"><table class="hd-tbl" aria-label="Logged messages"><thead><tr>' +
    head + "</tr></thead>" + rows.map(function (row) {
      return listRowHtml(vm, row, opts);
    }).join("") + "</table></div>";
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

// The whole screen for one view model. opts: {f, q, kind, sid, open (ids of the open rows), project, readOnly}.
export function headHtml(vm, opts) {
  const o = opts || {};
  const head = vm && vm.head ? vm.head : {};
  const all = rowsOf(vm);
  const rows = sortRows(all.filter(function (row) {
    return passes(row, o);
  }), o.sort);
  const counts = countsOf(head, all);
  const open = o.open || [];
  const allOpen = rows.length > 0 && rows.every(function (row) {
    return open.indexOf(String(row.id)) >= 0;
  });
  const top = '<div class="hd-top"><h2 id="hd-h" class="hd-title">Head</h2>' +
    (rows.length ? '<button type="button" class="btn hd-all" data-action="head-expand-all">' +
      (allOpen ? "Collapse all" : "Expand all") + "</button>" : "") + "</div>";
  const cards = o.view === "cards";
  const body = !rows.length ? emptyHtml(vm, o) : cards ? '<div class="hd-list">' +
    '<ul class="hd-items" aria-label="Logged messages">' + rows.map(function (row) {
      return rowHtml(vm, row, o);
    }).join("") + "</ul></div>" : listHtml(vm, rows, o);
  return '<section class="hd-screen" data-project="' + esc(o.project || "") + '" aria-labelledby="hd-h">' +
    top + nowHtml(head) + alertsHtml(counts) + barHtml(vm, o) + body + "</section>";
}

function projectOf(el) {
  const screen = el.closest ? el.closest(".hd-screen") : null;
  return screen && screen.getAttribute("data-project") ? screen.getAttribute("data-project") : null;
}

function idOf(item) {
  const row = item.querySelector(".hd-row");
  return row ? row.getAttribute("data-id") || "" : "";
}

// Fetch the verbatim text of one row once: GET .../head?full=Hn (the server gives text only on the same-origin page).
function fetchFull(pid, id) {
  const key = pid + "\n" + id;
  if (fullCache.has(key)) return Promise.resolve(fullCache.get(key));
  if (!inflight.has(key)) {
    const url = "/api/v1/projects/" + encodeURIComponent(pid) + "/head?f=all&n=200&full=" + encodeURIComponent(id);
    const req = getJson(url).then(function (res) {
      const f = res && res.data && res.data.full ? res.data.full : {};
      const entry = normFull(f);
      fullCache.set(key, entry);
      return entry;
    }).finally(function () {
      inflight.delete(key);
    });
    inflight.set(key, req);
  }
  return inflight.get(key);
}

// Fill the attachments list of one open row with text nodes (no markup), and show it only when there are some.
function fillAssets(item, list) {
  const ul = item.querySelector(".hd-assets");
  if (!ul) return;
  ul.textContent = "";
  for (const name of list) {
    const li = document.createElement("li");
    li.className = "hd-asset";
    li.textContent = name;
    ul.appendChild(li);
  }
  ul.hidden = list.length === 0;
}

// Fill one open row's text box, reply, history and attachments from the cache (fetching when needed).
// Errors show in the box.
function loadText(item) {
  const id = idOf(item);
  const screen = item.closest ? item.closest(".hd-screen") : null;
  const pid = projectOf(item) || "";
  const pre = item.querySelector(".hd-text");
  const hist = item.querySelector(".hd-hist");
  if (!id || !pre || !screen) return Promise.resolve();
  const show = function (entry) {
    pre.textContent = textNote(entry);
    pre.setAttribute("data-state", entry.text == null ? "none" : "ready");
    if (hist) hist.textContent = (entry.history || []).join(" · ");
    const reply = item.querySelector(".hd-reply");
    if (reply) reply.textContent = replyNote(entry);
    fillAssets(item, entry.assets || []);
    const sumEl = item.querySelector(".hd-sum");
    if (sumEl) sumEl.textContent = summaryText(sumEl.getAttribute("data-sum"), entry);
  };
  if (!FULL_ID.test(id) || !pid) {
    pre.textContent = "The full text is only on this computer.";
    return Promise.resolve();
  }
  return fetchFull(pid, id).then(show, function () {
    pre.textContent = "Could not load the text. Close the row and open it again.";
    pre.setAttribute("data-state", "error");
  });
}

// Loads run a few at a time, so expanding many rows does not send a burst of requests.
function pump() {
  while (active < FULL_CONCURRENCY && queue.length) {
    const item = queue.shift();
    active += 1;
    loadText(item).then(done, done);
  }
  function done() {
    active -= 1;
    pump();
  }
}

function enqueue(item) {
  queue.push(item);
  pump();
}

// Open or close one row in place (no re-render): the panel, the aria-expanded state and the open set.
function setOpen(item, on) {
  const id = idOf(item);
  const hit = item.querySelector(".hd-hit");
  const panel = item.querySelector(".hd-panel");
  if (!id || !hit || !panel) return;
  panel.hidden = !on;
  item.classList.toggle("is-open", on);
  hit.setAttribute("aria-expanded", on ? "true" : "false");
  hit.setAttribute("aria-label", (on ? "Hide " : "Show ") + id);
  if (on) {
    openSet.add(id);
    enqueue(item);
  } else {
    openSet.delete(id);
  }
}

function loadOpenRows() {
  if (typeof document === "undefined") return;
  for (const item of document.querySelectorAll("#main .hd-item.is-open")) {
    enqueue(item);
  }
}

let listening = false;

// Wires the row toggles, the buttons, the forms and the search and select fields. Call once after the screen renders.
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
    // A click on the list row (not on a button, link or field) opens or closes it, like its # button.
    const tr = event.target && event.target.closest ? event.target.closest("tr.hd-row") : null;
    if (tr && !event.target.closest("a, button, input, select, textarea, label, form")) {
      const entry = tr.closest(".hd-item");
      if (entry) setOpen(entry, !entry.classList.contains("is-open"));
      return;
    }
    const btn = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!btn) return;
    const action = btn.getAttribute("data-action");
    const id = btn.getAttribute("data-id");
    const project = projectOf(btn);
    if (action === "head-toggle") {
      const item = btn.closest(".hd-item");
      if (item) setOpen(item, !item.classList.contains("is-open"));
    } else if (action === "head-expand-all") {
      const root = btn.closest(".hd-screen");
      const items = root ? Array.from(root.querySelectorAll(".hd-item")) : [];
      const allOpen = items.length > 0 && items.every(function (item) {
        return item.classList.contains("is-open");
      });
      if (allOpen) openSet.clear();
      items.forEach(function (item) {
        setOpen(item, !allOpen);
      });
      btn.textContent = allOpen ? "Expand all" : "Collapse all";
    } else if (action === "head-accept") {
      run("head.accept", { id: id }, { project: project, label: "Accepted " + id });
    } else if (action === "head-reopen") {
      run("head.set", { id: id, status: "open" }, { project: project, label: "Reopened " + id });
    } else if (action === "head-set") {
      const status = btn.getAttribute("data-status");
      run("head.set", { id: id, status: status }, { project: project, label: id + " " + status });
    } else if (action === "head-log") {
      showToast({ text: "Type in the chat. Every message is logged here." });
    } else if (action === "head-merge") {
      const into = btn.getAttribute("data-into");
      run("head.merge", { id: id, into: into }, { project: project, label: id + " merged into " + into });
    } else if (action === "head-bind-sug") {
      const ref = btn.getAttribute("data-ref");
      run("head.bind", { id: id, refs: [ref] }, { project: project, label: "Bound " + id + " to " + ref });
    } else if (action === "head-form") {
      // Opens the row and shows one form (a second click on the same action hides it).
      const name = btn.getAttribute("data-form");
      const panel = document.getElementById("hd-p-" + id);
      if (!panel) return;
      const item = panel.closest(".hd-item");
      if (panel.hidden && item) setOpen(item, true);
      for (const form of panel.querySelectorAll(".hd-form")) {
        const show = form.getAttribute("data-form") === name && form.hidden;
        form.hidden = !show;
        const input = show ? form.querySelector("input") : null;
        if (input) input.focus();
      }
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

function setField(bar, key, value) {
  const f = bar.getAttribute("data-f") || "open";
  const state = { f: f, q: "", kind: "", sid: "", sort: "", view: bar.getAttribute("data-view") || "list" };
  for (const el of bar.querySelectorAll("[data-field]")) {
    state[el.getAttribute("data-field")] = el.value || "";
  }
  state[key] = value;
  return hashOf(state);
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
  // A deep-linked row (#head?id=H12) opens once; after that the person's own open and close decide.
  if (ITEM_ID.test(id) && id !== seededId) {
    openSet.add(id);
    seededId = id;
  }
  const opts = {
    f: pick(params.get("f"), FILTERS.map(function (pair) {
      return pair[0];
    }), 20) || "open",
    q: text.length <= 200 ? text : "",
    kind: pick(params.get("kind"), KINDS, 20),
    sid: sid.length <= 60 ? sid : "",
    sort: pick(params.get("sort"), SORTS, 3) || "new",
    view: pick(params.get("view"), ["cards", "list"], 5) || "list",
    open: Array.from(openSet),
    project: vm.route.id,
    readOnly: false,
  };
  const html = headHtml({ head: vm.project.snapshot.head || null }, opts);
  if (typeof setTimeout === "function") setTimeout(loadOpenRows, 0);
  return html;
}
