// Activity timeline (R11.117): the horizontal strip at the top of the Activity page. Pure helpers (axis, x mapping,
// tick labels, binning) plus the markup builder; no DOM, so node tests can import it. Events are binned by x so a few
// thousand events stay under MAX_MARKS marks. The list is the keyboard path; the strip is a pointer view.

import { esc } from "../dom.js";
import { KIND_WORD, rangeOf, stamp } from "./activity_data.js";

export const VIEW_W = 1000; // viewBox units across the axis
export const VIEW_H = 56;
export const BIN_W = 4; // marks closer than this (viewBox units) merge into one bin
export const MAX_MARKS = 600;
export const TICKS = 5;
const AXIS_Y = 40;
const DAY_MS = 86400000;
const SLACK_MS = 120000;

// The [t0, t1] the strip spans: the range filter, or first event to now when an end is open.
export function axisOf(filt, events, now) {
  const r = rangeOf(filt, now);
  let t0 = r[0];
  let t1 = r[1] == null ? now : r[1];
  if (t0 == null) {
    t0 = now;
    for (const e of events) if (e.ms != null && e.ms < t0) t0 = e.ms;
    if (t0 === now) t0 = now - DAY_MS;
  }
  if (t1 <= t0) t1 = t0 + 60000;
  return [t0, t1];
}

export function xOf(ms, t0, t1, w) {
  const f = (ms - t0) / (t1 - t0);
  return Math.max(0, Math.min(1, f)) * (w == null ? VIEW_W : w);
}

export function msAt(frac, t0, t1) {
  return Math.round(t0 + Math.max(0, Math.min(1, frac)) * (t1 - t0));
}

function pad(n) {
  return (n < 10 ? "0" : "") + n;
}

// Evenly spaced tick labels: hours (HH:mm) up to two days, MM-DD up to 60 days, full dates beyond. Last is "now"
// when the axis ends at now.
export function ticks(t0, t1, now) {
  const span = t1 - t0;
  const out = [];
  for (let i = 0; i < TICKS; i++) {
    const ms = t0 + Math.round((span * i) / (TICKS - 1));
    const d = new Date(ms);
    let label;
    if (span <= 2 * DAY_MS) label = pad(d.getHours()) + ":" + pad(d.getMinutes());
    else if (span <= 60 * DAY_MS) label = pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    else label = stamp(ms).slice(0, 10);
    if (i === TICKS - 1 && Math.abs(t1 - now) < 120000) label = "now";
    out.push({ ms: ms, label: label, x: (VIEW_W * i) / (TICKS - 1) });
  }
  return out;
}

// Bin events by x. Each bin: { x, n, id, ms, kind } with id/ms/kind of the first event of the bin in list order.
export function bin(events, t0, t1) {
  const bins = new Map();
  for (const e of events) {
    if (e.ms == null || e.ms < t0 || e.ms > t1 + SLACK_MS) continue;
    const b = Math.floor(xOf(e.ms, t0, t1) / BIN_W);
    const hit = bins.get(b);
    if (hit) hit.n += 1;
    else bins.set(b, { x: b * BIN_W, n: 1, id: e.id, ms: e.ms, kind: e.kind, summary: e.summary });
  }
  return Array.from(bins.values());
}

function clockOf(ms) {
  return stamp(ms).slice(11, 16);
}

function tipOf(m) {
  if (m.n > 1) return m.n + " events from " + stamp(m.ms).slice(5, 16) + " · click for the first";
  return stamp(m.ms).slice(5, 16) + " · " + (m.summary || KIND_WORD[m.kind] || m.kind);
}

// The text mirrored in the aria-live region.
export function selectedText(e) {
  if (!e) return "";
  return "Selected: " + clockOf(e.ms) + ", " + (KIND_WORD[e.kind] || e.kind) + " " + (e.summary || e.verb || "");
}

export function timelineHtml(st, events, now) {
  const f = st.filt;
  const [t0, t1] = axisOf(f, events, now);
  const marks = bin(events, t0, t1);
  const sel = st.sel ? events.find(function (e) { return e.id === st.sel; }) : null;
  const tk = ticks(t0, t1, now);
  const grid = tk.map(function (t) {
    return '<line class="hx-tl-grid" x1="' + t.x + '" x2="' + t.x + '" y1="' + (AXIS_Y - 2) + '" y2="' +
      (AXIS_Y + 4) + '"></line>';
  }).join("");
  const rects = marks.map(function (m) {
    const h = m.n > 1 ? 24 : 14;
    return '<rect class="hx-tl-m hx-m-' + esc(m.kind) + '" data-hx="tl" data-id="' + esc(m.id) + '" data-tip="' +
      esc(tipOf(m)) + '" x="' + m.x + '" y="' + (AXIS_Y - h) + '" width="' + (BIN_W - 1) + '" height="' + h +
      '"></rect>';
  }).join("");
  let selSvg = "";
  if (sel && sel.ms != null) {
    const x = Math.round(xOf(sel.ms, t0, t1) * 10) / 10;
    selSvg = '<line class="hx-tl-guide" x1="' + x + '" x2="' + x + '" y1="2" y2="' + AXIS_Y + '"></line>' +
      '<rect class="hx-tl-sel hx-m-' + esc(sel.kind) + '" x="' + (x - 4) + '" y="' + (AXIS_Y - 14) +
      '" width="8" height="14"></rect>';
  }
  const label = "Timeline of " + marks.reduce(function (a, m) { return a + m.n; }, 0) + " events, " +
    stamp(t0).slice(0, 16) + " to " + (Math.abs(t1 - now) < 120000 ? "now" : stamp(t1).slice(0, 16)) +
    ". Use the list to move through events.";
  const ticksHtml = tk.map(function (t) { return "<span>" + esc(t.label) + "</span>"; }).join("");
  return '<div class="hx-tl"><p class="hx-tl-sel-text" id="hx-tl-live" aria-live="polite">' +
    esc(selectedText(sel)) + "</p>" +
    '<svg class="hx-tl-svg" id="hx-tl" viewBox="0 0 ' + VIEW_W + " " + VIEW_H + '" preserveAspectRatio="none" ' +
    'data-t0="' + t0 + '" data-t1="' + t1 + '" role="img" aria-label="' + esc(label) + '">' +
    '<line class="hx-tl-axis" x1="0" x2="' + VIEW_W + '" y1="' + AXIS_Y + '" y2="' + AXIS_Y + '"></line>' +
    grid + rects + selSvg +
    '<rect class="hx-pick" id="hx-pick" x="0" y="0" width="0" height="' + VIEW_H + '"></rect></svg>' +
    '<div class="hx-tl-ticks" aria-hidden="true">' + ticksHtml + "</div></div>";
}
