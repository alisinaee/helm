// Workflow minimap (R7.14 D). A 160 by 90 SVG overview of the flow from flowLayout(): the phase frames (a folded one is
// filled), Start and End, the Now marker and the viewport rectangle. A click or drag on it centres the map through the
// controls from mountViewport(); a drag moves without animation. Pure helpers (layoutPoint, viewRect, chipsOf) are
// exported for the tests and for the narrow layout, where the view shows chipsOf() as a breadcrumb instead (CSS hides
// the minimap at 640 px and below). Markup comes from createElementNS only: no style attributes, no handlers in the
// markup (CSP), and colour comes from the classes in graph.css. Keyboard users jump with N and S on the map.

const NS = "http://www.w3.org/2000/svg";
export const MINI_W = 160;
export const MINI_H = 90;
export const NARROW_PX = 640;

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

// The layout point under a client position. The box is drawn with "meet" scaling inside rect, so the short side has
// margins; they are removed before dividing by the scale.
export function layoutPoint(box, rect, cx, cy) {
  const s = Math.min(rect.width / Math.max(1, box.w), rect.height / Math.max(1, box.h)) || 1;
  const ox = rect.left + (rect.width - box.w * s) / 2;
  const oy = rect.top + (rect.height - box.h * s) / 2;
  return { x: (cx - ox) / s, y: (cy - oy) / s };
}

// The part of the layout that the screen shows: the inverse of the viewport transform applied to the screen size.
export function viewRect(view, size) {
  const k = view.k || 1;
  return { x: -view.x / k, y: -view.y / k, w: size.w / k, h: size.h / k };
}

// One chip per phase frame, in order, for the narrow layout. current is true for the frame that holds Now.
export function chipsOf(flow) {
  const now = flow && flow.now ? flow.now.box : null;
  return ((flow && flow.frames) || []).map(function (f) {
    const current = !!now && now.x >= f.x && now.x < f.x + f.w && now.y >= f.y && now.y < f.y + f.h;
    return { id: f.id, label: f.lane + " " + f.label, done: f.done, total: f.total, collapsed: !!f.collapsed,
      current: current };
  });
}

// Builds the overview into host and keeps its rectangle in step with the viewport. st: { flow, viewport }, where
// viewport is the object mountViewport() returns. Returns { svg, stop() } (stop unsubscribes from the viewport).
export function mountMinimap(host, st) {
  const flow = st.flow || {};
  const vp = st.viewport;
  const box = { w: Math.max(1, flow.width || 1), h: Math.max(1, flow.height || 1) };
  const frames = (flow.frames || []).map(function (f) {
    return el("rect", { class: "wfm-frame" + (f.collapsed ? " wfm-fold" : ""), x: f.x, y: f.y, width: f.w,
      height: f.h });
  });
  const ends = ["start", "end"].map(function (id) {
    const b = (flow.boxes || {})[id];
    return b ? el("rect", { class: "wfm-end", x: b.x, y: b.y, width: b.w, height: b.h }) : null;
  });
  const now = flow.now ? flow.now.box : null;
  const nowMark = now ? el("rect", { class: "wfm-now", x: now.x, y: now.y, width: now.w, height: now.h }) : null;
  const view = el("rect", { class: "wfm-view", x: 0, y: 0, width: box.w, height: box.h });
  const label = "Overview of the workflow, " + frames.length + " phases. Press N for Now or S for Start on the map.";
  const svg = el("svg", { class: "wfm", width: MINI_W, height: MINI_H, viewBox: "0 0 " + box.w + " " + box.h,
    preserveAspectRatio: "xMidYMid meet", role: "group", "aria-label": label },
  frames.concat(ends, [nowMark, view]));
  let drag = false;
  const at = function (e) {
    return layoutPoint(box, svg.getBoundingClientRect(), e.clientX, e.clientY);
  };
  svg.addEventListener("pointerdown", function (e) {
    if (e.button > 0) return;
    drag = true;
    try {
      svg.setPointerCapture(e.pointerId);
    } catch (err) {
      // A synthetic pointer cannot be captured; the click still centres the map.
    }
    vp.centerOn(at(e), true);
  });
  svg.addEventListener("pointermove", function (e) {
    if (drag) vp.centerOn(at(e), true);
  });
  const end = function () {
    drag = false;
  };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  const unsubscribe = vp.subscribe(function (v) {
    const r = viewRect(v, vp.size());
    view.setAttribute("x", r.x.toFixed(1));
    view.setAttribute("y", r.y.toFixed(1));
    view.setAttribute("width", r.w.toFixed(1));
    view.setAttribute("height", r.h.toFixed(1));
  });
  host.appendChild(svg);
  return { svg: svg, stop: unsubscribe };
}
