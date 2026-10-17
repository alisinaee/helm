// Activity (R11.4, docs/ACTIVITY-V2.md): the full project history. One feed merged on the server from the activity
// log, the head ledger, jobs, questions, git commits and usage readings (GET .../history), with filters by who, kind,
// text and time (presets, a custom range, or a drag across the per-hour/day histogram). Rows sit in day groups with
// sticky headers inside the page's own scroll region; older pages load on scroll (or the Load older button); new
// events slide in from a 10 s poll (ETag, so an idle poll is a 304). A row opens its details in the pane on the right.
// All projects merges every project with a project column. Until the first page arrives (and in node renders, which
// never fetch) the snapshot's newest activity lines fill the page. Undo keeps the old row's button (op undo).

import { emptyHtml, esc, patch } from "../dom.js";
import { fmtTokens } from "../format.js";
import { pageState, scopeSnapshots } from "./inbox.js";
import { showToast } from "./toast.js";
import {
  clock, dayLabel, defaultFilters, eventFromLine, groupByDay, loadFirst, loadOlder, matches, modelShort, modelTone,
  refText, saveFilters, stamp, stateFor, toMarkdown,
} from "./activity_data.js";
import { timelineHtml, msAt, VIEW_W } from "./activity_timeline.js";
import { actorHtml, detailHtml, hrefOf, kindHtml, num, scrubberHtml, toolbarHtml } from "./activity_view.js";

// The log keeps gui, cli, agent or phone; the detail pane shows the plain name.
export const SOURCE_WORD = { gui: "Dashboard", cli: "Terminal", agent: "Agent", phone: "Phone" };
const POLL_MS = 10000;
const NEAR_BOTTOM_PX = 480;
const HAS_DOM = typeof document !== "undefined";
const FRESH_MS = 1600;
let lastVm = null;

// The events of the snapshot activity lines in scope, newest first (the fallback before the full history).
export function mergedLines(scopes, limit) {
  const all = [];
  for (const s of scopes) {
    for (const line of s.snap.activity) {
      const e = eventFromLine(line, s.id, s.name);
      e.detail.source = SOURCE_WORD[line.src] || "Other";
      all.push(e);
    }
  }
  all.sort(function (a, b) {
    return (b.ms == null ? -Infinity : b.ms) - (a.ms == null ? -Infinity : a.ms);
  });
  return limit ? all.slice(0, limit) : all;
}

// One row on the shared grid: time | [project] | who | kind | what (opens the details) | ref | model | tokens | undo.
// The Undo button keeps the R7.65 rules: icon only, the full text (what it undoes) in aria-label and title.
// "R10.4 done -> done" reads "R10.4 done → done".
export function activityRowHtml(e, ctx) {
  const what = e.summary || e.verb || "change";
  const shown = esc(what).replace(/\s*(?:-&gt;|→)\s*/g, " → ");
  const label = esc("Undo " + what);
  const undo = e.undo && e.activity && e.project
    ? '<button type="button" class="act-undo" data-action="undo-line" data-project="' + esc(e.project) +
      '" data-activity="' + esc(e.activity) + '" aria-label="' + label + '" title="' + label +
      '"><svg class="ico" aria-hidden="true" focusable="false"><path d="M9 14 4 9l5-5"/>' +
      '<path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></svg></button>'
    : '<span class="hx-none" aria-hidden="true"></span>';
  const href = hrefOf(e, ctx.pid);
  const ref = refText(e);
  const refCell = ref ? (href ? '<a class="hx-ref" href="' + esc(href) + '" title="Open ' + esc(ref) + '">' +
    esc(ref) + "</a>" : '<span class="hx-ref">' + esc(ref) + "</span>") : '<span class="hx-ref"></span>';
  const flags = (ctx.fresh && ctx.fresh.has(e.id) && ctx.now - ctx.fresh.get(e.id) < FRESH_MS ? " new" : "") +
    (ctx.sel === e.id ? " sel" : "");
  const proj = ctx.all ? '<span class="hx-proj" title="' + esc(e.pname || "Account") + '">' +
    esc(e.pname || "Account") + "</span>" : "";
  return '<li class="act-row row-grid" id="hx-r-' + esc(e.id) + '" data-key="' + esc(e.id) +
    '" data-hx-row="' + flags.trim() + '">' +
    '<span class="hx-time num" title="' + esc(stamp(e.ms)) + '">' + esc(clock(e.ms)) + "</span>" + proj +
    actorHtml(e.actor) + kindHtml(e) +
    '<button type="button" class="hx-open" data-hx="open" data-id="' + esc(e.id) + '" title="' + esc(what) +
    '" aria-controls="hx-r-' + esc(e.id) + '" aria-expanded="' + (ctx.sel === e.id ? "true" : "false") +
    '"><span class="act-sum">' + shown +
    "</span></button>" + refCell + '<span class="hx-model chip-' + esc(modelTone(e.model)) + '" title="' +
    esc(e.model || "") + '">' + esc(modelShort(e.model)) + "</span>" +
    '<span class="hx-tok num">' + (e.tokensK == null ? "" : esc(fmtTokens(e.tokensK))) + "</span>" + undo + "</li>";
}

// The column header and the day groups (sticky day headers inside the scroll region).
function listHtml(events, ctx) {
  const head = '<div class="hx-cols act-row row-grid" aria-hidden="true"><span>Time</span>' +
    (ctx.all ? "<span>Project</span>" : "") + "<span>Who</span><span>Kind</span><span>What</span><span>Ref</span>" +
    '<span>Model</span><span class="hx-r">Tokens</span><span></span></div>';
  return head + groupByDay(events).map(function (g) {
    const label = dayLabel(g.start, ctx.now);
    return '<section class="hx-group" aria-label="' + esc(label) + '"><h3 class="hx-day"><span>' + esc(label) +
      '</span><span class="num hx-cnt">' + num(g.events.length) + '</span></h3><ol class="hx-list">' +
      g.events.map(function (e) { return activityRowHtml(e, ctx); }).join("") + "</ol></section>";
  }).join("");
}

function totalText(st, shown, fallback) {
  if (fallback) return shown + " recent";
  return st.total.toLocaleString("en-US") + (st.total === 1 ? " event" : " events");
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  lastVm = vm;
  const st = stateFor(vm.route);
  const now = Date.now();
  const all = vm.route.name !== "project";
  if (HAS_DOM) {
    ensureCss();
    if (st.tried !== JSON.stringify(st.filt)) loadFirst(st, now, repaint);
  }
  const fallback = st.status !== "ready";
  const events = fallback ? mergedLines(scopeSnapshots(vm), 0).filter(function (e) {
    return e.ms != null && matches(e, st.filt, now);
  }) : st.events;
  const ctx = { all: all, pid: st.pid, now: now, sel: st.sel, fresh: st.fresh };
  const selected = st.sel ? events.find(function (e) { return e.id === st.sel; }) : null;
  let note = "";
  if (st.status === "error") note = '<p class="hx-note">Showing recent changes only: ' + esc(st.error) + "</p>";
  else if (fallback && HAS_DOM) note = '<p class="hx-note" aria-busy="true">Loading the full history…</p>';
  let body;
  if (events.length) {
    const tail = st.next ? '<div class="hx-more"><button type="button" class="btn btn-small" data-hx="older"' +
      (st.older ? " disabled" : "") + ">" + (st.older ? "Loading…" : "Load older") + "</button></div>"
      : (fallback ? "" : '<p class="hx-end">Start of history</p>');
    body = listHtml(events, ctx) + tail;
  } else {
    body = emptyHtml(fallback && !HAS_DOM ? "No activity yet." : "No events match these filters.",
      '<button type="button" class="btn btn-small" data-hx="clear">Clear filters</button>');
  }
  return '<div class="hx-page' + (all ? " hx-all" : "") + (selected ? " has-detail" : "") + '">' +
    toolbarHtml(st, { totalText: totalText(st, events.length, fallback), live: !fallback }) +
    timelineHtml(st, events, now) + scrubberHtml(st) + note +
    '<div class="hx-body"><div class="hx-scroll" id="hx-scroll" role="region" aria-label="Project history" ' +
    'tabindex="0">' + body + "</div>" + detailHtml(selected, ctx) + "</div></div>";
}

function repaint() {
  if (!lastVm || !HAS_DOM || !document.querySelector(".hx-page")) return;
  patch("main", sectionView(lastVm));
}

function ensureCss() {
  if (document.querySelector('link[data-hx-css]')) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/css/activity.css";
  link.setAttribute("data-hx-css", "1");
  document.head.appendChild(link);
}

function current() {
  return lastVm ? stateFor(lastVm.route) : null;
}

function setFilters(change) {
  const st = current();
  if (!st) return;
  change(st.filt);
  saveFilters(st.key, st.filt);
  st.sel = null;
  repaint();
}

function toggle(list, value) {
  const at = list.indexOf(value);
  if (at >= 0) list.splice(at, 1);
  else list.push(value);
}

function copyText(text, okText) {
  const nav = typeof navigator !== "undefined" ? navigator : null;
  if (nav && nav.clipboard && nav.clipboard.writeText) {
    nav.clipboard.writeText(text).then(function () {
      showToast({ text: okText });
    }, function () {
      showToast({ text: "Copy failed", tone: "danger" });
    });
  } else {
    showToast({ text: "No clipboard here", tone: "warning" });
  }
}

function shownEvents(st) {
  return st.status === "ready" ? st.events : mergedLines(scopeSnapshots(lastVm), 0);
}

function onClick(event) {
  const el = event.target.closest ? event.target.closest("[data-hx]") : null;
  if (!el || !el.closest(".hx-page")) return;
  const st = current();
  const what = el.getAttribute("data-hx");
  const v = el.getAttribute("data-v");
  if (what === "kind") setFilters(function (f) { toggle(f.kinds, v); });
  else if (what === "actor") setFilters(function (f) { toggle(f.actors, v); });
  else if (what === "preset") {
    setFilters(function (f) {
      if (v === "custom" && f.preset !== "custom") {
        const now = Date.now();
        f.from = f.from || now - 86400000;
        f.to = f.to || null;
      }
      f.preset = v;
    });
  } else if (what === "clear") setFilters(function (f) { Object.assign(f, defaultFilters()); });
  else if (what === "older") loadOlder(st, Date.now(), repaint);
  else if (what === "open") {
    const id = el.getAttribute("data-id");
    st.sel = st.sel === id ? null : id;
    repaint();
  } else if (what === "tl") {
    pickOnTimeline(el.getAttribute("data-id"), Number(el.getAttribute("data-from")),
      Number(el.getAttribute("data-to")));
  } else if (what === "close") {
    const id = st.sel;
    st.sel = null;
    repaint();
    focusRow(id);
  } else if (what === "export") {
    const scope = lastVm.route.name === "project" ? lastVm.route.id : "All projects";
    copyText(toMarkdown(shownEvents(st).slice(0, 500), "History: " + scope), "Copied as Markdown");
  } else if (what === "copy-md") {
    const e = shownEvents(st).find(function (x) { return x.id === el.getAttribute("data-id"); });
    if (e) copyText(toMarkdown([e], "Event"), "Copied as Markdown");
  }
}

function focusRow(id) {
  if (!id) return;
  const btn = document.querySelector('.hx-open[data-id="' + CSS.escape(id) + '"]');
  if (btn) btn.focus();
}

let searchTimer = null;
function onInput(event) {
  if (!event.target || event.target.id !== "hx-q") return;
  const value = event.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function () {
    setFilters(function (f) { f.q = value.trim().slice(0, 200); });
  }, 250);
}

function onChange(event) {
  const el = event.target;
  const what = el && el.getAttribute ? el.getAttribute("data-hx") : null;
  if (what !== "from" && what !== "to") return;
  const ms = el.value ? new Date(el.value).getTime() : null;
  setFilters(function (f) {
    f.preset = "custom";
    f[what] = Number.isNaN(ms) ? null : ms;
  });
}

// Infinite scroll inside the page's own region.
function onScroll(event) {
  const el = event.target;
  if (!el || el.id !== "hx-scroll") return;
  if (el.scrollTop + el.clientHeight > el.scrollHeight - NEAR_BOTTOM_PX) {
    const st = current();
    if (st && st.next && !st.older) loadOlder(st, Date.now(), repaint);
  }
}

// Up and Down move between rows; Escape closes the details.
function onKey(event) {
  const el = event.target;
  if (!el || !el.closest || !el.closest(".hx-page")) return;
  if (event.key === "Escape" && current() && current().sel) {
    const id = current().sel;
    current().sel = null;
    repaint();
    focusRow(id);
    event.preventDefault();
    return;
  }
  if (!el.classList.contains("hx-open") || (event.key !== "ArrowDown" && event.key !== "ArrowUp")) return;
  const all = Array.from(document.querySelectorAll(".hx-open"));
  const next = all[all.indexOf(el) + (event.key === "ArrowDown" ? 1 : -1)];
  if (next) {
    next.focus();
    event.preventDefault();
  }
}

// The timeline: press and drag across the strip to set a custom range; a press with no drag is a click on a mark.
const drag = { on: false, x0: 0, x1: 0, svg: null, moved: false };

function fracOf(svg, clientX) {
  const box = svg.getBoundingClientRect();
  return Math.max(0, Math.min(1, (clientX - box.left) / Math.max(1, box.width)));
}

function drawPick() {
  const pick = drag.svg && drag.svg.querySelector("#hx-pick");
  if (!pick) return;
  const lo = Math.min(drag.x0, drag.x1);
  pick.setAttribute("x", String(lo * VIEW_W));
  pick.setAttribute("width", String(Math.abs(drag.x1 - drag.x0) * VIEW_W));
}

function onDown(event) {
  const svg = event.target && event.target.closest ? event.target.closest("#hx-tl") : null;
  if (!svg || event.button !== 0) return;
  drag.on = true;
  drag.moved = false;
  drag.svg = svg;
  drag.x0 = drag.x1 = fracOf(svg, event.clientX);
}

function onMove(event) {
  if (!drag.on) return;
  drag.x1 = fracOf(drag.svg, event.clientX);
  if (!drag.moved && Math.abs(drag.x1 - drag.x0) * drag.svg.getBoundingClientRect().width < 6) return;
  drag.moved = true;
  drawPick();
}

function onUp() {
  if (!drag.on) return;
  drag.on = false;
  if (!drag.moved) return;
  const t0 = Number(drag.svg.getAttribute("data-t0"));
  const t1 = Number(drag.svg.getAttribute("data-t1"));
  const lo = msAt(Math.min(drag.x0, drag.x1), t0, t1);
  const hi = msAt(Math.max(drag.x0, drag.x1), t0, t1);
  setFilters(function (f) {
    f.preset = "custom";
    f.from = lo;
    f.to = hi;
  });
}

// Hover tooltip for the timeline marks (data-tip).
let tipEl = null;
function onTip(event) {
  const el = event.target && event.target.closest ? event.target.closest(".hx-tl-m[data-tip]") : null;
  if (!el) {
    if (tipEl) tipEl.hidden = true;
    return;
  }
  if (!tipEl) {
    tipEl = document.createElement("div");
    tipEl.className = "hx-tip";
    tipEl.setAttribute("role", "tooltip");
    document.body.appendChild(tipEl);
  }
  tipEl.textContent = el.getAttribute("data-tip");
  tipEl.hidden = false;
  const box = tipEl.getBoundingClientRect();
  tipEl.style.left = Math.max(4, Math.min(event.clientX + 12, window.innerWidth - box.width - 4)) + "px";
  tipEl.style.top = Math.max(4, event.clientY + 16) + "px";
}

function pickOnTimeline(id, from, to) {
  const st = current();
  if (!st) return;
  if (!id) {
    const hit = st.events.find(function (e) { return e.ms >= from && e.ms <= to; });
    if (!hit) {
      setFilters(function (f) {
        f.preset = "custom";
        f.from = from;
        f.to = to;
      });
      return;
    }
    id = hit.id;
  }
  st.sel = id;
  repaint();
  const row = document.getElementById("hx-r-" + id);
  if (row && row.scrollIntoView) row.scrollIntoView({ block: "center" });
}

function poll() {
  if (document.visibilityState !== "visible" || !document.querySelector(".hx-page")) return;
  const st = current();
  if (st && !st.inflight) loadFirst(st, Date.now(), repaint);
}

if (HAS_DOM) {
  document.addEventListener("click", onClick);
  document.addEventListener("input", onInput);
  document.addEventListener("change", onChange);
  document.addEventListener("keydown", onKey);
  document.addEventListener("scroll", onScroll, true);
  document.addEventListener("pointerdown", onDown);
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
  document.addEventListener("pointerover", onTip);
  document.addEventListener("pointerout", onTip);
  document.addEventListener("pointercancel", onUp);
  setInterval(poll, POLL_MS);
}
