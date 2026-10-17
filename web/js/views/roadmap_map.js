// Roadmap Map (R11.5, docs/ROADMAP-MAP.md): the plan as a metro line of phases with a column of task cards under each
// open station. graph/roadmap_layout.js places everything; this file draws the SVG with createElementNS (CSP: no style
// attributes, colour from roadmap_map.css classes) and binds graph/viewport.js for pan, Cmd/Ctrl+wheel zoom at the
// cursor, the keys (+ - 0, arrows, Shift+arrows pan, N centres on Now) and taps. A tap on a card, or Enter on a focused
// card, opens its Details in the side panel (route item); in full screen the same details show in an aside on the
// map. A tap on a station or a "done" stub folds or opens it in place. Right click, the ContextMenu key or Shift+F10 on
// a card opens a menu: Open details, Open in Work, Copy ref, Ask head. The diagram re-mounts only when its layout
// changes (data-rmm-rev); pan and zoom are kept per project.

import { getJson } from "../api.js";
import { chipHtml, esc, setHtml } from "../dom.js";
import { fmtCount, fmtTokens } from "../format.js";
import { refOf, refSummary } from "../ref.js";
import { buildHash, currentRoute } from "../router.js";
import { mountViewport, flowCentre } from "../graph/viewport.js";
import { roadmapLayout, STATUSES } from "../graph/roadmap_layout.js";
import { readSpacing, spacingOf, stepSpacing, writeSpacing } from "../graph/layout.js";

const NS = "http://www.w3.org/2000/svg";
const CSS_HREF = "/css/roadmap_map.css";
const FRESH_MS = 30000;
const GLYPH = { done: "✓", doing: "●", todo: "○", blocked: "✕", hold: "⏸", defer: "–" };
const WORD = { done: "Done", doing: "Doing", todo: "To do", blocked: "Blocked", hold: "On hold", defer: "Deferred" };
const FILTER_WORD = { all: "All", open: "Open", doing: "Doing", blocked: "Blocked", hold: "On hold", done: "Done" };
const TITLE_CHARS = 27;
const NAME_CHARS = 22;

// The spacing factor (R11.115) is kept for this map in localStorage; the view keeps its centre across a change.
const SPACE_KEY = "rb.space.roadmap";
const ui = { status: "all", model: "", open: {}, showDone: {}, full: false, spacing: readSpacing(SPACE_KEY) };
const store = new Map();
const deps = new Map();
let pending = null;
let recentre = null;
let focusNext = false;
let active = null;
let menu = null;
let cssLoaded = false;
let wired = false;
let fullAsked = false;

function el(tag, attrs, kids) {
  const node = document.createElementNS(NS, tag);
  Object.keys(attrs || {}).forEach(function (k) {
    if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, String(attrs[k]));
  });
  (kids || []).forEach(function (kid) {
    if (kid) node.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
  });
  return node;
}

function clip(s, max) {
  const t = String(s || "");
  return t.length > max ? t.slice(0, max - 1) + "…" : t;
}

function stamp(value) {
  const s = JSON.stringify(value);
  let h = 5381;
  for (let i = 0; i < s.length; i += 1) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
  return h.toString(36) + ":" + s.length;
}

function runningIds(snap) {
  const ids = {};
  (snap.jobs || []).forEach(function (j) {
    if ((j.status === "running" || j.status === "claimed") && j.task) ids[j.task] = true;
  });
  return ids;
}

// The `after` pairs live in the raw snapshot (workflow.edges.after), which the normalized one drops: fetched here,
// at most every 30 s, and a change re-renders once.
function depsOf(pid) {
  if (typeof window === "undefined") return [];
  const entry = deps.get(pid) || { after: [], at: 0, pending: false, key: "" };
  deps.set(pid, entry);
  if (!entry.pending && Date.now() - entry.at > FRESH_MS) {
    entry.pending = true;
    getJson("/api/v1/projects/" + encodeURIComponent(pid) + "/snapshot").then(function (res) {
      const wf = res && res.data && res.data.workflow;
      const after = wf && wf.edges && Array.isArray(wf.edges.after) ? wf.edges.after : [];
      const key = JSON.stringify(after);
      const changed = key !== entry.key;
      entry.after = after;
      entry.key = key;
      if (changed) window.dispatchEvent(new Event("hashchange"));
    }, function () {
      // No arrows when the raw snapshot cannot be read; the map still draws.
    }).then(function () {
      entry.at = Date.now();
      entry.pending = false;
    });
  }
  return entry.after;
}

function loadCss() {
  if (cssLoaded || typeof document === "undefined" || !document.head) return;
  cssLoaded = true;
  if (document.querySelector('link[href="' + CSS_HREF + '"]')) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = CSS_HREF;
  document.head.appendChild(link);
}

function modelsOf(snap) {
  const seen = [];
  (snap.tasks || []).forEach(function (t) {
    if (t.model && seen.indexOf(t.model) < 0) seen.push(t.model);
  });
  return seen.sort();
}

function toolbarHtml(snap) {
  const seg = STATUSES.map(function (s) {
    return '<button type="button" class="btn btn-small" data-rmm-status="' + s + '" aria-pressed="' +
      (ui.status === s) + '">' + FILTER_WORD[s] + "</button>";
  }).join("");
  const models = modelsOf(snap);
  if (ui.model && models.indexOf(ui.model) < 0) ui.model = "";
  const opts = ['<option value="">All models</option>'].concat(models.map(function (m) {
    return '<option value="' + esc(m) + '"' + (ui.model === m ? " selected" : "") + ">" + esc(m) + "</option>";
  })).join("");
  return '<div class="rmm-bar"><div class="seg" role="group" aria-label="Filter by status">' + seg + "</div>" +
    '<label class="rmm-model"><span class="rmm-lbl">Model</span><select class="rmm-select" data-rmm-model' +
    ' aria-label="Filter by model">' + opts + "</select></label></div>";
}

// The map actions sit inside the map box, top right, like the System view's overlay (web/css/system.css .sys-ov).
function overlayHtml() {
  const ctl = function (op, label, text) {
    return '<button type="button" class="btn btn-small" data-rmm-op="' + op + '" aria-label="' + label + '" title="' +
      label + '">' + text + "</button>";
  };
  const zoom = '<div class="rmm-og" role="group" aria-label="Map view">' + ctl("out", "Zoom out", "−") +
    ctl("in", "Zoom in", "+") + ctl("fit", "Fit to screen", "Fit") + ctl("now", "Centre on Now", "Now") +
    ctl("full", fullWord(), fullWord()) + "</div>";
  const space = '<div class="rmm-og" role="group" aria-label="Spacing"><span class="rmm-lbl">Spacing</span>' +
    '<button type="button" class="btn btn-small" data-rmm-space="-1" aria-label="Less space" title="Less space ([)">' +
    "−</button>" + '<span class="rmm-sp-v" data-rmm-space="reset" title="Double-click to reset">' +
    spaceText(ui.spacing) + "</span>" +
    '<button type="button" class="btn btn-small" data-rmm-space="1" aria-label="More space" title="More space (])">' +
    "+</button></div>";
  return '<div class="rmm-ov">' + zoom + space + "</div>";
}

function spaceText(v) {
  return spacingOf(v).toFixed(1) + "×";
}

function fullWord() {
  return ui.full ? "Exit full screen" : "Full screen";
}

function legendHtml() {
  const item = function (cls, glyph, word) {
    return '<li><span class="rmm-key ' + cls + '" aria-hidden="true">' + glyph + "</span>" + word + "</li>";
  };
  return '<ul class="rmm-legend" id="rmm-legend" aria-label="Map legend">' +
    item("is-done", "✓", "Done") + item("is-doing", "●", "Doing") + item("is-todo", "○", "To do") +
    item("is-blocked", "✕", "Blocked") + item("is-hold", "⏸", "On hold") + item("is-defer", "–", "Deferred") +
    item("is-run", "▶", "Agent running") + item("is-dep", "→", "Depends on") + item("is-now", "┊", "Now") +
    '<li class="rmm-hint">Drag or scroll to pan · ⌘/Ctrl+wheel zooms · arrows move · Enter opens · ' +
    "Shift+F10 menu · 0 fits</li></ul>";
}

// The Map body inside the Roadmap page. head is the page head (title, note, view tabs) from roadmap.js.
export function mapView(vm, snap, head) {
  loadCss();
  wire();
  const pid = vm.route.id;
  const running = runningIds(snap);
  const lay = roadmapLayout(snap, { status: ui.status, model: ui.model, open: ui.open, showDone: ui.showDone,
    deps: depsOf(pid), running: running, blocked: snap.blocked || [], spacing: ui.spacing });
  const rev = stamp(lay);
  const tasks = {};
  (snap.tasks || []).forEach(function (t) {
    tasks[t.id] = t;
  });
  pending = { pid: pid, lay: lay, rev: rev, tasks: tasks, snap: snap, phases: snap.phases || [],
    item: vm.route.item || null };
  schedule();
  const shown = lay.cards.length;
  const note = shown ? "" : '<p class="rmm-empty">No tasks match these filters.</p>';
  return '<div class="rmm-page' + (ui.full ? " is-full" : "") + '" data-rmm-page>' + head + toolbarHtml(snap) +
    '<div class="rmm-stage">' + overlayHtml() +
    '<div class="rmm-host" data-rmm-host data-rmm-rev="' + esc(rev) + '"></div>' + note +
    '<aside class="rmm-aside" data-rmm-aside aria-label="Task details" hidden></aside></div>' +
    legendHtml() + "</div>";
}

function schedule() {
  if (typeof window === "undefined") return;
  setTimeout(mount, 0);
}

function stationNode(c, pid) {
  const ring = el("circle", { class: "rmm-station", cx: c.cx, cy: c.cy, r: 8 });
  const fill = c.state === "done" ? el("circle", { class: "rmm-station-in", cx: c.cx, cy: c.cy, r: 4 }) : null;
  const room = c.open ? NAME_CHARS : 11;
  const name = el("text", { class: "rmm-pname", x: c.x + 26, y: c.cy + 4 }, [
    el("tspan", { class: "rmm-pid" }, [c.id + " "]), c.open ? clip(c.name, room) : ""]);
  const stat = el("text", { class: "rmm-pstat", x: c.x, y: 50 }, [
    (c.open ? "▾ " : "▸ ") + fmtCount(c.done) + "/" + fmtCount(c.total) + " · " + c.pct + "%" +
    (c.doing ? " · ● " + fmtCount(c.doing) + " doing" : "")]);
  const track = el("rect", { class: "rmm-track", x: c.x, y: 58, width: c.w, height: 4, rx: 2 });
  const bar = el("rect", { class: "rmm-bar-fill" + (c.state === "done" ? " is-done" : ""), x: c.x, y: 58,
    width: Math.round((c.w * c.pct) / 100), height: 4, rx: 2 });
  const hit = el("rect", { class: "rmm-hit", x: c.x - 4, y: 4, width: c.w + 8, height: 64, rx: 6 });
  const label = c.id + " " + c.name + ", " + (WORD[c.state] || c.state) + ", " + c.done + " of " + c.total +
    " done" + (c.doing ? ", " + c.doing + " running" : "") + (c.open ? ", open" : ", folded");
  return el("g", { class: "rmm-phase is-" + (c.state === "partial" ? "doing" : c.state) + (c.now ? " is-now" : ""),
    "data-wf-item": "phase:" + c.id, "data-cx": c.cx, "data-cy": c.cy, tabindex: -1, role: "button",
    "aria-expanded": c.open ? "true" : "false", "aria-label": label, "data-pid": pid },
  [el("title", null, [c.id + " · " + c.name]), hit, ring, fill, name, stat, track, bar]);
}

function foldBox(c) {
  const y = 76;
  return el("g", { class: "rmm-foldbox", "aria-hidden": "true" }, [
    el("rect", { class: "rmm-fold-rect", x: c.x, y: y, width: c.w, height: 44, rx: 6 }),
    el("text", { class: "rmm-ctext", x: c.x + 8, y: y + 18 }, [fmtCount(c.total) + " tasks"]),
    el("text", { class: "rmm-cmeta", x: c.x + 8, y: y + 34 }, [c.hidden ? "▸ open" : ""]),
  ]);
}

function stubNode(s) {
  const word = (s.open ? "▾ " : "▸ ") + "✓ " + fmtCount(s.count) + " done";
  return el("g", { class: "rmm-stub", "data-wf-item": s.id, "data-cx": s.cx, "data-cy": s.cy, tabindex: -1,
    role: "button", "aria-expanded": s.open ? "true" : "false",
    "aria-label": fmtCount(s.count) + " done tasks in " + s.phase + (s.open ? ", shown" : ", folded") }, [
    el("rect", { class: "rmm-stub-rect", x: s.x, y: s.y, width: s.w, height: s.h, rx: 6 }),
    el("text", { class: "rmm-ctext", x: s.x + 10, y: s.y + 18 }, [word]),
  ]);
}

function cardNode(c) {
  const glyph = c.running ? "▶" : GLYPH[c.status] || "○";
  const right = (c.model || "") + (c.tokensK != null ? " ~" + fmtTokens(c.tokensK) : "");
  const label = c.id + " " + c.title + ", " + (WORD[c.status] || c.status) + (c.running ? ", agent running" : "") +
    (c.needsUser ? ", needs you" : "") + (c.model ? ", " + c.model : "");
  return el("g", { class: "rmm-card is-" + c.status + (c.running ? " is-run" : "") + (c.needsUser ? " is-you" : ""),
    "data-wf-item": c.key, "data-task": c.id, "data-cx": c.cx, "data-cy": c.cy, tabindex: -1, role: "button",
    "aria-label": label }, [
    el("title", null, [c.id + " " + c.title]),
    el("rect", { class: "rmm-card-rect", x: c.x, y: c.y, width: c.w, height: c.h, rx: 6 }),
    el("rect", { class: "rmm-card-edge", x: c.x, y: c.y, width: 4, height: c.h, rx: 2 }),
    el("text", { class: "rmm-glyph", x: c.x + 11, y: c.y + 17 }, [glyph]),
    el("text", { class: "rmm-cid", x: c.x + 24, y: c.y + 17 }, [c.id + (c.needsUser ? " ·you" : "")]),
    el("text", { class: "rmm-cmeta", x: c.x + c.w - 8, y: c.y + 17, "text-anchor": "end" }, [right]),
    el("text", { class: "rmm-ctext", x: c.x + 11, y: c.y + 36 }, [clip(c.title, TITLE_CHARS)]),
  ]);
}

function buildSvg(lay, pid) {
  const defs = el("defs", null, [
    el("marker", { id: "rmm-arrow", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 8, markerHeight: 8,
      markerUnits: "userSpaceOnUse", orient: "auto" }, [el("path", { class: "rmm-arrowhead", d: "M0 0L8 4L0 8z" })]),
  ]);
  const vp = el("g", { class: "rmm-vp", transform: "translate(0 0) scale(1)" });
  const back = el("g", { class: "rmm-back" });
  if (lay.now) {
    back.appendChild(el("line", { class: "rmm-now-line", x1: lay.now.x, y1: 4, x2: lay.now.x, y2: lay.height - 8 }));
    back.appendChild(el("text", { class: "rmm-now-text", x: lay.now.x + 4, y: lay.height - 10 }, ["Now"]));
    // The viewport centres on .wfg-halo for the N key.
    back.appendChild(el("rect", { class: "wfg-halo rmm-halo", x: lay.now.cx - 14, y: lay.now.cy - 14, width: 28,
      height: 28, rx: 14 }));
  }
  if (lay.line) {
    back.appendChild(el("line", { class: "rmm-metro", x1: lay.line.x1, y1: lay.line.y, x2: lay.line.x2,
      y2: lay.line.y }));
  }
  const edges = el("g", { class: "rmm-edges" }, lay.edges.map(function (e) {
    return el("path", { class: "rmm-dep", d: e.d, "marker-end": "url(#rmm-arrow)", "data-from": e.from,
      "data-to": e.to });
  }));
  const nodes = el("g", { class: "rmm-nodes" });
  lay.cols.forEach(function (c) {
    nodes.appendChild(stationNode(c, pid));
    if (!c.open) nodes.appendChild(foldBox(c));
    lay.stubs.filter(function (s) {
      return s.phase === c.id;
    }).forEach(function (s) {
      nodes.appendChild(stubNode(s));
    });
    lay.cards.filter(function (k) {
      return k.phase === c.id;
    }).forEach(function (k) {
      nodes.appendChild(cardNode(k));
    });
  });
  vp.appendChild(back);
  vp.appendChild(edges);
  vp.appendChild(nodes);
  const svg = el("svg", { class: "rmm-svg", role: "group", tabindex: 0, "aria-label": "Roadmap map: " +
    lay.cols.length + " phases, " + lay.cards.length + " tasks shown. Arrow keys move between items.",
  "aria-describedby": "rmm-legend" }, [defs, vp]);
  return { svg: svg, vp: vp, box: { w: lay.width, h: lay.height } };
}

function select(svg, item) {
  svg.querySelectorAll(".rmm-card.is-sel").forEach(function (n) {
    n.classList.remove("is-sel");
  });
  if (!item) return;
  const hit = svg.querySelector('[data-wf-item="task:' + cssEsc(item) + '"]');
  if (hit) hit.classList.add("is-sel");
}

function cssEsc(s) {
  return String(s).replace(/["\\]/g, "\\$&");
}

function mount() {
  const st = pending;
  if (!st || typeof document === "undefined") return;
  const host = document.querySelector("[data-rmm-host]");
  if (!host) return;
  const same = active && active.host === host && host.firstChild && active.rev === st.rev;
  if (same) {
    active.st = st;
    select(active.svg, st.item);
    syncAside();
    return;
  }
  const keepFocus = document.activeElement && document.activeElement.closest &&
    document.activeElement.closest("[data-wf-item]");
  const focusKey = keepFocus ? keepFocus.getAttribute("data-wf-item") : null;
  const saved = store.get(st.pid);
  if (active && active.api) active.api.destroy();
  host.replaceChildren();
  const built = buildSvg(st.lay, st.pid);
  host.appendChild(built.svg);
  const api = mountViewport(built.svg, built.vp, {
    view: saved || { k: 1, x: 16, y: 16 },
    box: built.box,
    taps: { last: null },
    fit: false,
    onTap: activate,
    onClear: closeMenu,
    onView: function (v) {
      store.set(st.pid, { k: v.k, x: v.x, y: v.y });
    },
  });
  active = { host: host, svg: built.svg, api: api, rev: st.rev, st: st };
  if (recentre) {
    // A spacing change: the same part of the diagram stays in the middle of the screen, at the same zoom.
    const sx = st.lay.width / (recentre.w || 1);
    const sy = st.lay.height / (recentre.h || 1);
    api.centerOn({ x: recentre.x * sx, y: recentre.y * sy }, true);
    recentre = null;
  } else if (!saved) {
    openAtNow(api, st.lay);
  }
  built.svg.addEventListener("keydown", onSvgKey);
  built.svg.addEventListener("contextmenu", onContext);
  select(built.svg, st.item);
  if (focusNext) {
    focusNext = false;
    built.svg.focus({ preventScroll: true });
  }
  if (focusKey) {
    const again = built.svg.querySelector('[data-wf-item="' + cssEsc(focusKey) + '"]');
    if (again) again.focus({ preventScroll: true });
  }
  syncAside();
}

// The first view of a project: 1:1 (the text stays readable), the top in view, and the Now column a third in.
function openAtNow(api, lay) {
  const size = api.size();
  const k = 1;
  const room = size.w - 32;
  let x = 16;
  if (lay.width > room && lay.now) x = Math.max(room + 16 - lay.width, Math.min(16, size.w / 3 - lay.now.x));
  api.centerOn({ x: (size.w / 2 - x) / k, y: (size.h / 2 - 16) / k }, true);
}

function rerender() {
  window.dispatchEvent(new Event("hashchange"));
}

// One step of the spacing factor (dir -1 or 1), or the value itself. The map re-lays out and keeps its centre.
function changeSpacing(dir) {
  setSpacing(stepSpacing(ui.spacing, dir));
}

function setSpacing(v) {
  const next = spacingOf(v);
  if (next === ui.spacing) return;
  if (active) {
    recentre = Object.assign(flowCentre(active.api.view(), active.api.size()),
      { w: active.st.lay.width, h: active.st.lay.height });
  }
  ui.spacing = next;
  writeSpacing(SPACE_KEY, next);
  focusNext = true;
  rerender();
}

// A tap, or Enter, on a map item: a card opens its details; a station or a stub folds or opens in place.
function activate(node) {
  closeMenu();
  const key = node.getAttribute("data-wf-item") || "";
  if (key.indexOf("phase:") === 0) {
    const pid = key.slice(6);
    const col = active && active.st.lay.cols.find(function (c) {
      return c.id === pid;
    });
    ui.open[pid] = !(col && col.open);
    rerender();
  } else if (key.indexOf("done:") === 0) {
    const pid = key.slice(5);
    ui.showDone[pid] = !ui.showDone[pid];
    rerender();
  } else if (key.indexOf("task:") === 0) {
    openDetails(key.slice(5));
  }
}

function openDetails(id) {
  const route = currentRoute();
  const next = buildHash(Object.assign({}, route, { view: "map", item: id }));
  if (window.location.hash !== next) window.location.hash = next;
  else syncAside();
  if (fullEl()) showAside(id);
}

function fullEl() {
  return ui.full && typeof document !== "undefined" ? document.querySelector("[data-rmm-page]") : null;
}

function taskRef(id) {
  const st = active && active.st;
  const t = st && st.tasks[id];
  return { ref: refOf(st ? st.pid : "", "task", id), sum: t ? refSummary("task", t, st.snap) : "" };
}

// In full screen the side panel is hidden behind the map, so the same essentials show in an aside on the map.
function showAside(id) {
  const aside = document.querySelector("[data-rmm-aside]");
  const st = active && active.st;
  const t = st && st.tasks[id];
  if (!aside || !t) return;
  const r = taskRef(id);
  const work = "#/p/" + st.pid + "/work/i/" + id;
  setHtml(aside, '<p class="rmm-aside-id">' + esc(id) + "</p><h2 class=\"rmm-aside-title\">" + esc(t.title) +
    '</h2><p class="rmm-aside-meta">' + chipHtml(WORD[statusOfTask(t)] || t.state, "neutral") +
    (t.model ? chipHtml(t.model, "neutral") : "") + (t.tokensK != null ? '<span class="num">~' +
    esc(fmtTokens(t.tokensK)) + "</span>" : "") + "</p>" +
    (t.note ? '<p class="rmm-aside-note">' + esc(t.note) + "</p>" : "") +
    '<p class="rmm-aside-act"><button type="button" class="btn btn-small" data-action="copy-ref" data-ref="' +
    esc(r.ref) + '" data-sum="' + esc(r.sum) + '">Copy ref</button><a class="btn btn-small" href="' + esc(work) +
    '" data-rmm-exit>Open in Work</a><button type="button" class="btn btn-small" data-rmm-aside-close' +
    ' aria-label="Close details">Close</button></p>');
  aside.hidden = false;
}

function statusOfTask(t) {
  const st = active && active.st;
  const lay = st && st.lay;
  const card = lay && lay.cards.find(function (c) {
    return c.id === t.id;
  });
  return card ? card.status : t.state === "done" ? "done" : "todo";
}

function syncAside() {
  const aside = typeof document !== "undefined" ? document.querySelector("[data-rmm-aside]") : null;
  if (!aside) return;
  const item = active && active.st.item;
  if (fullEl() && item) showAside(item);
  else aside.hidden = true;
}

function onSvgKey(e) {
  const node = e.target && e.target.closest ? e.target.closest("[data-wf-item]") : null;
  if (e.key === "[" || e.key === "]") {
    e.preventDefault();
    changeSpacing(e.key === "]" ? 1 : -1);
  } else if ((e.key === "Enter" || e.key === " ") && node) {
    e.preventDefault();
    activate(node);
  } else if ((e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey)) && node) {
    e.preventDefault();
    const r = node.getBoundingClientRect();
    openMenu(node, r.left + r.width / 2, r.top + r.height / 2);
  }
}

function onContext(e) {
  const node = e.target && e.target.closest ? e.target.closest('[data-wf-item^="task:"]') : null;
  if (!node) return;
  e.preventDefault();
  openMenu(node, e.clientX, e.clientY);
}

function openMenu(node, cx, cy) {
  const key = node.getAttribute("data-wf-item") || "";
  if (key.indexOf("task:") !== 0) return;
  closeMenu();
  const id = key.slice(5);
  const stage = active.host.parentNode;
  const box = stage.getBoundingClientRect();
  const r = taskRef(id);
  const m = document.createElement("div");
  m.className = "rmm-menu";
  m.setAttribute("role", "menu");
  m.setAttribute("aria-label", "Actions for " + id);
  const item = function (op, text, extra) {
    return '<button type="button" role="menuitem" tabindex="-1" class="rmm-mi" data-rmm-menu="' + op + '"' +
      (extra || "") + ">" + text + "</button>";
  };
  setHtml(m, item("details", "Open details") + item("work", "Open in Work") +
    item("copy", "Copy ref", ' data-action="copy-ref" data-ref="' + esc(r.ref) + '" data-sum="' + esc(r.sum) + '"') +
    item("ask", "Ask head", ' data-action="copy-ref" data-ref="' + esc(r.ref) + '" data-sum="' +
      esc("Head, about this task: " + r.sum) + '"'));
  m.setAttribute("data-task", id);
  stage.appendChild(m);
  const x = Math.max(4, Math.min(cx - box.left, box.width - m.offsetWidth - 4));
  const y = Math.max(4, Math.min(cy - box.top, box.height - m.offsetHeight - 4));
  m.style.left = x + "px";
  m.style.top = y + "px";
  menu = { el: m, from: node };
  const first = m.querySelector(".rmm-mi");
  if (first) first.focus();
}

function closeMenu(restore) {
  if (!menu) return;
  const from = menu.from;
  menu.el.remove();
  menu = null;
  if (restore && from && from.isConnected) from.focus({ preventScroll: true });
}

function menuPick(btn) {
  const op = btn.getAttribute("data-rmm-menu");
  const id = menu ? menu.el.getAttribute("data-task") : null;
  const pid = active ? active.st.pid : null;
  closeMenu(op === "copy");
  if (!id || !pid) return;
  if (op === "details") openDetails(id);
  else if (op === "work") leaveTo("#/p/" + pid + "/work/i/" + id);
  else if (op === "ask") leaveTo("#/p/" + pid + "/head?q=" + encodeURIComponent(id));
}

function leaveTo(hash) {
  if (fullEl()) exitFull();
  window.location.hash = hash;
}

function onMenuKey(e) {
  if (!menu) {
    if (e.key === "Escape" && ui.full) {
      e.preventDefault();
      e.stopPropagation();
      exitFull();
    }
    return;
  }
  const items = Array.from(menu.el.querySelectorAll(".rmm-mi"));
  const at = items.indexOf(document.activeElement);
  if (e.key === "Escape") {
    e.preventDefault();
    e.stopPropagation();
    closeMenu(true);
  } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const step = e.key === "ArrowDown" ? 1 : -1;
    items[(at + step + items.length) % items.length].focus();
  } else if (e.key === "Home" || e.key === "End") {
    e.preventDefault();
    items[e.key === "Home" ? 0 : items.length - 1].focus();
  } else if (e.key === "Tab") {
    closeMenu(true);
  }
}

// Full screen: the page is pinned over the window (is-full, kept in ui so a re-render keeps it), and the document
// asks the browser for full screen too (the root element, which no re-render replaces). Where the browser refuses
// (an embedded pane) the pinned page still fills the window. Escape, the button or leaving the browser's full screen
// ends both.
function toggleFull(page) {
  if (ui.full) {
    exitFull();
    return;
  }
  ui.full = true;
  page.classList.add("is-full");
  const root = document.documentElement;
  if (root.requestFullscreen) root.requestFullscreen().then(null, function () {});
  onFullChange();
}

function exitFull() {
  ui.full = false;
  const page = document.querySelector("[data-rmm-page]");
  if (page) page.classList.remove("is-full");
  if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().then(null, function () {});
  onFullChange();
}

function onClick(e) {
  const t = e.target;
  if (!t || !t.closest) return;
  const mi = t.closest("[data-rmm-menu]");
  if (mi) {
    menuPick(mi);
    return;
  }
  if (menu && !t.closest(".rmm-menu")) closeMenu();
  const page = t.closest("[data-rmm-page]");
  if (!page) return;
  const s = t.closest("[data-rmm-status]");
  if (s) {
    ui.status = s.getAttribute("data-rmm-status");
    rerender();
    return;
  }
  const sp = t.closest("[data-rmm-space]");
  if (sp && sp.getAttribute("data-rmm-space") !== "reset") {
    changeSpacing(Number(sp.getAttribute("data-rmm-space")));
    return;
  }
  const op = t.closest("[data-rmm-op]");
  if (op && active) {
    const o = op.getAttribute("data-rmm-op");
    if (o === "in") active.api.zoom(1.25);
    else if (o === "out") active.api.zoom(0.8);
    else if (o === "fit") active.api.fit();
    else if (o === "now") active.api.centerOn("now");
    else if (o === "full") toggleFull(page);
    return;
  }
  if (t.closest("[data-rmm-aside-close]")) {
    const aside = page.querySelector("[data-rmm-aside]");
    if (aside) aside.hidden = true;
  } else if (t.closest("[data-rmm-exit]") && fullEl()) {
    exitFull();
  }
}

// Double-click on the value puts the spacing back to 1.
function onDbl(e) {
  const t = e.target;
  if (t && t.closest && t.closest('[data-rmm-space="reset"]')) setSpacing(1);
}

function onChange(e) {
  const t = e.target;
  if (!t || !t.hasAttribute || !t.hasAttribute("data-rmm-model")) return;
  ui.model = t.value;
  rerender();
}

function onFullChange() {
  // The browser left full screen (its own Escape): unpin too.
  if (ui.full && document.fullscreenEnabled && !document.fullscreenElement && fullAsked) {
    fullAsked = false;
    exitFull();
    return;
  }
  fullAsked = !!document.fullscreenElement;
  const page = document.querySelector("[data-rmm-page]");
  const btn = page ? page.querySelector('[data-rmm-op="full"]') : null;
  if (btn) {
    btn.textContent = fullWord();
    btn.setAttribute("aria-label", fullWord());
    btn.setAttribute("title", fullWord());
  }
  syncAside();
  if (active && active.api) setTimeout(function () {
    if (active) active.api.fit();
  }, 50);
}

// Document listeners, once. Each one returns at once unless the event comes from the Map.
function wire() {
  if (wired || typeof document === "undefined") return;
  wired = true;
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("dblclick", onDbl);
  document.addEventListener("keydown", onMenuKey, true);
  document.addEventListener("fullscreenchange", onFullChange);
}

