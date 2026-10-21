// Limits v2 (R11.126, docs/LIMITS-V2-SPEC.md sections 1 and 2): one card per usage window (5 hours, Week). Each card
// has a usage bar 0-100 with the current fill and a draggable stop handle (role=slider), a mode choice (Budget from
// now | Cap at), an on/off switch, a number that mirrors the handle and a status line. Changes save live (debounced
// 400 ms) through POST /api/v1/limits, which records one head panel line. State lives here; a drag repaints the card
// in place (no re-render), so a live refresh cannot drop the handle. Widths come from data-pct (applyMeters).

import { getJson, postJson } from "../api.js";
import { withBusy } from "../busy.js";
import { applyMeters, esc } from "../dom.js";
import { copyButton, refSummary } from "../ref.js";
import { showToast } from "./toast.js";

const SAVE_MS = 400;
const FRESH_MS = 10000;
const WINDOWS = {
  five_hour: { title: "5 hours", short: "5h", sliderLabel: "5 hours stop", numLabel: "5 hours stop percent, 1 to 100",
    switchOn: "5 hours stop, on", switchOff: "5 hours stop, off" },
  week: { title: "Week", short: "weekly", sliderLabel: "Week stop", numLabel: "Week stop percent, 1 to 100",
    switchOn: "Week stop, on", switchOff: "Week stop, off" },
};
const ORDER = ["five_hour", "week"];
const MODE_WORDS = { budget: "Budget from now", cap: "Cap at" };

const L = { data: null, at: 0, loading: false, error: false, draft: {}, timers: {}, drag: null, listening: false };

function rerender() {
  if (typeof document !== "undefined") document.dispatchEvent(new Event("rb:render"));
}

function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n));
}

function announce(w) {
  document.dispatchEvent(new CustomEvent("rb:limits", { detail: w }));
}

function load() {
  if (L.loading || typeof fetch === "undefined") return;
  L.loading = true;
  getJson("/api/v1/limits").then(function (res) {
    if (!res || res.status !== 200 || !res.data || !res.data.windows) throw new Error("limits");
    L.data = res.data.windows;
    announce(L.data);
    L.error = false;
  }).catch(function () {
    L.error = true;
  }).finally(function () {
    L.loading = false;
    L.at = Date.now();
    if (!L.drag && !Object.keys(L.timers).length) rerender();
  });
}

// While the card is mounted (ensureLimits ran in the last 3 intervals), poll on its own; skipped when the tab is hidden.
let lastEnsure = 0;
let pollId = null;
function startPoll() {
  if (pollId || typeof window === "undefined") return;
  pollId = window.setInterval(function () {
    if (document.hidden || Date.now() - lastEnsure > FRESH_MS * 3) return;
    if (!L.drag && !Object.keys(L.timers).length && Date.now() - L.at >= FRESH_MS - 500) load();
  }, FRESH_MS);
}

function ensureLimits() {
  lastEnsure = Date.now();
  startPoll();
  if (L.data && Date.now() - L.at < FRESH_MS) return;
  if (L.error && Date.now() - L.at < FRESH_MS) return;
  setTimeout(load, 0);
}

// The working copy of one window: the draft while a change is pending, else the stored record.
function recOf(w) {
  const src = L.draft[w] || (L.data && L.data[w]);
  if (!src) return null;
  const used = L.data && L.data[w] && typeof L.data[w].percent === "number" ? L.data[w].percent : null;
  return { on: src.on === true, mode: src.mode === "budget" ? "budget" : "cap", value: Number(src.value) || 1,
    base: Number(src.base) || 0, once: src.once === true, used: used,
    resetsAt: L.data && L.data[w] ? L.data[w].resetsAt : null };
}

// The one absolute stop percent a record means (the server's effective_stop).
export function stopOf(rec) {
  return rec.mode === "cap" ? rec.value : Math.min(100, rec.base + rec.value);
}

export function labelOf(rec, w) {
  if (rec.mode === "cap") return "stop at " + Math.round(stopOf(rec)) + "%";
  return "+" + Math.round(rec.value) + "% of " + WINDOWS[w].short;
}

function valueText(rec, w) {
  return rec.mode === "cap" ? labelOf(rec, w) : labelOf(rec, w) + ", stop at " + Math.round(stopOf(rec)) + "%";
}

function resetText(value) {
  const t = Date.parse(value || "");
  if (!isFinite(t)) return "";
  const d = new Date(t);
  const pad = function (n) {
    return (n < 10 ? "0" : "") + n;
  };
  return "resets " + pad(d.getHours()) + ":" + pad(d.getMinutes());
}

function statusText(rec) {
  if (!rec.on) return "Stop is off. Agents are not limited by this window.";
  if (rec.used === null) return "No fresh reading: the stop cannot be checked yet.";
  const stop = stopOf(rec);
  if (rec.used >= stop) return "Reached: agents paused";
  return "Stops new jobs at " + Math.round(stop) + "%; " + Math.round(stop - rec.used) + "% left.";
}

function overridePid(vm) {
  if (vm.route && vm.route.name === "project" && vm.route.id) return vm.route.id;
  return vm.projects && vm.projects.length ? vm.projects[0].id : "";
}

function tone(rec) {
  if (!rec.on || rec.used === null) return "";
  const stop = stopOf(rec);
  return rec.used >= stop ? " tone-danger" : rec.used >= stop - 10 ? " tone-warning" : "";
}

function cardHtml(w, rec, vm) {
  const win = WINDOWS[w];
  const stop = clamp(stopOf(rec), 1, 100);
  const used = rec.used === null ? 0 : clamp(rec.used, 0, 100);
  const reached = rec.on && rec.used !== null && rec.used >= stopOf(rec);
  const pid = overridePid(vm);
  const seg = Object.keys(MODE_WORDS).map(function (m) {
    return '<button type="button" data-lv="mode" data-win="' + w + '" data-value="' + m + '" aria-pressed="' +
      (rec.mode === m) + '">' + MODE_WORDS[m] + "</button>";
  }).join("");
  const sw = '<button type="button" class="btn sw" role="switch" data-lv="on" data-win="' + w + '" aria-checked="' +
    rec.on + '" aria-label="' + (rec.on ? win.switchOn : win.switchOff) + '">' + (rec.on ? "On" : "Off") +
    "</button>";
  const min = rec.mode === "budget" ? Math.min(100, Math.round(rec.base) + 1) : 1;
  const bar = '<div class="lv-bar' + tone(rec) + (rec.on ? "" : " is-off") + '" data-lv="bar" data-win="' + w + '">' +
    '<span class="lv-zone' + (rec.mode === "budget" ? " is-budget" : "") + '" data-pct="' + stop +
    '"><span class="lv-handle" role="slider" tabindex="0" data-lv="handle" data-win="' + w + '" aria-label="' +
    win.sliderLabel + '" aria-orientation="horizontal" aria-valuemin="' + min + '" aria-valuemax="100" ' +
    'aria-valuenow="' + Math.round(stop) + '" aria-valuetext="' + esc(valueText(rec, w)) + '"></span></span>' +
    '<span class="lv-fill" data-pct="' + used + '"></span></div>';
  const scale = '<div class="lv-scale" aria-hidden="true"><span>0</span><span>50</span><span>100%</span></div>';
  const num = '<label class="lv-numwrap"><input class="lim-text lv-num" type="number" inputmode="numeric" min="1" ' +
    'max="100" data-lv="num" data-win="' + w + '" aria-label="' + win.numLabel + '" value="' +
    Math.round(rec.mode === "cap" ? stopOf(rec) : rec.value) + '"' + (rec.on ? "" : " disabled") + "> " +
    '<span class="lv-unit">' + (rec.mode === "cap" ? "% stop" : "% more") + "</span></label>";
  const once = rec.mode === "budget" ? '<label class="lv-once"><input type="checkbox" data-lv="once" data-win="' +
    w + '"' + (rec.once ? " checked" : "") + (rec.on ? "" : " disabled") + "> Once, do not repeat each " +
    esc(win.short === "weekly" ? "week" : "5h window") + "</label>" : "";
  const over = reached && pid ? ' <button type="button" class="btn" data-action="override" data-project="' + esc(pid) +
    '" data-focus="override" aria-label="Override for 1 hour">Override 1h</button>' : "";
  const used_t = rec.used === null ? "no reading" : Math.round(rec.used) + "% used";
  return '<section class="lv-card ov-card" aria-label="' + win.title + ' stop" data-win="' + w + '">' +
    '<div class="lv-head"><h3 class="lim-h">' + win.title + '</h3><span class="page-note">' + esc(used_t) +
    (rec.resetsAt ? " · " + esc(resetText(rec.resetsAt)) : "") + "</span>" + sw + "</div>" + bar + scale +
    '<div class="lv-row"><span class="hd-seg" role="group" aria-label="' + win.title + ' stop mode">' + seg +
    '</span><span class="lv-label" data-lv="label" aria-live="polite">' + esc(labelOf(rec, w)) + "</span>" + num +
    "</div>" + once + '<p class="page-note lv-status" data-lv="status">' + esc(statusText(rec)) + over +
    "</p></section>";
}

// Both window cards side by side (stacked under 900 px). Starts the first read; shows a note until it arrives.
export function limitsV2Html(vm) {
  attachLv();
  ensureLimits();
  const pid = vm.route && vm.route.name === "project" ? vm.route.id || null : null;
  const copy = copyButton("section", "tokens.weekly", "Usage stops", { project: pid, sum: refSummary("section", 2) });
  const top = '<div class="lv-top"><h3 class="lim-h">Usage stops</h3>' + copy + "</div>";
  if (!L.data) {
    return '<section class="ov-card" aria-label="Usage stops">' + top + '<p class="page-note">' +
      (L.error ? "Stops could not be loaded. They load again in a moment." : "Loading stops.") + "</p></section>";
  }
  return top + '<div class="lv-grid" aria-label="Usage stops">' + ORDER.map(function (w) {
    return cardHtml(w, recOf(w), vm);
  }).join("") + "</div>";
}

// ------------------------------------------------------------------ editing

function scheduleSave(w) {
  clearTimeout(L.timers[w]);
  L.timers[w] = setTimeout(function () {
    delete L.timers[w];
    save(w);
  }, SAVE_MS);
}

function save(w) {
  const d = L.draft[w];
  if (!d) return;
  // The save runs after a short pause, so the window's On switch is read now; it shows loading while the stop is saved.
  const sw = document.querySelector('[data-lv="on"][data-win="' + w + '"]');
  withBusy(sw, postJson("/api/v1/limits", { window: w, on: d.on, mode: d.mode, value: d.value, once: d.once })).then(function (res) {
    if (res && res.data && res.data.windows) { L.data = res.data.windows; announce(L.data); }
    if (!L.timers[w]) delete L.draft[w];
    L.at = Date.now();
    showToast({ text: WINDOWS[w].title + " stop saved.", tone: "success" });
  }).catch(function (err) {
    delete L.draft[w];
    showToast({ text: err && err.message ? err.message : "The stop was not saved.", tone: "danger" });
  }).finally(function () {
    if (!L.drag) rerender();
  });
}

function draftOf(w) {
  if (!L.draft[w]) {
    const rec = recOf(w);
    if (!rec) return null;
    L.draft[w] = { on: rec.on, mode: rec.mode, value: rec.value, base: rec.base, once: rec.once };
  }
  return L.draft[w];
}

// Move the stop to an absolute percent (handle, keys, bar click): a cap keeps it, a budget keeps base + N.
function setStop(w, pct) {
  const d = draftOf(w);
  if (!d) return;
  const s = clamp(Math.round(pct), 1, 100);
  d.value = d.mode === "cap" ? s : clamp(s - Math.round(d.base), 1, 100);
  d.on = true;
  paint(w);
  scheduleSave(w);
}

function setMode(w, mode) {
  const d = draftOf(w);
  const rec = recOf(w);
  if (!d || d.mode === mode) return;
  if (mode === "budget") {
    d.base = rec.used === null ? 0 : Math.round(rec.used);
    d.value = clamp(d.mode === "cap" ? 20 : d.value, 1, 100 - d.base || 1);
  } else {
    d.value = clamp(Math.round(stopOf(rec)), 1, 100);
  }
  d.mode = mode;
  d.on = true;
  scheduleSave(w);
  rerender();
}

// Repaint one card in place (drag, keys, number input) without a re-render.
function paint(w) {
  const rec = recOf(w);
  const card = typeof document !== "undefined" ? document.querySelector('.lv-card[data-win="' + w + '"]') : null;
  if (!rec || !card) return;
  const stop = clamp(stopOf(rec), 1, 100);
  const zone = card.querySelector(".lv-zone");
  zone.setAttribute("data-pct", String(stop));
  applyMeters(card);
  const handle = card.querySelector(".lv-handle");
  handle.setAttribute("aria-valuenow", String(Math.round(stop)));
  handle.setAttribute("aria-valuetext", valueText(rec, w));
  handle.setAttribute("aria-valuemin", String(rec.mode === "budget" ? Math.min(100, Math.round(rec.base) + 1) : 1));
  card.querySelector('[data-lv="label"]').textContent = labelOf(rec, w);
  const num = card.querySelector(".lv-num");
  if (num && document.activeElement !== num) num.value = String(Math.round(rec.mode === "cap" ? stop : rec.value));
  card.querySelector('[data-lv="status"]').firstChild.textContent = statusText(rec);
}

function barPct(bar, event) {
  const box = bar.getBoundingClientRect();
  return box.width > 0 ? ((event.clientX - box.left) / box.width) * 100 : 0;
}

function onKey(event) {
  const h = event.target && event.target.closest ? event.target.closest('[data-lv="handle"]') : null;
  if (!h) return;
  const w = h.getAttribute("data-win");
  const rec = recOf(w);
  if (!rec) return;
  const step = event.shiftKey ? 5 : 1;
  const now = stopOf(rec);
  const map = { ArrowRight: now + step, ArrowUp: now + step, ArrowLeft: now - step, ArrowDown: now - step,
    PageUp: now + 10, PageDown: now - 10, Home: 1, End: 100 };
  if (!(event.key in map)) return;
  event.preventDefault();
  setStop(w, map[event.key]);
}

function onDown(event) {
  const bar = event.target && event.target.closest ? event.target.closest('[data-lv="bar"]') : null;
  if (!bar) return;
  const w = bar.getAttribute("data-win");
  L.drag = { w: w, bar: bar };
  if (bar.setPointerCapture && event.pointerId !== undefined) {
    try {
      bar.setPointerCapture(event.pointerId);
    } catch (err) {
      // a synthetic pointer has no capture; the document listeners still follow the move
    }
  }
  const handle = bar.querySelector(".lv-handle");
  if (handle && handle.focus) handle.focus();
  setStop(w, barPct(bar, event));
  event.preventDefault();
}

function onMove(event) {
  if (L.drag) setStop(L.drag.w, barPct(L.drag.bar, event));
}

function onUp() {
  if (!L.drag) return;
  L.drag = null;
}

function onClick(event) {
  const el = event.target && event.target.closest ? event.target.closest("[data-lv]") : null;
  if (!el) return;
  const kind = el.getAttribute("data-lv");
  const w = el.getAttribute("data-win");
  if (kind === "mode") {
    setMode(w, el.getAttribute("data-value"));
  } else if (kind === "on") {
    const d = draftOf(w);
    if (!d) return;
    d.on = el.getAttribute("aria-checked") !== "true";
    scheduleSave(w);
    rerender();
  }
}

function onInput(event) {
  const el = event.target;
  const kind = el && el.getAttribute ? el.getAttribute("data-lv") : null;
  const w = el && el.getAttribute ? el.getAttribute("data-win") : null;
  if (kind === "num") {
    const n = Number(el.value);
    if (Number.isFinite(n) && n >= 1 && n <= 100) {
      const d = draftOf(w);
      if (!d) return;
      d.value = Math.round(n);
      paint(w);
      scheduleSave(w);
    }
  } else if (kind === "once") {
    const d = draftOf(w);
    if (!d) return;
    d.once = el.checked;
    scheduleSave(w);
  }
}

function attachLv() {
  if (L.listening || typeof document === "undefined") return;
  L.listening = true;
  document.addEventListener("pointerdown", onDown);
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
  document.addEventListener("pointercancel", onUp);
  document.addEventListener("keydown", onKey);
  document.addEventListener("click", onClick);
  document.addEventListener("input", onInput);
}

// Test hooks: the state and the pure helpers, no DOM.
export const _lv = { state: L, recOf: recOf, setStop: setStop };
