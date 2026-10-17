// Workflow diagram viewport (WP72, WP70-B, R7.14 D). The gesture state machine is pure (pointer and wheel input in,
// view out), so the node tests can drive it with synthetic events. mountViewport() binds it to one SVG with Pointer
// Events and pointer capture: one pointer pans, two pinch-zoom, and a pointer that moves 6 px or less is a tap
// (select). Two taps within 300 ms and 24 px zoom 2x. Ctrl or Cmd+wheel (a trackpad pinch) zooms at the cursor; a plain
// wheel pans. The view is { k, x, y } in screen pixels;
// the viewport <g> gets transform="translate(x y) scale(k)" as an attribute, and every change is pushed to subscribers
// (the minimap reads it there). Keys: + and - zoom, 0 fits, Escape clears, N centres on Now, S on Start (eased, or
// instant under reduced motion), Left and Right walk the path order node by node, Up and Down move to the nearest node
// in that direction, Shift+arrows pan 40 px. Ctrl, Meta and Alt combinations are left to the browser. The SVG is the
// one tab stop; the nodes take focus by script (tabindex -1), and the arrows resume from the last node reached.

export const MIN_K = 0.25;
export const MAX_K = 3;
export const TAP_PX = 6;
export const GLIDE_MS = 240;
const DOUBLE_MS = 300;
const DOUBLE_PX = 24;
const PAN_STEP = 40;
const FIT_PAD = 16;
const OPEN_MIN_K = 0.6;
const STEP = { ArrowUp: [0, -1], ArrowDown: [0, 1] };
// The nodes in path order, and the fold toggles of open phases (they sit before their phase's first node).
const FOCUSABLE = "[data-wf-item], .wfg-fold";
// Presses on these keep their own behaviour: no pan, no preventDefault, no selection change.
const CONTROL = "button, a, input, select, textarea, label, [contenteditable], .wfg-ctl, .wfm, [data-no-pan]";

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

// Eased progress for a glide: quick start, soft landing. t is clamped to [0, 1].
export function ease(t) {
  const c = Math.min(1, Math.max(0, t));
  return 1 - Math.pow(1 - c, 3);
}

// The view between a and b at progress p (0 to 1), component by component.
export function tween(a, b, p) {
  return { k: a.k + (b.k - a.k) * p, x: a.x + (b.x - a.x) * p, y: a.y + (b.y - a.y) * p };
}

// The view at scale k that puts the layout point pt in the centre of a screen of size {w, h}.
export function centreView(k, size, pt) {
  return { k: k, x: size.w / 2 - pt.x * k, y: size.h / 2 - pt.y * k };
}

// The diagram point under the middle of the screen, for a view {k, x, y} and a size {w, h}.
export function flowCentre(view, size) {
  return { x: (size.w / 2 - view.x) / view.k, y: (size.h / 2 - view.y) / view.k };
}

// True when the person asked for less motion. Node has no matchMedia, so there it is false.
export function reducedMotion() {
  try {
    return typeof globalThis.matchMedia === "function" &&
      globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (err) {
    return false;
  }
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

// What a key does. Null for every other key. Left and Right walk the path; Up and Down go to the nearest node.
export function keyPlan(key, shift) {
  if (key === "+" || key === "=") return { op: "zoom", f: 1.25 };
  if (key === "-" || key === "_") return { op: "zoom", f: 0.8 };
  if (key === "0") return { op: "fit" };
  if (key === "Escape") return { op: "clear" };
  if (key === "n" || key === "N") return { op: "now" };
  if (key === "s" || key === "S") return { op: "start" };
  if (key === "ArrowLeft" || key === "ArrowRight") {
    const d = key === "ArrowLeft" ? -1 : 1;
    if (shift) return { op: "pan", dx: -d * PAN_STEP, dy: 0 };
    return { op: "walk", step: d };
  }
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
  return el && typeof el.closest === "function" ? el.closest(FOCUSABLE) : null;
}

function isControl(el) {
  return !!(el && typeof el.closest === "function" && el.closest(CONTROL));
}

// A pan must not start a text selection: this clears any selection the press left behind.
function clearSelection() {
  try {
    const sel = globalThis.getSelection ? globalThis.getSelection() : null;
    if (sel && typeof sel.removeAllRanges === "function") sel.removeAllRanges();
  } catch (err) {
    // No selection API here (node): nothing to clear.
  }
}

function centreOf(el) {
  return { x: Number(el.getAttribute("data-cx")), y: Number(el.getAttribute("data-cy")) };
}

function haloCentre(h) {
  return { x: Number(h.getAttribute("x")) + Number(h.getAttribute("width")) / 2,
    y: Number(h.getAttribute("y")) + Number(h.getAttribute("height")) / 2 };
}

// Binds the gestures and keys to one SVG. opts: { view, box: {w, h}, taps, fit, onTap(el), onClear(), onView(view),
// raf, cancel, clock, reduce }. raf, cancel and clock default to the browser; reduce overrides reducedMotion() (the
// tests use it). Returns the controls: zoom(f), fit(), actual(), view(), size(), centerOn(target, instant),
// walk(step, from), subscribe(fn) (fn runs now and on every change; returns an unsubscribe), stop() (ends a glide),
// destroy() (ends a glide and makes every later change silent: the SVG was replaced). Nothing here runs in node.
export function mountViewport(svg, vpG, opts) {
  const clock = opts.clock || function () {
    return Date.now();
  };
  const frame = opts.raf || function (fn) {
    return globalThis.requestAnimationFrame(fn);
  };
  const cancel = opts.cancel || function (id) {
    if (typeof globalThis.cancelAnimationFrame === "function") globalThis.cancelAnimationFrame(id);
  };
  let alive = true;
  let frameId = null;
  let active = null;
  const held = new Set();
  const motionOff = function () {
    return opts.reduce !== undefined ? !!opts.reduce : reducedMotion();
  };
  const size = function () {
    const r = svg.getBoundingClientRect();
    return { w: r.width || opts.box.w, h: r.height || opts.box.h };
  };
  const local = function (e) {
    const r = svg.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const gest = createGestures(opts.view, opts.taps || { last: null });
  const subs = [];
  let downEl = null;
  let glide = 0;
  const paint = function () {
    if (!alive || svg.isConnected === false) return;
    const v = gest.view;
    const at = "translate(" + v.x.toFixed(1) + " " + v.y.toFixed(1) + ") scale(" + v.k.toFixed(3) + ")";
    vpG.setAttribute("transform", at);
    if (opts.onView) opts.onView(v);
    subs.forEach(function (fn) {
      fn(v);
    });
  };
  const stop = function () {
    glide += 1;
    if (frameId !== null) cancel(frameId);
    frameId = null;
  };
  const destroy = function () {
    alive = false;
    subs.length = 0;
    stop();
  };
  const nodes = function () {
    return Array.from(svg.querySelectorAll(FOCUSABLE));
  };
  const anchorOf = function (target) {
    if (target && typeof target === "object") return target;
    if (target === "now") {
      const h = svg.querySelector(".wfg-halo");
      return h ? haloCentre(h) : null;
    }
    const el = nodes().find(function (n) {
      return n.getAttribute("data-wf-item") === target;
    });
    return el ? centreOf(el) : null;
  };
  // Eases the view to `to` over GLIDE_MS. A newer glide or any gesture cancels it. Instant under reduced motion.
  const glideTo = function (to, instant) {
    stop();
    const token = glide;
    const from = gest.view;
    if (instant || motionOff()) {
      gest.setView(to);
      paint();
      return;
    }
    const t0 = clock();
    const step = function () {
      frameId = null;
      if (token !== glide) return;
      const p = Math.min(1, (clock() - t0) / GLIDE_MS);
      gest.setView(tween(from, to, ease(p)));
      paint();
      if (p < 1) frameId = frame(step);
    };
    frameId = frame(step);
  };
  const centerOn = function (target, instant) {
    const pt = anchorOf(target);
    if (!pt) return false;
    glideTo(centreView(gest.view.k, size(), pt), instant);
    return true;
  };
  // Focuses a node and brings it on screen (a glide, only when it is outside the screen).
  const reveal = function (el) {
    el.focus({ preventScroll: true });
    const c = centreOf(el);
    const s = size();
    const v = gest.view;
    const x = v.k * c.x + v.x;
    const y = v.k * c.y + v.y;
    if (x < 0 || y < 0 || x > s.w || y > s.h) glideTo(centreView(v.k, s, c));
  };
  // Path order: the nodes are appended in path order, so the DOM order of [data-wf-item] is the path.
  const walk = function (step, from) {
    const list = nodes();
    if (!list.length) return null;
    const at = from ? list.indexOf(from) : -1;
    const i = at >= 0 ? at + step : (step > 0 ? 0 : list.length - 1);
    if (i < 0 || i >= list.length) return null;
    reveal(list[i]);
    return list[i];
  };
  const zoom = function (f) {
    stop();
    const s = size();
    gest.zoomBy(f, s.w / 2, s.h / 2);
    paint();
  };
  const fit = function () {
    stop();
    gest.setView(fitView(opts.box, size()));
    paint();
  };
  svg.addEventListener("pointerdown", function (e) {
    if (e.button > 0) return;
    held.add(e.pointerId);
    stop();
    if (!isControl(e.target)) {
      // No native selection on a pan; focus moves by hand, so the keyboard still lands on the map.
      e.preventDefault();
      clearSelection();
      try {
        (closestNode(e.target) || svg).focus({ preventScroll: true });
      } catch (err) {
        // Not focusable (a synthetic target): the pan still runs.
      }
    }
    const p = local(e);
    downEl = e.target;
    try {
      svg.setPointerCapture(e.pointerId);
    } catch (err) {
      // A pointer that is not active (a synthetic event) cannot be captured; the gesture still runs.
    }
    gest.down(e.pointerId, p.x, p.y);
  });
  // Belt and braces for browsers that start the selection on mousedown, and for keyboard select-all inside the map.
  svg.addEventListener("mousedown", function (e) {
    if (e.button === 0 && !isControl(e.target)) e.preventDefault();
  });
  svg.addEventListener("selectstart", function (e) {
    e.preventDefault();
  });
  // Only a held pointer moves the view: a hover costs nothing (no layout read, no paint).
  svg.addEventListener("pointermove", function (e) {
    if (!held.has(e.pointerId)) return;
    const p = local(e);
    gest.move(e.pointerId, p.x, p.y);
    paint();
  });
  const release = function (e) {
    held.delete(e.pointerId);
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
    held.delete(e.pointerId);
    gest.up(e.pointerId, 0, 0, e.timeStamp);
    paint();
  });
  svg.addEventListener("focusin", function (e) {
    const n = closestNode(e.target);
    if (n) active = n;
  });
  svg.addEventListener("wheel", function (e) {
    e.preventDefault();
    stop();
    const p = local(e);
    if (e.ctrlKey || e.metaKey) gest.wheel(e.deltaY, p.x, p.y);
    else {
      const v = gest.view;
      gest.setView({ k: v.k, x: v.x - (e.deltaX || 0), y: v.y - (e.deltaY || 0) });
    }
    paint();
  }, { passive: false });
  svg.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const plan = keyPlan(e.key, e.shiftKey);
    if (!plan) return;
    e.preventDefault();
    stop();
    if (plan.op === "zoom") zoom(plan.f);
    else if (plan.op === "fit") fit();
    else if (plan.op === "clear") opts.onClear();
    else if (plan.op === "now") centerOn("now");
    else if (plan.op === "start") centerOn("start");
    else if (plan.op === "walk") walk(plan.step, closestNode(e.target) || active);
    else if (plan.op === "pan") {
      const v = gest.view;
      gest.setView({ k: v.k, x: v.x + plan.dx, y: v.y + plan.dy });
      paint();
    } else moveFocus(closestNode(e.target) || active, plan.dir);
  });
  function moveFocus(cur, dir) {
    if (!cur) return;
    const items = nodes().map(function (el) {
      const c = centreOf(el);
      return { key: el.getAttribute("data-wf-item") || el.getAttribute("data-wf-fold"), cx: c.x, cy: c.y, el: el };
    });
    const from = items.find(function (n) {
      return n.el === cur;
    });
    const next = from ? nearest(items, from, dir) : null;
    if (next) reveal(next.el);
  }
  if (opts.fit) gest.setView(openView(opts.box, size()));
  paint();
  return {
    zoom: zoom,
    fit: fit,
    actual: function () {
      stop();
      const s = size();
      gest.setView(zoomAt(gest.view, 1, s.w / 2, s.h / 2));
      paint();
    },
    view: function () {
      return gest.view;
    },
    size: size,
    centerOn: centerOn,
    walk: walk,
    stop: stop,
    destroy: destroy,
    subscribe: function (fn) {
      subs.push(fn);
      fn(gest.view);
      return function () {
        const i = subs.indexOf(fn);
        if (i >= 0) subs.splice(i, 1);
      };
    },
  };
}
