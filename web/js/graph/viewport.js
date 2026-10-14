// Workflow diagram viewport (WP72, WP70-B). The gesture state machine is pure (pointer and wheel input in, view out),
// so the node tests can drive it with synthetic events. mountViewport() binds it to one SVG with Pointer Events and
// pointer capture: one pointer pans, two pinch-zoom, the wheel zooms at the cursor, and a pointer that moves 6 px or
// less is a tap (select). Two taps within 300 ms and 24 px zoom 2x. The view is { k, x, y } in screen pixels; the
// viewport <g> gets transform="translate(x y) scale(k)" as an attribute. Keys: + and - zoom, 0 fits, Shift+arrows pan
// 40 px, arrows move focus to the nearest node in that direction, Escape clears the focus.

export const MIN_K = 0.25;
export const MAX_K = 3;
export const TAP_PX = 6;
const DOUBLE_MS = 300;
const DOUBLE_PX = 24;
const PAN_STEP = 40;
const FIT_PAD = 16;
const OPEN_MIN_K = 0.6;
const STEP = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

export function clampK(k) {
  return Math.min(MAX_K, Math.max(MIN_K, k));
}

// Scale to k while keeping the point (cx, cy) fixed on screen.
export function zoomAt(view, k, cx, cy) {
  const next = clampK(k);
  const r = next / view.k;
  return { k: next, x: cx - (cx - view.x) * r, y: cy - (cy - view.y) * r };
}

// The view that shows a box of {w, h} layout units inside a screen of {w, h} pixels, centred.
export function fitView(box, size) {
  const k = clampK(Math.min((size.w - 2 * FIT_PAD) / Math.max(1, box.w), (size.h - 2 * FIT_PAD) / Math.max(1, box.h)));
  return { k: k, x: (size.w - box.w * k) / 2, y: (size.h - box.h * k) / 2 };
}

// The view on open: the width fits at most 1:1, but not below 0.6 (a wide time layout is panned, not shrunk), and the
// top stays in view.
export function openView(box, size) {
  const k = Math.max(OPEN_MIN_K, Math.min(1, (size.w - 2 * FIT_PAD) / Math.max(1, box.w)));
  return { k: clampK(k), x: Math.max(FIT_PAD, (size.w - box.w * k) / 2), y: FIT_PAD };
}

// taps is an object { last } that the caller keeps, so a double tap still counts after the SVG is rebuilt.
export function createGestures(start, taps) {
  let v = { k: start.k, x: start.x, y: start.y };
  const pts = new Map();
  let base = v;
  let sx = 0;
  let sy = 0;
  let moved = false;
  let pinch = 0;
  const span = function () {
    const both = Array.from(pts.values());
    return Math.hypot(both[0].x - both[1].x, both[0].y - both[1].y);
  };
  const centre = function () {
    const both = Array.from(pts.values());
    return { x: (both[0].x + both[1].x) / 2, y: (both[0].y + both[1].y) / 2 };
  };
  return {
    get view() {
      return v;
    },
    setView(next) {
      v = { k: clampK(next.k), x: next.x, y: next.y };
      base = v;
      return v;
    },
    zoomBy(factor, cx, cy) {
      v = zoomAt(v, v.k * factor, cx, cy);
      base = v;
      return v;
    },
    down(id, x, y) {
      pts.set(id, { x: x, y: y });
      if (pts.size === 1) {
        base = v;
        sx = x;
        sy = y;
        moved = false;
      } else {
        moved = true;
        pinch = span();
      }
    },
    move(id, x, y) {
      const p = pts.get(id);
      if (!p) return v;
      p.x = x;
      p.y = y;
      if (pts.size === 1) {
        if (!moved && Math.hypot(x - sx, y - sy) > TAP_PX) moved = true;
        if (moved) v = { k: base.k, x: base.x + x - sx, y: base.y + y - sy };
      } else if (pts.size >= 2) {
        const d = span();
        const m = centre();
        if (pinch > 0 && d > 0) v = zoomAt(v, v.k * d / pinch, m.x, m.y);
        pinch = d;
      }
      return v;
    },
    wheel(deltaY, cx, cy) {
      v = zoomAt(v, v.k * Math.exp(-deltaY * 0.002), cx, cy);
      base = v;
      return v;
    },
    // Returns "tap", "double", "end" (a pan or pinch ended) or "none" (one of several pointers lifted).
    up(id, x, y, t) {
      const was = pts.size;
      pts.delete(id);
      if (pts.size === 1) {
        const rest = Array.from(pts.values())[0];
        base = v;
        sx = rest.x;
        sy = rest.y;
        moved = true;
      }
      if (was >= 2) return "none";
      if (was !== 1 || moved) return "end";
      const last = taps.last;
      if (last && t - last.t < DOUBLE_MS && Math.hypot(x - last.x, y - last.y) < DOUBLE_PX) {
        taps.last = null;
        v = zoomAt(v, v.k * 2, x, y);
        base = v;
        return "double";
      }
      taps.last = { t: t, x: x, y: y };
      return "tap";
    },
  };
}

// What a key does: zoom, fit, pan (Shift+arrows), focus (arrows) or clear (Escape). Null for every other key.
export function keyPlan(key, shift) {
  if (key === "+" || key === "=") return { op: "zoom", f: 1.25 };
  if (key === "-" || key === "_") return { op: "zoom", f: 0.8 };
  if (key === "0") return { op: "fit" };
  if (key === "Escape") return { op: "clear" };
  const dir = STEP[key];
  if (!dir) return null;
  if (shift) return { op: "pan", dx: -dir[0] * PAN_STEP, dy: -dir[1] * PAN_STEP };
  return { op: "focus", dir: dir };
}

// The node in a direction from `from`: ahead of it, the least distance along the axis with 2x weight on the offset.
export function nearest(nodes, from, dir) {
  let best = null;
  let score = Infinity;
  nodes.forEach(function (n) {
    if (n.key === from.key) return;
    const dx = n.cx - from.cx;
    const dy = n.cy - from.cy;
    const along = dx * dir[0] + dy * dir[1];
    if (along <= 0) return;
    const across = Math.abs(dx * dir[1]) + Math.abs(dy * dir[0]);
    const s = along + 2 * across;
    if (s < score) {
      score = s;
      best = n;
    }
  });
  return best;
}

function closestNode(el) {
  return el && typeof el.closest === "function" ? el.closest("[data-wf-item]") : null;
}

// Binds the gestures and keys to one SVG. opts: { view, box: {w, h}, taps, fit, onTap(el), onClear(), onView(view) }.
// Returns { zoom(f), fit(), actual(), view() } for the controls. Nothing here runs in node.
export function mountViewport(svg, vpG, opts) {
  const size = function () {
    const r = svg.getBoundingClientRect();
    return { w: r.width || opts.box.w, h: r.height || opts.box.h };
  };
  const local = function (e) {
    const r = svg.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const gest = createGestures(opts.view, opts.taps || { last: null });
  let downEl = null;
  const paint = function () {
    const v = gest.view;
    const at = "translate(" + v.x.toFixed(1) + " " + v.y.toFixed(1) + ") scale(" + v.k.toFixed(3) + ")";
    vpG.setAttribute("transform", at);
    if (opts.onView) opts.onView(v);
  };
  const fit = function () {
    gest.setView(fitView(opts.box, size()));
    paint();
  };
  const zoom = function (f) {
    const s = size();
    gest.zoomBy(f, s.w / 2, s.h / 2);
    paint();
  };
  svg.addEventListener("pointerdown", function (e) {
    if (e.button > 0) return;
    const p = local(e);
    downEl = e.target;
    try {
      svg.setPointerCapture(e.pointerId);
    } catch (err) {
      // A pointer that is not active (a synthetic event) cannot be captured; the gesture still runs.
    }
    gest.down(e.pointerId, p.x, p.y);
  });
  svg.addEventListener("pointermove", function (e) {
    const p = local(e);
    gest.move(e.pointerId, p.x, p.y);
    paint();
  });
  const release = function (e) {
    const p = local(e);
    const res = gest.up(e.pointerId, p.x, p.y, e.timeStamp);
    paint();
    if (res !== "tap") return;
    const node = closestNode(downEl);
    if (node) opts.onTap(node);
    else opts.onClear();
  };
  svg.addEventListener("pointerup", release);
  svg.addEventListener("pointercancel", function (e) {
    gest.up(e.pointerId, 0, 0, e.timeStamp);
    paint();
  });
  svg.addEventListener("wheel", function (e) {
    e.preventDefault();
    const p = local(e);
    gest.wheel(e.deltaY, p.x, p.y);
    paint();
  }, { passive: false });
  svg.addEventListener("keydown", function (e) {
    const plan = keyPlan(e.key, e.shiftKey);
    if (!plan) return;
    e.preventDefault();
    if (plan.op === "zoom") zoom(plan.f);
    else if (plan.op === "fit") fit();
    else if (plan.op === "clear") opts.onClear();
    else if (plan.op === "pan") {
      const v = gest.view;
      gest.setView({ k: v.k, x: v.x + plan.dx, y: v.y + plan.dy });
      paint();
    } else moveFocus(e, plan.dir);
  });
  function moveFocus(e, dir) {
    const cur = closestNode(e.target);
    if (!cur) return;
    const nodes = Array.from(svg.querySelectorAll("[data-wf-item]")).map(function (el) {
      return { key: el.getAttribute("data-wf-item"), cx: Number(el.getAttribute("data-cx")),
        cy: Number(el.getAttribute("data-cy")), el: el };
    });
    const from = nodes.find(function (n) {
      return n.el === cur;
    });
    const next = from ? nearest(nodes, from, dir) : null;
    if (!next) return;
    next.el.focus({ preventScroll: true });
    const s = size();
    const v = gest.view;
    const sx = v.k * from.cx + v.x;
    const sy = v.k * from.cy + v.y;
    const nx = v.k * next.cx + v.x;
    const ny = v.k * next.cy + v.y;
    if (nx < 0 || ny < 0 || nx > s.w || ny > s.h) {
      gest.setView({ k: v.k, x: v.x + (sx - nx), y: v.y + (sy - ny) });
      paint();
    }
  }
  if (opts.fit) gest.setView(openView(opts.box, size()));
  paint();
  return { zoom: zoom, fit: fit, actual: function () {
    const s = size();
    gest.setView(zoomAt(gest.view, 1, s.w / 2, s.h / 2));
    paint();
  }, view: function () {
    return gest.view;
  } };
}
