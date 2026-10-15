// Workflow diagram renderer (WP72, R7.14 C). buildMap(graph, lay, pid) draws the left-to-right flow of flowLayout()
// (graph/layout.js): Start and End pills, one frame per phase (a folded phase is a card), a card per node by state,
// orthogonal edges with rounded corners and one arrowhead marker per class, parallel brackets, the "You are here" flag
// and an empty copy slot (class wfg-ref) in every node. lay is the flowLayout() result, or the layout() result whose
// `flow` field holds it. Markup comes from createElementNS: no style attributes, no handlers (CSP), and colour comes
// from the classes in graph.css. Loaded only in the Map view. Focus mode and the closure helpers are unchanged.

import { mountViewport } from "./viewport.js";

const NS = "http://www.w3.org/2000/svg";
const PAD = 16;
const MARKERS = ["sequence", "dependency", "handoff", "blocker", "lead"];
const GLYPH = { done: "✓", doing: "●", todo: "○", blocked: "✕", defer: "–" };
const FOLD_OPEN = "▾";
const FOLD_SHUT = "▸";
// Characters that fit one line of a task title (the box is 200 wide, less the 10 px inset and the 28 px copy slot).
const TITLE_CHARS = 20;
const CHAR_PX = 6.4;

function el(tag, attrs, kids) {
  const node = document.createElementNS(NS, tag);
  Object.keys(attrs || {}).forEach(function (k) {
    if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, String(attrs[k]));
  });
  (kids || []).forEach(function (kid) {
    if (kid) node.appendChild(kid);
  });
  return node;
}

function txt(s) {
  return document.createTextNode(String(s));
}

function clip(s, max) {
  const t = String(s || "");
  return t.length > max ? t.slice(0, max - 1) + "…" : t;
}

// Two lines of a title, broken at spaces. The second line ends in an ellipsis when the rest does not fit.
function titleLines(s, max) {
  const words = String(s || "").split(/\s+/).filter(Boolean);
  const first = [];
  let k = 0;
  while (k < words.length && (first.join(" ") + " " + words[k]).trim().length <= max) first.push(words[k++]);
  if (!first.length && k < words.length) first.push(words[k++]);
  return [clip(first.join(" "), max), clip(words.slice(k).join(" "), max)];
}

// "P4 · name" for a frame, ellipsized to the characters that fit in room pixels. The full text is in a <title>.
function frameName(f) {
  return f.label && f.label !== f.lane ? f.lane + " · " + f.label : f.lane;
}

function frameTitle(f, room) {
  return clip(frameName(f), Math.max(6, Math.floor(room / CHAR_PX)));
}

function push(map, key, value) {
  if (!map.has(key)) map.set(key, []);
  map.get(key).push(value);
}

// The ids reachable from key, following edges forward (downstream) or backward (upstream), over all edge types. The
// adjacency is built once, and the queue is read by index (no shift).
function reach(edges, start, forward) {
  const next = new Map();
  edges.forEach(function (e) {
    push(next, forward ? e.from : e.to, forward ? e.to : e.from);
  });
  const seen = new Set([start]);
  const queue = [start];
  for (let i = 0; i < queue.length; i += 1) {
    (next.get(queue[i]) || []).forEach(function (to) {
      if (!seen.has(to)) {
        seen.add(to);
        queue.push(to);
      }
    });
  }
  return seen;
}

// Focus mode: the node itself, its upstream and its downstream closure. Null when no node is focused.
export function closureOf(graph, key) {
  if (!key || !graph) return null;
  const known = key === "start" || key === "end" || (graph.nodes || []).some(function (n) {
    return n.id === key;
  });
  if (!known) return null;
  const up = reach(graph.edges || [], key, false);
  const down = reach(graph.edges || [], key, true);
  const out = new Set();
  up.forEach(function (id) {
    out.add(id);
  });
  down.forEach(function (id) {
    out.add(id);
  });
  return out;
}

function statusOf(n) {
  return n.status || "todo";
}

function glyphOf(status) {
  return GLYPH[status] || GLYPH.todo;
}

function dateText(ms) {
  if (typeof ms !== "number" || !isFinite(ms)) return "";
  const d = new Date(ms);
  return isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
}

function frameLabel(f) {
  return "Phase " + f.label + ", " + f.done + " of " + f.total + " done";
}

function numsOf(f) {
  const k = f.tokensK ? "  " + (Math.round(f.tokensK * 10) / 10) + "K" : "";
  return f.done + "/" + f.total + k;
}

function nodeLabel(n) {
  if (n.type === "task") {
    const jobs = n.jobs ? ", " + n.jobs + (n.jobs === 1 ? " job" : " jobs") : "";
    const after = n.after ? ", after " + n.after + " task" + (n.after === 1 ? "" : "s") : "";
    return "Task " + n.label + ", " + statusOf(n) + after + jobs;
  }
  if (n.type === "job") {
    if (n.more) return "Older jobs of task " + n.task + ", " + n.more + " more";
    return "Job " + (n.job || "") + " " + (n.model || "") + ", " + (n.running ? "running" : statusOf(n)) +
      ", task " + n.task;
  }
  if (n.type === "issue") return "Blocking issue " + n.issue + " " + n.label;
  if (n.type === "queue") return n.label + " waiting";
  return n.label || n.id;
}

function boxAttrs(p) {
  return { x: p.x, y: p.y, width: p.w, height: p.h };
}

function taskNode(n, p, pid) {
  const st = statusOf(n);
  const x = p.x;
  const y = p.y;
  const lines = titleLines(n.title || n.label, TITLE_CHARS);
  return el("g", { class: "wfg-n wfg-task wfg-s-" + st, tabindex: -1, role: "button", "aria-label": nodeLabel(n),
    "data-wf-item": n.id, "data-wf-task": n.task || "", "data-wf-pid": pid, "data-cx": x + p.w / 2,
    "data-cy": y + p.h / 2 }, [
    el("title", null, [txt(n.title || n.label || n.id)]),
    el("rect", Object.assign({ class: "wfg-box", rx: 6, fill: st === "blocked" ? "url(#wfg-hatch)" : null },
      boxAttrs(p))),
    el("text", { class: "wfg-glyph", x: x + 10, y: y + 17 }, [txt(glyphOf(st))]),
    el("text", { class: "wfg-id", x: x + 26, y: y + 17 }, [txt(n.task || "")]),
    el("text", { class: "wfg-t", x: x + 10, y: y + 31 }, [txt(lines[0])]),
    lines[1] ? el("text", { class: "wfg-t", x: x + 10, y: y + 44 }, [txt(lines[1])]) : null,
    el("g", { class: "wfg-ref" }),
  ]);
}

function jobNode(n, p, pid) {
  const cls = "wfg-n wfg-pill wfg-m-" + (n.model || "other") + " wfg-s-" + (n.status || "todo") +
    (n.running ? " wfg-run" : "");
  const label = n.more ? "+" + n.more : clip(n.label, 5);
  return el("g", { class: cls, tabindex: -1, role: "button", "aria-label": nodeLabel(n),
    "data-wf-item": n.id, "data-wf-task": n.task || "", "data-wf-pid": pid,
    "data-cx": p.x + p.w / 2, "data-cy": p.y + p.h / 2 }, [
    el("rect", Object.assign({ rx: 10 }, boxAttrs(p))),
    el("text", { class: "wfg-pt", x: p.x + p.w / 2, y: p.y + 14, "text-anchor": "middle" }, [txt(label)]),
  ]);
}

function issueNode(n, p, pid) {
  const x = p.x;
  const y = p.y;
  const w = p.w;
  const h = p.h;
  const d = "M" + (x + 10) + " " + y + "L" + (x + w - 10) + " " + y + "L" + (x + w) + " " + (y + h / 2) +
    "L" + (x + w - 10) + " " + (y + h) + "L" + (x + 10) + " " + (y + h) + "L" + x + " " + (y + h / 2) + "Z";
  return el("g", { class: "wfg-n wfg-issue wfg-s-blocked", tabindex: -1, role: "button", "aria-label": nodeLabel(n),
    "data-wf-item": n.id, "data-wf-task": n.task || "", "data-wf-pid": pid, "data-cx": x + w / 2,
    "data-cy": y + h / 2 }, [
    el("path", { class: "wfg-box", d: d }),
    el("text", { class: "wfg-t", x: x + w / 2, y: y + h / 2 + 4, "text-anchor": "middle" }, [txt(clip(n.label, 22))]),
  ]);
}

function queueNode(n, p, pid) {
  return el("g", { class: "wfg-n wfg-queue", tabindex: -1, role: "button", "aria-label": nodeLabel(n),
    "data-wf-item": n.id, "data-wf-task": "", "data-wf-pid": pid, "data-cx": p.x + p.w / 2,
    "data-cy": p.y + p.h / 2 }, [
    el("rect", Object.assign({ rx: 10 }, boxAttrs(p))),
    el("text", { class: "wfg-t", x: p.x + p.w / 2, y: p.y + p.h / 2 + 4, "text-anchor": "middle" }, [txt(n.label)]),
  ]);
}

// A folded phase's done tasks: one focusable node with no task to open.
function collapseNode(n, p, pid) {
  return el("g", { class: "wfg-n wfg-task wfg-s-done", tabindex: -1, role: "button", "aria-label": n.label,
    "data-wf-item": n.id, "data-wf-task": "", "data-wf-pid": pid, "data-cx": p.x + p.w / 2,
    "data-cy": p.y + p.h / 2 }, [
    el("rect", Object.assign({ class: "wfg-box", rx: 6 }, boxAttrs(p))),
    el("text", { class: "wfg-glyph", x: p.x + 10, y: p.y + 18 }, [txt(glyphOf("done"))]),
    el("text", { class: "wfg-t", x: p.x + 26, y: p.y + 26 }, [txt(clip(n.label, 22))]),
  ]);
}

// A folded phase: a 200 by 56 card with its progress and an expand glyph. The card is the node for that frame.
function cardNode(f, p, pid) {
  const st = f.total > 0 && f.done >= f.total ? "done" : "todo";
  return el("g", { class: "wfg-n wfg-card wfg-s-" + st, tabindex: -1, role: "button",
    "aria-label": frameLabel(f) + ", folded. Expand", "data-wf-item": f.id, "data-wf-task": "", "data-wf-pid": pid,
    "data-cx": p.x + p.w / 2, "data-cy": p.y + p.h / 2 }, [
    el("rect", { class: "wfg-box", rx: 8, x: p.x, y: p.y, width: p.w, height: p.h }),
    el("text", { class: "wfg-glyph", x: p.x + 12, y: p.y + 24 }, [txt(glyphOf(st))]),
    el("text", { class: "wfg-t", x: p.x + 28, y: p.y + 24 }, [txt(frameTitle(f, p.w - 28 - 24))]),
    el("text", { class: "wfg-num", x: p.x + 12, y: p.y + 45 }, [txt(numsOf(f))]),
    el("text", { class: "wfg-fold-glyph", x: p.x + p.w - 14, y: p.y + 31, "text-anchor": "middle" }, [txt(FOLD_SHUT)]),
  ]);
}

// The title tab of an open phase: id and name on the left, done/total and tokens K on the right.
function frameBand(f) {
  const room = f.title.w - 16 - numsOf(f).length * CHAR_PX - 12;
  return el("g", { class: "wfg-frame", role: "group", "aria-label": frameLabel(f) }, [
    el("title", null, [txt(frameName(f))]),
    el("rect", { class: "wfg-band", x: f.x, y: f.y, width: f.w, height: f.h, rx: 8 }),
    el("rect", { class: "wfg-tab", x: f.title.x, y: f.title.y, width: f.title.w, height: f.title.h, rx: 4 }),
    el("text", { class: "wfg-ph", x: f.title.x + 8, y: f.title.y + 17 }, [txt(frameTitle(f, room))]),
    el("text", { class: "wfg-num", x: f.slot.x - 6, y: f.title.y + 17, "text-anchor": "end" }, [txt(numsOf(f))]),
  ]);
}

// The fold toggle of an open phase, placed before the phase's first node in focus order.
function foldNode(f, pid) {
  const s = f.slot;
  return el("g", { class: "wfg-fold", tabindex: -1, role: "button", "aria-label": "Collapse phase " + f.label,
    "aria-expanded": "true", "data-wf-fold": f.id, "data-wf-pid": pid,
    "data-cx": s.x + s.w / 2, "data-cy": s.y + s.h / 2 }, [
    el("rect", { class: "wfg-fold-box", x: s.x, y: s.y, width: s.w, height: s.h, rx: 4 }),
    el("text", { class: "wfg-glyph", x: s.x + s.w / 2, y: s.y + 16, "text-anchor": "middle" }, [txt(FOLD_OPEN)]),
  ]);
}

// Start and End: pills at the ends of the path. Start shows the project and its first date; End shows "n left".
function endpointNode(id, p, pid, label, sub) {
  return el("g", { class: "wfg-n wfg-end wfg-" + id, tabindex: -1, role: "button",
    "aria-label": sub ? label + ", " + sub : label, "data-wf-item": id, "data-wf-task": "", "data-wf-pid": pid,
    "data-cx": p.x + p.w / 2, "data-cy": p.y + p.h / 2 }, [
    el("rect", { class: "wfg-pill-box", rx: 22, x: p.x, y: p.y, width: p.w, height: p.h }),
    el("text", { class: "wfg-pt", x: p.x + p.w / 2, y: p.y + 18, "text-anchor": "middle" }, [txt(clip(label, 16))]),
    el("text", { class: "wfg-num", x: p.x + p.w / 2, y: p.y + 34, "text-anchor": "middle" }, [txt(sub || "")]),
  ]);
}

function parallelNode(b) {
  return el("g", { class: "wfg-par-group", role: "group", "aria-label": "Parallel work, " + b.members.length +
    " tasks" }, [el("rect", { class: "wfg-par", x: b.x, y: b.y, width: b.w, height: b.h, rx: 8 })]);
}

// The "You are here" flag above the Now node, a bar down to it, and a 2 px halo on the node.
function nowMarks(now) {
  if (!now || !now.box) return [];
  const b = now.box;
  const halo = el("rect", { class: "wfg-halo", x: b.x - 3, y: b.y - 3, width: b.w + 6, height: b.h + 6, rx: 8 });
  if (!now.flag) return [halo];
  const f = now.flag;
  const bottom = f.y + f.h;
  const bar = b.y + b.h > bottom ? el("rect", { class: "wfg-nowbar", x: b.x - 6, y: bottom, width: 3,
    height: b.y + b.h - bottom }) : null;
  const flag = el("g", { class: "wfg-flag", role: "img", "aria-label": "You are here" }, [
    el("rect", { class: "wfg-flag-box", x: f.x, y: f.y, width: f.w, height: f.h, rx: 4 }),
    el("text", { class: "wfg-flag-t", x: f.x + f.w / 2, y: f.y + 14, "text-anchor": "middle" }, [txt("You are here")]),
  ]);
  return [halo, bar, flag];
}

// Smooth path through the route points: one cubic Bezier per segment, with horizontal tangents at both ends.
function roundPath(pts) {
  if (!Array.isArray(pts) || pts.length < 2) return null;
  let d = "M" + pts[0][0] + " " + pts[0][1];
  for (let i = 1; i < pts.length; i += 1) {
    const a = pts[i - 1];
    const b = pts[i];
    const mx = (a[0] + b[0]) / 2;
    d += "C" + mx + " " + a[1] + " " + mx + " " + b[1] + " " + b[0] + " " + b[1];
  }
  return d;
}

function edgeNode(e, d, lead) {
  const type = lead ? "lead" : e.type;
  const marker = MARKERS.indexOf(type) >= 0 ? "url(#wfg-arrow-" + type + ")" : null;
  return el("path", { class: "wfg-e wfg-e-" + e.type + (lead ? " wfg-e-lead" : ""), d: d, "marker-end": marker,
    "data-from": e.from, "data-to": e.to });
}

function markerFor(type) {
  return el("marker", { id: "wfg-arrow-" + type, viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 7,
    markerHeight: 7, orient: "auto" }, [el("path", { class: "wfg-arrow wfg-arrow-" + type, d: "M0 0L8 4L0 8z" })]);
}

function nodeFor(n, p, pid) {
  if (n.type === "task") return n.id.indexOf("collapse:") === 0 ? collapseNode(n, p, pid) : taskNode(n, p, pid);
  if (n.type === "job") return jobNode(n, p, pid);
  if (n.type === "issue") return issueNode(n, p, pid);
  if (n.type === "queue") return queueNode(n, p, pid);
  return null;
}

// The whole diagram as one SVG element. Nodes are appended in path order, so Tab follows the path.
export function buildMap(graph, lay, pid) {
  const g = graph && Array.isArray(graph.nodes) ? graph : { nodes: [], edges: [] };
  const flow = lay && lay.flow && !lay.frames ? lay.flow : lay || {};
  const boxes = flow.boxes || {};
  const path = Array.isArray(flow.path) ? flow.path : [];
  const frames = Array.isArray(flow.frames) ? flow.frames : [];
  const routes = flow.routes || {};
  const byId = new Map(g.nodes.map(function (n) {
    return [n.id, n];
  }));
  const framesById = new Map(frames.map(function (f) {
    return [f.id, f];
  }));
  const framesByLane = new Map(frames.map(function (f) {
    return [f.lane, f];
  }));
  const idx = new Map(path.map(function (id, i) {
    return [id, i];
  }));
  const curIdx = flow.now && idx.has(flow.now.node) ? idx.get(flow.now.node) : -1;
  const pillsOf = new Map();
  const issuesOf = new Map();
  g.nodes.forEach(function (n) {
    if (n.type === "job" && n.parent) push(pillsOf, n.parent, n);
    if (n.type === "issue" && n.task) push(issuesOf, "task:" + n.task, n);
  });

  const nodes = [];
  const done = new Set();
  const folded = new Set();
  const put = function (id, node) {
    done.add(id);
    if (!node) return;
    if (curIdx >= 0 && idx.has(id) && idx.get(id) > curIdx) {
      node.setAttribute("class", node.getAttribute("class") + " wfg-after");
    }
    nodes.push(node);
  };
  const emit = function (n) {
    if (done.has(n.id) || !boxes[n.id]) return;
    put(n.id, nodeFor(n, boxes[n.id], pid));
  };
  const foldFor = function (lane) {
    const f = framesByLane.get(lane);
    if (!f || f.collapsed || folded.has(f.id)) return;
    folded.add(f.id);
    nodes.push(foldNode(f, pid));
  };

  path.forEach(function (id) {
    if (id === "start" || id === "end") {
      const p = boxes[id];
      if (!p) return;
      if (id === "start") {
        const s = g.start || {};
        put(id, endpointNode(id, p, pid, "Start: " + (s.label || "Project"), dateText(s.date)));
      } else {
        put(id, endpointNode(id, p, pid, "End", ""));
      }
      return;
    }
    const fr = framesById.get(id);
    if (fr) {
      if (fr.collapsed && boxes[id]) put(id, cardNode(fr, boxes[id], pid));
      return;
    }
    const n = byId.get(id);
    if (!n) return;
    foldFor(n.lane);
    (issuesOf.get(id) || []).forEach(emit);
    emit(n);
    (pillsOf.get(id) || []).forEach(emit);
  });
  g.nodes.forEach(function (n) {
    if (n.type !== "phase") emit(n);
  });

  const edges = [];
  const seenEdge = new Set();
  const before = function (id) {
    return curIdx >= 0 && idx.has(id) && idx.get(id) <= curIdx;
  };
  // Only handoff, dependency and blocker edges are drawn (WORKFLOW-DIAGRAM-SPEC); sequence edges only steer the layout.
  (g.edges || []).forEach(function (e) {
    if (!e || seenEdge.has(e.id)) return;
    seenEdge.add(e.id);
    const d = roundPath(routes[e.id]);
    if (!d) return;
    const lead = e.type === "sequence" && before(e.from) && before(e.to);
    edges.push(edgeNode(e, d, lead));
  });

  const bands = [];
  frames.forEach(function (f) {
    if (!f.collapsed) bands.push(frameBand(f));
  });
  (flow.parallel || []).forEach(function (b) {
    bands.push(parallelNode(b));
  });

  const defs = el("defs", null, MARKERS.map(markerFor).concat([
    el("pattern", { id: "wfg-hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse",
      patternTransform: "rotate(45)" }, [el("rect", { class: "wfg-hatch-bg", width: 6, height: 6 }),
      el("path", { class: "wfg-hatch-line", d: "M0 0V6" })]),
  ]));
  const vp = el("g", { class: "wfg-vp", transform: "translate(0 0) scale(1)" });
  vp.appendChild(el("g", { class: "wfg-bands" }, bands));
  vp.appendChild(el("g", { class: "wfg-edges" }, edges));
  vp.appendChild(el("g", { class: "wfg-nodes" }, nodes.concat(nowMarks(flow.now))));
  // tabindex 0 puts the canvas itself in the tab order: the one tab stop, so + - 0 Escape work from it. The nodes are
  // tabindex -1 and take focus from the arrow keys (viewport.js), which keeps Tab from walking every node.
  // The global :focus-visible outline in base.css is the focus ring.
  const svg = el("svg", { class: "wfg-svg", role: "group", tabindex: 0, "aria-label": "Workflow diagram",
    "aria-describedby": "wf-legend" }, [defs, vp]);
  return { svg: svg, vp: vp, box: { w: flow.width || 0, h: flow.height || 0 } };
}

// Focus mode on an existing SVG: classes only. Nodes outside the closure dim, and so do edges that leave it.
export function applyFocus(svg, closure, focusKey) {
  svg.querySelectorAll("[data-wf-item]").forEach(function (g) {
    const id = g.getAttribute("data-wf-item");
    const inside = !closure || closure.has(id);
    g.classList.toggle("wfg-dim", !inside);
    g.classList.toggle("wfg-hot", id === focusKey);
  });
  svg.querySelectorAll(".wfg-e").forEach(function (p) {
    const inside = !closure || (closure.has(p.getAttribute("data-from")) && closure.has(p.getAttribute("data-to")));
    p.classList.toggle("wfg-dim", !inside);
  });
}

// Mounts the diagram into host (an empty element) and starts the viewport. st: { graph, lay, pid, focus, view, taps,
// fit, onTap, onClear, onView }. Returns the viewport controls.
export function mountMap(host, st) {
  const built = buildMap(st.graph, st.lay, st.pid);
  host.appendChild(built.svg);
  applyFocus(built.svg, closureOf(st.graph, st.focus), st.focus);
  return mountViewport(built.svg, built.vp, {
    view: st.view || { k: 1, x: PAD, y: PAD },
    box: built.box,
    taps: st.taps,
    fit: st.fit,
    onTap: st.onTap,
    onClear: st.onClear,
    onView: st.onView,
  });
}
