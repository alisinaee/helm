// Workflow diagram renderer (WP72, WP70-B). buildMap(graph, lay) builds one SVG with createElementNS: lane bands,
// edges, nodes and a viewport <g> that viewport.js moves. Markup is never built from strings, and there are no style
// attributes: geometry is SVG attributes, colour comes from classes on the tokens, and the hatch pattern is defined
// once in <defs>. Loaded only in the Map view. Every node is a focusable <g role="button"> with an aria-label.
// closureOf() and the focus classes implement focus mode.

import { mountViewport } from "./viewport.js";

const NS = "http://www.w3.org/2000/svg";
const PAD = 16;

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

// The ids reachable from key, following edges forward (downstream) or backward (upstream), over all edge types.
function reach(edges, start, forward) {
  const seen = new Set([start]);
  const queue = [start];
  while (queue.length) {
    const cur = queue.shift();
    edges.forEach(function (e) {
      const from = forward ? e.from : e.to;
      const to = forward ? e.to : e.from;
      if (from === cur && !seen.has(to)) {
        seen.add(to);
        queue.push(to);
      }
    });
  }
  return seen;
}

// Focus mode: the node itself, its upstream and its downstream closure. Null when no node is focused.
export function closureOf(graph, key) {
  if (!key || !graph || !graph.nodes.some(function (n) {
    return n.id === key;
  })) return null;
  const up = reach(graph.edges, key, false);
  const down = reach(graph.edges, key, true);
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
  if (n.type === "phase") return "Phase " + n.label + ", " + n.done + " of " + n.total + " done";
  return n.label || n.id;
}

function boxAttrs(p) {
  return { x: p.x, y: p.y, width: p.w, height: p.h };
}

function taskNode(n, p, pid) {
  const x = p.x;
  const y = p.y;
  const cls = "wfg-n wfg-task wfg-s-" + statusOf(n);
  return el("g", { class: cls, tabindex: 0, role: "button", "aria-label": nodeLabel(n), "data-wf-item": n.id,
    "data-wf-task": n.task || "", "data-wf-pid": pid, "data-cx": x + p.w / 2, "data-cy": y + p.h / 2 }, [
    el("rect", Object.assign({ class: "wfg-box", rx: 6, fill: statusOf(n) === "blocked" ? "url(#wfg-hatch)" : null },
      boxAttrs(p))),
    el("circle", { class: "wfg-dot", cx: x + 10, cy: y + 14, r: 4 }),
    el("text", { class: "wfg-id", x: x + 19, y: y + 18 }, [txt(n.task || "")]),
    n.after ? el("text", { class: "wfg-sub", x: x + p.w - 8, y: y + 18, "text-anchor": "end" },
      [txt("after " + n.after)]) : null,
    el("text", { class: "wfg-t", x: x + 10, y: y + 35 }, [txt(clip(n.title || n.label, 24))]),
  ]);
}

function jobNode(n, p, pid) {
  const cls = "wfg-n wfg-pill wfg-m-" + (n.model || "other") + (n.running ? " wfg-run" : "");
  const label = n.more ? "+" + n.more : clip(n.label, 5);
  return el("g", { class: cls, tabindex: 0, role: "button", "aria-label": nodeLabel(n),
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
  return el("g", { class: "wfg-n wfg-issue wfg-s-blocked", tabindex: 0, role: "button", "aria-label": nodeLabel(n),
    "data-wf-item": n.id, "data-wf-task": n.task || "", "data-wf-pid": pid, "data-cx": x + w / 2,
    "data-cy": y + h / 2 }, [
    el("path", { class: "wfg-box", d: d }),
    el("text", { class: "wfg-t", x: x + w / 2, y: y + h / 2 + 4, "text-anchor": "middle" }, [txt(clip(n.label, 22))]),
  ]);
}

function queueNode(n, p, pid) {
  return el("g", { class: "wfg-n wfg-queue", tabindex: 0, role: "button", "aria-label": nodeLabel(n),
    "data-wf-item": n.id, "data-wf-task": "", "data-wf-pid": pid, "data-cx": p.x + p.w / 2,
    "data-cy": p.y + p.h / 2 }, [
    el("rect", Object.assign({ rx: 10 }, boxAttrs(p))),
    el("text", { class: "wfg-t", x: p.x + p.w / 2, y: p.y + p.h / 2 + 4, "text-anchor": "middle" }, [txt(n.label)]),
  ]);
}

// A collapsed phase: one node for its done tasks, focusable, with no task to open.
function collapseNode(n, p, pid) {
  return el("g", { class: "wfg-n wfg-task wfg-s-done", tabindex: 0, role: "button", "aria-label": n.label,
    "data-wf-item": n.id, "data-wf-task": "", "data-wf-pid": pid, "data-cx": p.x + p.w / 2,
    "data-cy": p.y + p.h / 2 }, [
    el("rect", Object.assign({ rx: 6 }, boxAttrs(p))),
    el("text", { class: "wfg-t", x: p.x + 10, y: p.y + 26 }, [txt(n.label)]),
  ]);
}

// A phase band: the lane rectangle, the label on the left and the done/total and tokens K in fixed right columns.
function phaseGroup(n, p, band, width) {
  const tokens = n.tokensK ? (Math.round(n.tokensK * 10) / 10) + "K" : "";
  return el("g", { class: "wfg-phase", role: "group", "aria-label": nodeLabel(n) }, [
    el("rect", { class: "wfg-band", x: 0, y: band.y, width: width, height: band.h, rx: 6 }),
    el("text", { class: "wfg-ph", x: 10, y: p.y + 18 }, [txt(clip(n.label, 16))]),
    el("text", { class: "wfg-num", x: 150, y: p.y + 18, "text-anchor": "end" }, [txt(n.done + "/" + n.total)]),
    el("text", { class: "wfg-num", x: 150, y: p.y + 34, "text-anchor": "end" }, [txt(tokens)]),
  ]);
}

function edgePath(e, d) {
  return el("path", { class: "wfg-e wfg-e-" + e.type, d: d, "marker-end": "url(#wfg-arrow)", "data-from": e.from,
    "data-to": e.to });
}

function nodeFor(n, p, pid) {
  if (n.type === "task") return n.id.indexOf("collapse:") === 0 ? collapseNode(n, p, pid) : taskNode(n, p, pid);
  if (n.type === "job") return jobNode(n, p, pid);
  if (n.type === "issue") return issueNode(n, p, pid);
  if (n.type === "queue") return queueNode(n, p, pid);
  return null;
}

// The whole diagram as one SVG element. lay is layout(graph, ...) from graph/layout.js.
export function buildMap(graph, lay, pid) {
  const defs = el("defs", null, [
    el("marker", { id: "wfg-arrow", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 7, markerHeight: 7,
      orient: "auto-start-reverse" }, [el("path", { class: "wfg-arrow", d: "M0 0L8 4L0 8z" })]),
    el("pattern", { id: "wfg-hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse",
      patternTransform: "rotate(45)" }, [el("rect", { class: "wfg-hatch-bg", width: 6, height: 6 }),
      el("path", { class: "wfg-hatch-line", d: "M0 0V6" })]),
  ]);
  const vp = el("g", { class: "wfg-vp", transform: "translate(0 0) scale(1)" });
  const bandOf = new Map(lay.lanes.map(function (b) {
    return [b.id, b];
  }));
  const bands = [];
  const edges = [];
  const nodes = [];
  graph.nodes.forEach(function (n) {
    const p = lay.pos[n.id];
    if (!p) return;
    if (n.type === "phase") {
      const band = bandOf.get(n.lane);
      if (band) bands.push(phaseGroup(n, p, band, lay.width));
      return;
    }
    const g = nodeFor(n, p, pid);
    if (g) nodes.push(g);
  });
  graph.edges.forEach(function (e) {
    const d = lay.paths[e.id];
    if (d) edges.push(edgePath(e, d));
  });
  vp.appendChild(el("g", { class: "wfg-bands" }, bands));
  vp.appendChild(el("g", { class: "wfg-edges" }, edges));
  vp.appendChild(el("g", { class: "wfg-nodes" }, nodes));
  const svg = el("svg", { class: "wfg-svg", role: "group", "aria-label": "Workflow diagram",
    "aria-describedby": "wf-legend" }, [defs, vp]);
  return { svg: svg, vp: vp, box: { w: lay.width, h: lay.height } };
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
