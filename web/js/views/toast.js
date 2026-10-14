// Toasts (WP28): one aria-live region. A toast with an Undo action stays 5 s, others 4 s. Hovering or focusing a
// toast pauses its timer. Undo runs the action's function once. triggerUndo() undoes the newest undoable toast (z).

import { esc } from "../dom.js";

const UNDO_MS = 5000;
const PLAIN_MS = 4000;
const MIN_LEFT_MS = 500;
const toasts = [];
let seq = 0;
let onChange = function () {};

export function setToastListener(fn) {
  onChange = fn;
}

function find(id) {
  for (const t of toasts) {
    if (t.id === id) return t;
  }
  return null;
}

function start(t) {
  if (t.timer || t.paused) return;
  t.startedAt = Date.now();
  t.timer = window.setTimeout(function () {
    dismissToast(t.id);
  }, t.left);
}

function stop(t) {
  if (!t.timer) return;
  window.clearTimeout(t.timer);
  t.timer = null;
  t.left = Math.max(MIN_LEFT_MS, t.left - (Date.now() - t.startedAt));
}

export function showToast(opts) {
  const undo = typeof opts.undo === "function" ? opts.undo : null;
  const t = {
    id: "toast-" + (++seq),
    text: String(opts.text || ""),
    tone: opts.tone === "danger" || opts.tone === "success" ? opts.tone : "neutral",
    undo: undo,
    left: undo ? UNDO_MS : PLAIN_MS,
    timer: null,
    startedAt: 0,
    paused: false,
  };
  toasts.push(t);
  start(t);
  onChange();
  return t.id;
}

export function dismissToast(id) {
  const t = find(id);
  if (!t) return;
  stop(t);
  toasts.splice(toasts.indexOf(t), 1);
  onChange();
}

// Pause while the pointer or the keyboard focus is on the toast; resume when both leave.
export function setToastHold(id, held) {
  const t = find(id);
  if (!t) return;
  if (held) {
    t.paused = true;
    stop(t);
  } else {
    t.paused = false;
    start(t);
  }
}

export function undoToast(id) {
  const t = find(id);
  if (!t || !t.undo) return;
  const run = t.undo;
  dismissToast(id);
  run();
}

export function triggerUndo() {
  for (let i = toasts.length - 1; i >= 0; i -= 1) {
    if (toasts[i].undo) {
      undoToast(toasts[i].id);
      return true;
    }
  }
  return false;
}

export function toastsHtml() {
  return toasts.map(function (t) {
    const undo = t.undo
      ? '<button type="button" class="btn" data-action="toast-undo" data-toast="' + esc(t.id) +
        '" data-focus="undo-' + esc(t.id) + '" aria-label="Undo ' + esc(t.text) + '">Undo</button>'
      : "";
    return '<div class="toast" data-tone="' + esc(t.tone) + '" data-toast="' + esc(t.id) + '">' +
      '<p class="toast-text">' + esc(t.text) + "</p>" + undo +
      '<button type="button" class="btn" data-action="toast-close" data-toast="' + esc(t.id) +
      '" aria-label="Dismiss notification: ' + esc(t.text) + '">×</button></div>';
  }).join("");
}
