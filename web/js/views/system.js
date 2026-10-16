// System (R10.23, A5 of docs/SYSTEM-DESIGN-SECTION.md): one card per component, one column per layer, orthogonal edges
// with arrowheads, and a heat bar per card (Off | Commits | Jobs | Work). GET /api/v1/projects/<id>/system gives
// {components, edges, heat, warnings, sha}; the layout is graph/syslayout.js and pan/zoom is graph/viewport.js. The
// markup is a string (no inline styles or handlers): geometry is SVG attributes, colour comes from system.css.
// Selecting a card docks the side panel (system-panel.js, Esc or Close shuts it) and fires "system:select" ({pid, id}).
// The map fits the canvas on first render and on resize until the person zooms or pans.

import { getJson } from "../api.js";
import { bannerHtml, chipHtml, emptyHtml, esc, patch, skeletonHtml } from "../dom.js";
import { mountViewport } from "../graph/viewport.js";
import { CARD_W, systemLayout } from "../graph/syslayout.js";
import { panelHtml } from "./system-panel.js";

const MODES = [["off", "Off"], ["commits", "Commits"], ["jobs", "Jobs"], ["work", "Work"]];
const NAME_CHARS = 22;
const BAR_W = CARD_W - 16;
const store = new Map(); // project id -> {data, error, status}
const reading = new Set();
const mounted = new WeakSet();
const taps = { last: null };
let lastVm = null;
let mode = "commits";
let selected = null;
let view = null;
let api = null;
let auto = true;
let watcher = null;

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

// The heat of one component for the mode: the API's heat map first, then a heat object on the component itself.
export function heatOf(sys, c, m) {
  const top = sys.heat && typeof sys.heat === "object" ? sys.heat[c.id] : null;
  const own = c.heat && typeof c.heat === "object" ? c.heat : {};
  const h = Object.assign({}, own, top && typeof top === "object" ? top : {});
  if (m === "commits") return num(h.commits !== undefined ? h.commits : h.commits30);
  if (m === "jobs") return num(h.jobs !== undefined ? h.jobs : h.runningJobs);
  if (m === "work") return num(h.work !== undefined ? h.work : h.openWork);
  return 0;
}

function fileCount(c) {
  if (Number.isFinite(Number(c.fileCount))) return Number(c.fileCount);
  return Array.isArray(c.files) ? c.files.length : 0;
}

function clip(s) {
  return s.length > NAME_CHARS ? s.slice(0, NAME_CHARS - 1) + "…" : s;
}

function load(pid) {
  if (reading.has(pid)) return;
  reading.add(pid);
  getJson("/api/v1/projects/" + encodeURIComponent(pid) + "/system").then(function (reply) {
    store.set(pid, { data: reply.data || (store.get(pid) || {}).data || null, error: null, status: reply.status });
  }, function (err) {
    store.set(pid, { data: null, error: (err && err.message) || "Could not read the system map.",
      status: (err && err.status) || 0 });
  }).then(function () {
    reading.delete(pid);
    if (lastVm) patch("main", sectionHtml(lastVm));
  });
}

function cardSvg(card, comp, sys, max) {
  const v = heatOf(sys, comp, mode);
  const frac = max > 0 ? Math.min(1, v / max) : 0;
  const name = comp.name || card.name || card.id;
  const sel = selected === card.id;
  const by = card.h - 14;
  const bar = mode === "off" ? "" : '<rect class="wfg-band" x="8" y="' + by + '" width="' + BAR_W +
    '" height="6" rx="3"/>' +
    '<rect class="sys-heat wfg-nowbar" x="8" y="' + by + '" width="' +
    (frac * BAR_W).toFixed(1) + '" height="6" rx="3"/>';
  return '<g class="wfg-n sys-card' + (sel ? " sys-sel" : "") + '" data-sys="' + esc(card.id) + '" tabindex="0" ' +
    'role="button" aria-pressed="' + sel + '" transform="translate(' + card.x + " " + card.y + ')">' +
    "<title>" + esc(name) + " (" + esc(card.layer) + ", " + fileCount(comp) + " files, " + v + " " + mode +
    ")</title>" +
    '<rect class="wfg-tab" width="' + card.w + '" height="' + card.h + '" rx="6"/>' +
    '<text class="wfg-ph sys-n" x="8" y="22">' + esc(clip(name)) + "</text>" +
    '<text class="wfg-num" x="8" y="39">' + esc(card.layer) + "</text>" +
    '<text class="wfg-num" x="' + (card.w - 8) + '" y="39" text-anchor="end">' + fileCount(comp) + " files</text>" +
    bar + "</g>";
}

export function canvasSvg(sys) {
  const comps = Array.isArray(sys.components) ? sys.components.filter((c) => c && typeof c.id === "string") : [];
  const byId = {};
  comps.forEach((c) => {
    byId[c.id] = c;
  });
  const lay = systemLayout({ layers: sys.layers, components: comps, edges: sys.edges });
  const max = Math.max(0, ...comps.map((c) => heatOf(sys, c, mode)));
  const edges = lay.routes.map((r) => '<path class="wfg-e' + (r.kind === "data" ? " wfg-e-dependency" : "") +
    '" d="' + esc(r.d) +
    '" data-from="' + esc(r.from) + '" data-to="' + esc(r.to) + '" marker-end="url(#sys-arrow)"/>').join("");
  const heads = lay.columns.map((c) => '<text class="wfg-num" x="' + (c.x + 4) + '" y="12">' + esc(c.layer) +
    "</text>").join("");
  const cards = lay.cards.map((c) => cardSvg(c, byId[c.id] || {}, sys, max)).join("");
  const defs = '<defs><marker id="sys-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" ' +
    'orient="auto"><path class="wfg-arrow" d="M0 0L8 4L0 8z"/></marker></defs>';
  return '<svg id="sys-svg" class="wfg-svg" role="group" aria-label="System map" tabindex="0" data-w="' + lay.width +
    '" data-h="' + lay.height + '">' + defs + '<g id="sys-vp">' + heads + edges + cards + "</g></svg>";
}

function toolbarHtml(pid) {
  const seg = MODES.map((m) => '<button type="button" class="btn btn-small" data-sys-heat="' + m[0] +
    '" aria-pressed="' + (mode === m[0]) + '">' + m[1] + "</button>").join("");
  const op = (name, label, text) => '<button type="button" class="btn btn-small" data-sys-op="' + name +
    '" aria-label="' + label + '">' + text + "</button>";
  return '<div class="wfg-bar" role="toolbar" aria-label="System map controls"><span class="wfg-chips" role="group" ' +
    'aria-label="Heat">' + seg + "</span>" + op("out", "Zoom out", "−") + op("in", "Zoom in", "+") +
    op("fit", "Fit to screen", "Fit") + '<a class="btn btn-small" href="#/full/' + esc(pid) +
    '/system" target="_blank" rel="noopener">Open full screen</a></div>';
}

function retryHtml() {
  return '<button type="button" class="btn btn-small" data-sys-op="retry">Retry</button>';
}

export function bodyHtml(pid, got) {
  if (!got) return skeletonHtml(["w-90", "w-60"]);
  if (got.error) {
    if (got.status === 404) return emptyHtml("System map needs the API", retryHtml());
    return bannerHtml("warning", "System map could not be read.", got.error) + "<p>" + retryHtml() + "</p>";
  }
  const sys = got.data || {};
  const warn = (Array.isArray(sys.warnings) ? sys.warnings : []).map((w) => chipHtml(String(w), "warning")).join("");
  if (!Array.isArray(sys.components) || !sys.components.length) {
    return emptyHtml("No structure found. Add docs/system.json to describe the parts.", retryHtml());
  }
  const comp = selected ? sys.components.find((x) => x && x.id === selected) : null;
  const hit = comp && sys.heat ? sys.heat[comp.id] : null;
  return toolbarHtml(pid) + warn + '<div class="sys-canvas">' + canvasSvg(sys) + "</div>" + panelHtml(pid, comp, hit);
}

function sectionHtml(vm) {
  if (vm.route.name !== "project") return emptyHtml("Pick a project to see its system map.");
  const pid = vm.route.id;
  return '<div class="sys">' + bodyHtml(pid, store.get(pid)) + "</div>";
}

function select(id) {
  selected = selected === id ? null : id;
  if (id === null) selected = null;
  if (typeof document !== "undefined" && lastVm) {
    document.dispatchEvent(new CustomEvent("system:select", { detail: { pid: lastVm.route.id, id: selected } }));
    patch("main", sectionHtml(lastVm));
    mountSoon();
  }
}

function mountNow() {
  const svg = document.getElementById("sys-svg");
  if (!svg || mounted.has(svg)) return;
  mounted.add(svg);
  const box = { w: Number(svg.getAttribute("data-w")) || 1, h: Number(svg.getAttribute("data-h")) || 1 };
  api = mountViewport(svg, document.getElementById("sys-vp"), {
    view: view || { k: 1, x: 16, y: 16 }, box: box, taps: taps, fit: false,
    onTap: (el) => {
      const g = el.closest ? el.closest("[data-sys]") : null;
      if (g) select(g.getAttribute("data-sys"));
    },
    onView: (v) => {
      view = { k: v.k, x: v.x, y: v.y };
    },
  });
  if (auto || !view) api.fit();
  if (watcher) watcher.disconnect();
  if (typeof ResizeObserver === "function") {
    watcher = new ResizeObserver(() => {
      if (auto && api) api.fit();
    });
    watcher.observe(svg);
  }
  svg.addEventListener("pointerdown", () => {
    auto = false;
  });
  svg.addEventListener("wheel", () => {
    auto = false;
  });
}

function mountSoon() {
  if (typeof setTimeout === "function") setTimeout(mountNow, 0);
}

function onKey(event) {
  if (event.key === "Escape" && selected && lastVm) select(null);
}

function onClick(event) {
  const t = event.target && event.target.closest ? event.target.closest("[data-sys-heat],[data-sys-op]") : null;
  if (!t || !lastVm) return;
  if (t.hasAttribute("data-sys-heat")) {
    mode = t.getAttribute("data-sys-heat");
    patch("main", sectionHtml(lastVm));
    mountSoon();
    return;
  }
  const op = t.getAttribute("data-sys-op");
  if (op === "close") {
    select(null);
    return;
  }
  if (op === "fit") auto = true;
  else if (op === "in" || op === "out") auto = false;
  if (op === "retry") {
    store.delete(lastVm.route.id);
    load(lastVm.route.id);
    patch("main", sectionHtml(lastVm));
  } else if (api && op === "fit") api.fit();
  else if (api && op === "in") api.zoom(1.25);
  else if (api && op === "out") api.zoom(0.8);
}

let bound = false;
export function sectionView(vm) {
  lastVm = vm;
  if (!bound && typeof document !== "undefined" && document.addEventListener) {
    bound = true;
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
  }
  if (vm.route.name === "project" && !store.has(vm.route.id) && !reading.has(vm.route.id)) load(vm.route.id);
  mountSoon();
  return sectionHtml(vm);
}
