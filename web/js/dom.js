// DOM writes and markup helpers. This is the only module that assigns HTML strings to the page (lint_js enforces it).
// patch() replaces one section only when its markup changed, keeps the focused control, and sets meter widths
// through the CSSOM because the CSP forbids style attributes.

const lastHtml = new Map();

export function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
    if (ch === "&") return "&amp;";
    if (ch === "<") return "&lt;";
    if (ch === ">") return "&gt;";
    if (ch === "\"") return "&quot;";
    return "&#39;";
  });
}

function clampPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(0, n));
}

// Set every element with data-pct to its width. Run after each write, and on any root that holds meters.
export function applyMeters(root) {
  const scope = root || document;
  const fills = scope.querySelectorAll("[data-pct]");
  for (const el of fills) {
    el.style.width = clampPct(el.getAttribute("data-pct")) + "%";
  }
}

// Replace one section's contents. Returns true when the DOM changed. A focused select or text field is left alone
// until focus moves, so an open dropdown is not closed by a poll.
export function patch(sectionId, html) {
  const el = document.getElementById(sectionId);
  if (!el) return false;
  if (lastHtml.get(sectionId) === html) return false;
  const active = document.activeElement;
  const inside = Boolean(active) && el.contains(active);
  if (inside && (active.tagName === "SELECT" || active.tagName === "INPUT")) return false;
  const focusKey = inside ? active.getAttribute("data-focus") : null;
  el.innerHTML = html;
  lastHtml.set(sectionId, html);
  applyMeters(el);
  if (focusKey) {
    for (const candidate of el.querySelectorAll("[data-focus]")) {
      if (candidate.getAttribute("data-focus") === focusKey) {
        candidate.focus({ preventScroll: true });
        break;
      }
    }
  }
  return true;
}

// Replace the contents of one element that has no id (patch() needs one). Sets meter widths like patch() does.
export function setHtml(el, html) {
  if (!el) return;
  el.innerHTML = html;
  applyMeters(el);
}

export function setHidden(sectionId, hidden) {
  const el = document.getElementById(sectionId);
  if (el) el.hidden = Boolean(hidden);
}

// Markup helpers. They return strings and escape every value they are given.

export function meterHtml(pct, tone) {
  const width = pct == null ? 0 : clampPct(pct);
  return '<div class="meter tone-' + esc(tone || "accent") + '" aria-hidden="true">' +
    '<span class="meter-fill" data-pct="' + width + '"></span></div>';
}

export function chipHtml(text, kind) {
  return '<span class="chip chip-' + esc(kind || "neutral") + '">' + esc(text) + "</span>";
}

export function bannerHtml(tone, title, detail) {
  const detailHtml = detail ? '<p class="banner-detail">' + esc(detail) + "</p>" : "";
  return '<div class="banner banner-' + esc(tone) + '"><p class="banner-title">' + esc(title) + "</p>" +
    detailHtml + "</div>";
}

export function emptyHtml(title, actionHtml) {
  return '<div class="empty"><p class="empty-title">' + esc(title) + "</p>" +
    (actionHtml ? "<p>" + actionHtml + "</p>" : "") + "</div>";
}

// The placeholder lines while data loads. The wrapper is a busy region with a spoken "Loading"; the lines are hidden.
export function skeletonHtml(widths) {
  const list = widths || ["w-60", "w-90", "w-40"];
  const lines = list.map(function (w) {
    return '<span class="skel ' + esc(w) + '"></span>';
  }).join("");
  return '<div aria-busy="true"><span class="sr-only">Loading</span><div aria-hidden="true">' + lines +
    "</div></div>";
}

// SectionHeader: a disclosure button with a one-line summary, and a body that is hidden when closed.
export function sectionHtml(opts) {
  const id = opts.id;
  const expanded = Boolean(opts.open);
  const bodyId = "sec-" + id + "-body";
  return '<section class="section" aria-labelledby="sec-' + esc(id) + '-title">' +
    '<h2 class="section-h"><button type="button" class="section-head" aria-expanded="' + expanded +
    '" aria-controls="' + bodyId + '" data-action="toggle-section" data-section="' + esc(id) +
    '" data-focus="toggle-' + esc(id) + '">' +
    '<span class="section-title" id="sec-' + esc(id) + '-title">' + esc(opts.title) + "</span>" +
    '<span class="section-summary">' + esc(opts.summary || "") + "</span>" +
    '<span class="chev" aria-hidden="true">' + (expanded ? "▾" : "▸") + "</span>" +
    "</button></h2>" +
    '<div class="section-body" id="' + bodyId + '"' + (expanded ? "" : " hidden") + ">" +
    (opts.body || "") + "</div></section>";
}
