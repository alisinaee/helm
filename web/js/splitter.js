// Reusable drag splitter (R11.3). Contract: a host `[data-splitter-host="KEY"]` is a grid whose last column is
// `var(--split-KEY, DEFpx)`; inside it a separator `[data-splitter="KEY"]` (class `spl`) sits between the two regions.
// Optional on the separator: data-min, data-max, data-def (px). The region AFTER
// the separator is stored in localStorage "rb.splits" per KEY; pointer drag, arrow keys (Shift = x4), Home/End and
// double-click (reset) work through document-level delegation, so re-rendered views need no re-binding.
const KEY = "rb.splits";
const STEP = 16;

function load() {
  try {
    const o = JSON.parse(window.localStorage.getItem(KEY) || "{}");
    return o && typeof o === "object" ? o : {};
  } catch (e) {
    return {};
  }
}

function save(name, value) {
  try {
    const o = load();
    if (value === null) delete o[name]; else o[name] = value;
    window.localStorage.setItem(KEY, JSON.stringify(o));
  } catch (e) { /* storage unavailable */ }
}

export function bounds(sep, hostWidth) {
  const min = Number(sep.dataset.min) || 240;
  const cap = Number(sep.dataset.max) || 720;
  const room = hostWidth > 0 ? hostWidth - 320 : cap;
  return { min: min, max: Math.max(min, Math.min(cap, room)) };
}

export function clampWidth(sep, hostWidth, v) {
  const b = bounds(sep, hostWidth);
  return Math.max(b.min, Math.min(b.max, Math.round(v)));
}

function hostOf(sep) {
  return sep.closest('[data-splitter-host="' + sep.dataset.splitter + '"]');
}

function current(sep) {
  const host = hostOf(sep);
  const next = sep.nextElementSibling;
  if (next && next.getBoundingClientRect().width) return Math.round(next.getBoundingClientRect().width);
  const saved = load()[sep.dataset.splitter];
  return typeof saved === "number" ? saved : Number(sep.dataset.def) || (host ? 400 : 400);
}

function sync(sep) {
  const host = hostOf(sep);
  const hw = host ? host.getBoundingClientRect().width : 0;
  const b = bounds(sep, hw);
  sep.setAttribute("aria-valuemin", String(b.min));
  sep.setAttribute("aria-valuemax", String(b.max));
  sep.setAttribute("aria-valuenow", String(clampWidth(sep, hw, current(sep))));
}

function set(sep, value, persist) {
  const host = hostOf(sep);
  const w = clampWidth(sep, host ? host.getBoundingClientRect().width : 0, value);
  document.documentElement.style.setProperty("--split-" + sep.dataset.splitter, w + "px");
  sep.setAttribute("aria-valuenow", String(w));
  if (persist) save(sep.dataset.splitter, w);
  return w;
}

export function initSplitters() {
  const root = document.documentElement;
  const saved = load();
  Object.keys(saved).forEach(function (k) {
    if (typeof saved[k] === "number" && /^[a-z0-9-]+$/.test(k)) root.style.setProperty("--split-" + k, saved[k] + "px");
  });
  let drag = null;
  function find(e) {
    return e.target && e.target.closest ? e.target.closest("[data-splitter]") : null;
  }
  document.addEventListener("pointerdown", function (e) {
    const sep = find(e);
    if (!sep || e.button > 0) return;
    drag = { sep: sep, x: e.clientX, w: current(sep) };
    try { sep.setPointerCapture(e.pointerId); } catch (err) { /* synthetic pointer */ }
    sep.classList.add("spl-drag");
    e.preventDefault();
  });
  document.addEventListener("pointermove", function (e) {
    if (!drag) return;
    set(drag.sep, drag.w - (e.clientX - drag.x), false);
  });
  function end(e) {
    if (!drag) return;
    const sep = drag.sep;
    drag = null;
    sep.classList.remove("spl-drag");
    try { sep.releasePointerCapture(e.pointerId); } catch (err) { /* already released */ }
    const w = Number(sep.getAttribute("aria-valuenow"));
    if (w) save(sep.dataset.splitter, w);
  }
  document.addEventListener("pointerup", end);
  document.addEventListener("pointercancel", end);
  document.addEventListener("dblclick", function (e) {
    const sep = find(e);
    if (!sep) return;
    root.style.removeProperty("--split-" + sep.dataset.splitter);
    save(sep.dataset.splitter, null);
    sync(sep);
  });
  document.addEventListener("keydown", function (e) {
    const sep = find(e);
    if (!sep) return;
    const k = e.key;
    if (k !== "ArrowLeft" && k !== "ArrowRight" && k !== "Home" && k !== "End") return;
    const hw = hostOf(sep) ? hostOf(sep).getBoundingClientRect().width : 0;
    const b = bounds(sep, hw);
    const step = STEP * (e.shiftKey ? 4 : 1);
    const w = current(sep);
    set(sep, k === "Home" ? b.min : k === "End" ? b.max : k === "ArrowLeft" ? w + step : w - step, true);
    e.preventDefault();
  });
  document.addEventListener("focusin", function (e) { const s = find(e); if (s) sync(s); });
  document.addEventListener("pointerover", function (e) { const s = find(e); if (s) sync(s); });
  window.addEventListener("resize", function () {
    document.querySelectorAll("[data-splitter]").forEach(function (s) {
      if (root.style.getPropertyValue("--split-" + s.dataset.splitter)) set(s, current(s), false);
      else sync(s);
    });
  });
}
