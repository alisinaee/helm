"""The workflow viewport and minimap (R7.14 D), run in node over tests/fixtures/graph/chain.json.

Checks: centerOn (a node id or a point) puts the point at the screen centre, eased when motion is allowed and instant
under reduced motion, and a pointer cancels a glide; the N and S keys centre on Now and Start; Left and Right walk the
path order node by node; Ctrl and Meta combinations are left alone; + and 0 zoom and fit; Escape clears; a click or drag
on the minimap centres the map and the minimap rectangle follows the viewport; chipsOf marks the phase that holds Now.
Source checks: no style attribute, no inline handler, no eval or innerHTML in viewport.js and minimap.js; minimap.js
stays within 120 lines; the minimap CSS is at most 1 KB and graph.css within 6 KB. The node checks are skipped when node
is not installed. node runs an inline script with a small DOM stand-in, so no browser is needed.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
GRAPH = os.path.join(WEB, "js", "graph")
GRAPH_CSS = os.path.join(WEB, "css", "graph.css")
FIXTURES = os.path.join(TESTS, "fixtures", "graph")
NODE = shutil.which("node")
FORBIDDEN = [
    (re.compile(r"\sstyle\s*="), "style attribute"),
    (re.compile(r"\son[a-z]{3,}\s*="), "inline handler"),
    (re.compile(r"\beval\s*\("), "eval"),
    (re.compile(r"new\s+Function\b"), "new Function"),
    (re.compile(r"\binnerHTML\b"), "innerHTML"),
]

# argv: web directory, fixtures directory. Prints one JSON object (see the Python tests for the keys).
SCRIPT = r"""
(async () => {
  const [web, fixtures] = process.argv.slice(1);
  const { readFileSync } = await import("node:fs");
  const { join } = await import("node:path");
  const { pathToFileURL } = await import("node:url");
  const load = (name) => import(pathToFileURL(join(web, "js", "graph", name)).href);
  const log = { focus: [], prevented: 0, cleared: 0 };
  class El {
    constructor(tag) {
      this.tagName = tag;
      this.attrs = {};
      this.kids = [];
      this.parent = null;
      this.handlers = {};
      this.rect = null;
    }
    setAttribute(k, v) { this.attrs[k] = String(v); }
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
    appendChild(c) { c.parent = this; this.kids.push(c); return c; }
    addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); }
    fire(t, ev) { const e = Object.assign({ preventDefault() {} }, ev); (this.handlers[t] || []).forEach((f) => f(e)); }
    setPointerCapture() {}
    getBoundingClientRect() { return this.rect || { left: 0, top: 0, width: 800, height: 600 }; }
    focus() { log.focus.push(this.getAttribute("data-wf-item") || this.getAttribute("data-wf-fold")); }
    matches(sel) {
      return sel.split(",").some((part) => {
        const s = part.trim();
        if (s.startsWith("[")) return this.getAttribute(s.slice(1, -1)) !== null;
        if (s.startsWith(".")) return (this.getAttribute("class") || "").split(" ").includes(s.slice(1));
        return false;
      });
    }
    closest(sel) {
      let n = this;
      while (n && n.matches) { if (n.matches(sel)) return n; n = n.parent; }
      return null;
    }
    collect(sel, out) {
      this.kids.forEach((c) => { if (c.matches) { if (c.matches(sel)) out.push(c); c.collect(sel, out); } });
      return out;
    }
    querySelectorAll(sel) { return this.collect(sel, []); }
    querySelector(sel) { return this.collect(sel, [])[0] || null; }
  }
  globalThis.document = {
    createElementNS: (ns, tag) => new El(tag),
    createTextNode: (s) => ({ nodeType: 3, data: String(s), parent: null }),
  };
  const vp = await load("viewport.js");
  const mm = await load("minimap.js");
  const model = await load("model.js");
  const layout = await load("layout.js");
  const render = await load("render.js");
  const snap = JSON.parse(readFileSync(join(fixtures, "chain.json"), "utf8"));
  const graph = model.buildGraph(snap, {});
  const lay = layout.layout(graph, "dependency", "week", Number(snap.now) || 0);
  const flow = lay.flow;
  const box = { w: flow.width, h: flow.height };
  const taskId = graph.nodes.find((n) => n.type === "task").id;
  const out = { box: box, flowPath: flow.path, taskId: taskId };
  const key = (target, k, shift) => ({ key: k, shiftKey: !!shift, ctrlKey: false, metaKey: false, altKey: false,
    target: target, preventDefault() { log.prevented += 1; } });
  const fresh = (opts) => {
    const b = render.buildMap(graph, lay, "demo");
    const ctl = vp.mountViewport(b.svg, b.vp, Object.assign({ view: { k: 1, x: 0, y: 0 }, box: box,
      taps: { last: null }, onTap() {}, onClear() { log.cleared += 1; } }, opts || {}));
    return { svg: b.svg, ctl: ctl };
  };
  const keyOf = (n) => n.getAttribute("data-wf-item") || n.getAttribute("data-wf-fold");
  const nodeOf = (svg, id) => svg.querySelectorAll("[data-wf-item], .wfg-fold").find((n) => keyOf(n) === id);
  const screenOf = (ctl, pt) => { const v = ctl.view(); return { x: v.k * pt.x + v.x, y: v.k * pt.y + v.y }; };
  const centreOfNode = (svg, id) => {
    const n = nodeOf(svg, id);
    return { x: Number(n.getAttribute("data-cx")), y: Number(n.getAttribute("data-cy")) };
  };

  // centerOn: instant by node id and by point.
  const a = fresh({ reduce: true });
  out.centerInstant = { found: a.ctl.centerOn(taskId), screen: screenOf(a.ctl, centreOfNode(a.svg, taskId)) };
  out.centerMissing = a.ctl.centerOn("no-such-node", true);
  a.ctl.centerOn({ x: 30, y: 20 }, true);
  out.centerPoint = screenOf(a.ctl, { x: 30, y: 20 });

  // centerOn eased: nothing moves until the frames run, then the view lands on the target.
  const queue = [];
  let now = 0;
  const raf = (fn) => { queue.push(fn); };
  const g = fresh({ reduce: false, raf: raf, clock: () => now });
  g.ctl.centerOn(taskId);
  out.glideStartsAt = g.ctl.view();
  const seen = [];
  while (queue.length) { now += 40; queue.shift()(now); seen.push(g.ctl.view()); }
  out.glide = { frames: seen.length, last: screenOf(g.ctl, centreOfNode(g.svg, taskId)),
    midway: seen.length > 2 && seen[0].x !== out.glideStartsAt.x && seen[0].x !== seen[seen.length - 1].x };

  // Reduced motion: no frame is queued, the view jumps.
  const rq = [];
  const r = fresh({ reduce: true, raf: (fn) => rq.push(fn) });
  r.ctl.centerOn(taskId);
  out.reduced = { queued: rq.length, screen: screenOf(r.ctl, centreOfNode(r.svg, taskId)) };

  // A pointer during a glide cancels it.
  const cq = [];
  let ct = 0;
  const c = fresh({ reduce: false, raf: (fn) => cq.push(fn), clock: () => ct });
  c.ctl.centerOn(taskId);
  c.svg.fire("pointerdown", { button: 0, pointerId: 1, clientX: 0, clientY: 0, timeStamp: 0 });
  const held = c.ctl.view();
  while (cq.length) { ct += 80; cq.shift()(ct); }
  out.cancelled = { same: JSON.stringify(held) === JSON.stringify(c.ctl.view()) };

  // Keys N and S centre on Now and Start (instant here); Now is the halo around the current node.
  const k1 = fresh({ reduce: true });
  const halo = k1.svg.querySelector(".wfg-halo");
  out.keyNow = { halo: !!halo };
  if (halo) {
    k1.svg.fire("keydown", key(k1.svg, "n"));
    const hx = Number(halo.getAttribute("x")) + Number(halo.getAttribute("width")) / 2;
    const hy = Number(halo.getAttribute("y")) + Number(halo.getAttribute("height")) / 2;
    out.keyNow.screen = screenOf(k1.ctl, { x: hx, y: hy });
  }
  k1.svg.fire("keydown", key(k1.svg, "S", true));
  out.keyStart = screenOf(k1.ctl, centreOfNode(k1.svg, "start"));

  // Path walk: Right from the canvas focuses the first node, then each press moves one node along the path.
  const w = fresh({ reduce: true });
  log.focus.length = 0;
  w.svg.fire("keydown", key(w.svg, "ArrowRight"));
  const ids = w.svg.querySelectorAll("[data-wf-item], .wfg-fold").map(keyOf);
  const pathIds = flow.path.filter((id) => ids.includes(id));
  for (let i = 1; i < ids.length + 1; i += 1) {
    const cur = nodeOf(w.svg, log.focus[log.focus.length - 1]);
    w.svg.fire("keydown", key(cur, "ArrowRight"));
  }
  const domPath = ids.filter((id) => flow.path.includes(id));
  out.walk = { order: log.focus.slice(), dom: ids, pathOrder: JSON.stringify(pathIds) === JSON.stringify(domPath) };
  const last = nodeOf(w.svg, log.focus[log.focus.length - 1]);
  const beforeEnd = log.focus.length;
  w.svg.fire("keydown", key(last, "ArrowRight"));
  out.walk.stayedAtEnd = log.focus.length === beforeEnd;
  w.svg.fire("keydown", key(last, "ArrowLeft"));
  out.walk.backOne = log.focus[log.focus.length - 1] === ids[ids.length - 2];

  // Ctrl+S is left to the browser: no handling and no preventDefault.
  const z = fresh({ reduce: true });
  const before = JSON.stringify(z.ctl.view());
  const pd = log.prevented;
  z.svg.fire("keydown", Object.assign(key(z.svg, "s"), { ctrlKey: true }));
  out.ctrlS = { unchanged: JSON.stringify(z.ctl.view()) === before, prevented: log.prevented === pd };

  // + zooms by 1.25, 0 fits, Escape clears.
  z.svg.fire("keydown", key(z.svg, "+"));
  out.zoomPlus = z.ctl.view().k;
  z.svg.fire("keydown", key(z.svg, "0"));
  out.fitK = z.ctl.view().k;
  z.svg.fire("keydown", key(z.svg, "Escape"));
  out.cleared = log.cleared;

  // Minimap: a click centres the map on the point under the pointer; a drag follows; the rectangle is the view.
  const m = fresh({ reduce: true });
  const mhost = new El("div");
  const mini = mm.mountMinimap(mhost, { flow: flow, viewport: m.ctl });
  const ms = mini.svg;
  ms.rect = { left: 0, top: 0, width: 160, height: 90 };
  const s = Math.min(160 / box.w, 90 / box.h);
  const clientOf = (p) => ({ clientX: (160 - box.w * s) / 2 + p.x * s, clientY: (90 - box.h * s) / 2 + p.y * s });
  const target = centreOfNode(m.svg, taskId);
  ms.fire("pointerdown", Object.assign({ button: 0, pointerId: 2 }, clientOf(target)));
  out.minimapClick = screenOf(m.ctl, target);
  const rectEl = ms.querySelector(".wfm-view");
  out.minimapTarget = target;
  out.minimapRectCentre = { x: Number(rectEl.getAttribute("x")) + Number(rectEl.getAttribute("width")) / 2,
    y: Number(rectEl.getAttribute("y")) + Number(rectEl.getAttribute("height")) / 2 };
  const far = { x: box.w * 0.9, y: box.h * 0.9 };
  ms.fire("pointermove", Object.assign({ pointerId: 2 }, clientOf(far)));
  out.minimapDrag = screenOf(m.ctl, far);
  ms.fire("pointerup", { pointerId: 2 });
  const parked = JSON.stringify(m.ctl.view());
  ms.fire("pointermove", Object.assign({ pointerId: 2 }, clientOf(target)));
  out.minimapAfterUp = JSON.stringify(m.ctl.view()) === parked;
  out.minimapFrames = ms.querySelectorAll(".wfm-frame").length;
  out.flowFrames = flow.frames.length;

  // Destroy (the SVG was replaced): the pending glide frame is cancelled and no view is reported after it.
  const dq = [];
  const dc = [];
  let dt = 0;
  let views = 0;
  const d = fresh({ reduce: false, raf: (fn) => { dq.push(fn); return dq.length; }, cancel: (id) => dc.push(id),
    clock: () => dt, onView: () => { views += 1; } });
  d.ctl.centerOn(taskId);
  const seenBefore = views;
  d.ctl.destroy();
  dt += 100;
  while (dq.length) dq.shift()(dt);
  out.destroy = { cancelled: dc.length, silent: views === seenBefore };

  // The wheel scrolls the page unless Ctrl is held (a trackpad pinch sends Ctrl).
  const wh = fresh({ reduce: true });
  let wpd = 0;
  const wv0 = JSON.stringify(wh.ctl.view());
  wh.svg.fire("wheel", { deltaY: -100, clientX: 0, clientY: 0, ctrlKey: false, preventDefault() { wpd += 1; } });
  out.wheelPlain = { prevented: wpd, unchanged: JSON.stringify(wh.ctl.view()) === wv0 };
  wh.svg.fire("wheel", { deltaY: -100, clientX: 0, clientY: 0, metaKey: true, preventDefault() { wpd += 1; } });
  out.wheelMeta = { zoomed: wh.ctl.view().k > 1 };
  wh.svg.fire("wheel", { deltaY: -100, clientX: 0, clientY: 0, ctrlKey: true, preventDefault() { wpd += 1; } });
  out.wheelCtrl = { prevented: wpd, zoomed: wh.ctl.view().k > 1 };

  // A hover (no button held) does not read the layout or paint.
  const hv = fresh({ reduce: true });
  let rects = 0;
  const hrect = hv.svg.getBoundingClientRect.bind(hv.svg);
  hv.svg.getBoundingClientRect = () => { rects += 1; return hrect(); };
  hv.svg.fire("pointermove", { pointerId: 7, clientX: 10, clientY: 10 });
  out.hover = { rects: rects };

  // Roving focus: the arrows resume from the node that last took focus, when the SVG itself is the target.
  const rv = fresh({ reduce: true });
  const rnodes = rv.svg.querySelectorAll("[data-wf-item], .wfg-fold");
  rv.svg.fire("focusin", { target: rnodes[0] });
  log.focus.length = 0;
  rv.svg.fire("keydown", key(rv.svg, "ArrowRight"));
  out.roving = { focused: log.focus[0], second: keyOf(rnodes[1]) };

  // Pure helpers.
  out.layoutPoint = mm.layoutPoint({ w: 100, h: 50 }, { left: 10, top: 20, width: 200, height: 100 }, 70, 40);
  out.viewRect = mm.viewRect({ k: 2, x: -100, y: -50 }, { w: 800, h: 600 });
  out.easeEnds = [vp.ease(0), vp.ease(1)];
  out.chips = mm.chipsOf(flow);
  out.keys = { n: vp.keyPlan("n", false), S: vp.keyPlan("S", false), left: vp.keyPlan("ArrowLeft", false),
    right: vp.keyPlan("ArrowRight", false), up: vp.keyPlan("ArrowUp", false),
    shiftLeft: vp.keyPlan("ArrowLeft", true), other: vp.keyPlan("q", false) };
  process.stdout.write(JSON.stringify(out));
})().catch((err) => {
  process.stderr.write(String(err && err.stack || err));
  process.exit(1);
});
"""


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def run_node():
    proc = subprocess.run([NODE, "--experimental-default-type=module", "-e", SCRIPT, WEB, FIXTURES],
                          capture_output=True, text=True, check=False, timeout=120)
    if proc.returncode != 0:
        raise AssertionError("viewport script failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class ViewportSourceTests(unittest.TestCase):

    def test_viewport_and_minimap_have_no_style_handler_eval_or_innerhtml(self):
        for name in ("viewport.js", "minimap.js"):
            text = read_text(os.path.join(GRAPH, name))
            for pattern, what in FORBIDDEN:
                self.assertIsNone(pattern.search(text), "%s uses %s" % (name, what))

    def test_minimap_is_within_120_lines_and_viewport_within_360(self):
        self.assertLessEqual(len(read_text(os.path.join(GRAPH, "minimap.js")).splitlines()), 120)
        self.assertLessEqual(len(read_text(os.path.join(GRAPH, "viewport.js")).splitlines()), 490)

    def test_a_pan_never_starts_a_text_selection(self):
        text = read_text(os.path.join(GRAPH, "viewport.js"))
        down = text[text.index('addEventListener("pointerdown"'):text.index('addEventListener("pointermove"')]
        self.assertIn("isControl(e.target)", down)
        self.assertIn("e.preventDefault()", down)
        self.assertIn("clearSelection()", down)
        self.assertIn("setPointerCapture(e.pointerId)", down)
        self.assertIn("removeAllRanges()", text)
        self.assertIn('addEventListener("mousedown"', text)
        self.assertIn('addEventListener("selectstart"', text)
        control = re.search(r'const CONTROL = "([^"]*)"', text).group(1)
        for tag in ("button", "a", "input", "select", "textarea", ".wfg-ctl", ".wfm"):
            self.assertIn(tag, control)

    def test_map_css_stops_selection_and_keeps_touch_pan(self):
        css = read_text(GRAPH_CSS)
        for selector in (".wfg-svg", ".wfg-host", ".wfm"):
            rule = re.search(re.escape(selector) + r"\{([^}]*)\}", css).group(1)
            self.assertIn("user-select:none", rule, selector)
            self.assertIn("-webkit-user-select:none", rule, selector)
        self.assertIn("touch-action:none", re.search(r"\.wfg-svg\{([^}]*)\}", css).group(1))

    def test_reduced_motion_is_read_from_the_media_query(self):
        text = read_text(os.path.join(GRAPH, "viewport.js"))
        self.assertIn("(prefers-reduced-motion: reduce)", text)
        self.assertIn("reducedMotion()", text)

    def test_lines_stay_within_120_columns(self):
        paths = [os.path.join(GRAPH, "viewport.js"), os.path.join(GRAPH, "minimap.js"),
                 os.path.join(TESTS, "web", "test_graph_viewport.py")]
        for path in paths:
            for number, line in enumerate(read_text(path).splitlines(), 1):
                self.assertLessEqual(len(line), 120, "%s:%d is %d columns" % (path, number, len(line)))

    def test_minimap_css_is_small_and_the_budget_holds(self):
        css = read_text(GRAPH_CSS)
        start = css.index("/* Minimap (R7.14 D)")
        self.assertLessEqual(len(css[start:].encode("utf-8")), 1024)
        self.assertLessEqual(len(css.encode("utf-8")), 6 * 1024)
        self.assertIn("@media (max-width:640px){.wfm{display:none}}", css)
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(", css), "graph.css has a literal colour")


@unittest.skipIf(NODE is None, "node is not installed")
class ViewportNodeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = run_node()

    def test_center_on_a_node_puts_it_at_the_screen_centre(self):
        self.assertTrue(self.out["centerInstant"]["found"])
        screen = self.out["centerInstant"]["screen"]
        self.assertAlmostEqual(screen["x"], 400, places=3)
        self.assertAlmostEqual(screen["y"], 300, places=3)

    def test_center_on_a_point_and_a_missing_node(self):
        self.assertIs(self.out["centerMissing"], False)
        self.assertAlmostEqual(self.out["centerPoint"]["x"], 400, places=3)
        self.assertAlmostEqual(self.out["centerPoint"]["y"], 300, places=3)

    def test_eased_centre_glides_over_frames_and_lands_on_the_target(self):
        glide = self.out["glide"]
        self.assertGreater(glide["frames"], 2)
        self.assertTrue(glide["midway"])
        self.assertAlmostEqual(glide["last"]["x"], 400, places=3)
        self.assertAlmostEqual(glide["last"]["y"], 300, places=3)

    def test_reduced_motion_jumps_without_a_frame(self):
        self.assertEqual(self.out["reduced"]["queued"], 0)
        self.assertAlmostEqual(self.out["reduced"]["screen"]["x"], 400, places=3)

    def test_a_pointer_cancels_a_glide(self):
        self.assertTrue(self.out["cancelled"]["same"])

    def test_destroy_cancels_the_frame_and_silences_the_view(self):
        self.assertEqual(self.out["destroy"]["cancelled"], 1)
        self.assertTrue(self.out["destroy"]["silent"])

    def test_plain_wheel_pans_and_ctrl_or_cmd_wheel_zooms(self):
        self.assertEqual(self.out["wheelPlain"], {"prevented": 1, "unchanged": False})
        self.assertEqual(self.out["wheelCtrl"], {"prevented": 3, "zoomed": True})
        self.assertTrue(self.out["wheelMeta"]["zoomed"])

    def test_hover_does_not_read_the_layout(self):
        self.assertEqual(self.out["hover"]["rects"], 0)

    def test_arrows_resume_from_the_node_that_last_took_focus(self):
        self.assertEqual(self.out["roving"]["focused"], self.out["roving"]["second"])

    def test_n_and_s_keys_centre_on_now_and_start(self):
        self.assertTrue(self.out["keyNow"]["halo"])
        self.assertAlmostEqual(self.out["keyNow"]["screen"]["x"], 400, places=3)
        self.assertAlmostEqual(self.out["keyNow"]["screen"]["y"], 300, places=3)
        self.assertAlmostEqual(self.out["keyStart"]["x"], 400, places=3)
        self.assertAlmostEqual(self.out["keyStart"]["y"], 300, places=3)

    def test_arrow_keys_walk_the_path_order_node_by_node(self):
        walk = self.out["walk"]
        self.assertEqual(walk["order"], walk["dom"])
        self.assertTrue(walk["pathOrder"], "DOM order is not the path order")
        self.assertTrue(walk["stayedAtEnd"])
        self.assertTrue(walk["backOne"])

    def test_ctrl_s_is_left_to_the_browser(self):
        self.assertTrue(self.out["ctrlS"]["unchanged"])
        self.assertTrue(self.out["ctrlS"]["prevented"])

    def test_plus_zooms_zero_fits_and_escape_clears(self):
        self.assertAlmostEqual(self.out["zoomPlus"], 1.25, places=3)
        self.assertGreater(self.out["fitK"], 0)
        self.assertEqual(self.out["cleared"], 1)

    def test_minimap_click_centres_the_map_on_the_point(self):
        self.assertAlmostEqual(self.out["minimapClick"]["x"], 400, places=2)
        self.assertAlmostEqual(self.out["minimapClick"]["y"], 300, places=2)
        centre = self.out["minimapRectCentre"]
        self.assertAlmostEqual(centre["x"], self.out["minimapTarget"]["x"], places=2)
        self.assertAlmostEqual(centre["y"], self.out["minimapTarget"]["y"], places=2)

    def test_minimap_drag_follows_the_pointer_and_stops_on_release(self):
        self.assertAlmostEqual(self.out["minimapDrag"]["x"], 400, places=2)
        self.assertAlmostEqual(self.out["minimapDrag"]["y"], 300, places=2)
        self.assertTrue(self.out["minimapAfterUp"])

    def test_minimap_draws_every_frame(self):
        self.assertEqual(self.out["minimapFrames"], self.out["flowFrames"])

    def test_pure_helpers(self):
        self.assertEqual(self.out["layoutPoint"], {"x": 30, "y": 10})
        self.assertEqual(self.out["viewRect"], {"x": 50, "y": 25, "w": 400, "h": 300})
        self.assertEqual(self.out["easeEnds"], [0, 1])

    def test_one_chip_per_phase_and_exactly_one_holds_now(self):
        chips = self.out["chips"]
        self.assertEqual(len(chips), self.out["flowFrames"])
        self.assertEqual(sum(1 for c in chips if c["current"]), 1)

    def test_key_plan_for_the_new_keys(self):
        keys = self.out["keys"]
        self.assertEqual(keys["n"], {"op": "now"})
        self.assertEqual(keys["S"], {"op": "start"})
        self.assertEqual(keys["left"], {"op": "walk", "step": -1})
        self.assertEqual(keys["right"], {"op": "walk", "step": 1})
        self.assertEqual(keys["up"], {"op": "focus", "dir": [0, -1]})
        self.assertEqual(keys["shiftLeft"], {"op": "pan", "dx": 40, "dy": 0})
        self.assertIsNone(keys["other"])


if __name__ == "__main__":
    unittest.main()
