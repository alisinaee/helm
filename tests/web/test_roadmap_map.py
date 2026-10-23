"""Roadmap Map (R11.5, docs/ROADMAP-MAP.md): the layout (metro stations, card columns, folds, filters, Now, dependency
arrows), the Map tab and page markup, and the source rules (viewport reuse, CSP-safe SVG, keyboard and menu paths).

The node checks run web/js/graph/roadmap_layout.js and web/js/views/roadmap.js in node and are skipped when node is
not installed. The source checks always run.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(REPO, "web")

SCRIPT = """
import { pathToFileURL } from "node:url";
const web = process.argv[2];
const load = (n) => import(pathToFileURL(web + "/js/" + n).href);
const L = await load("graph/roadmap_layout.js");
const state = await load("state.js");
const roadmap = await load("views/roadmap.js");
const phases = [
  { id: "A", name: "Alpha", state: "done", done: 2, total: 2 },
  { id: "B", name: "Beta", state: "partial", done: 1, total: 4 },
  { id: "C", name: "Gamma", state: "todo", done: 0, total: 2 },
];
const tasks = [
  { id: "A.1", phase: "A", title: "a1", state: "done", model: "haiku" },
  { id: "A.2", phase: "A", title: "a2", state: "done", model: "haiku" },
  { id: "B.1", phase: "B", title: "b1", state: "done", model: "sonnet" },
  { id: "B.2", phase: "B", title: "b2", state: "partial", model: "opus", tokensK: 40 },
  { id: "B.3", phase: "B", title: "b3", state: "todo", model: "haiku" },
  { id: "B.4", phase: "B", title: "b4", state: "hold", model: "haiku" },
  { id: "C.1", phase: "C", title: "c1", state: "todo", model: "sonnet" },
  { id: "C.2", phase: "C", title: "c2", state: "todo", model: "haiku" },
];
const snap = { phases, tasks };
const base = { deps: [["B.3", "C.1"], ["B.2", "B.3"], ["A.1", "C.2"]], running: { "C.2": true }, blocked: ["C.1"] };
const run = (extra) => L.roadmapLayout(snap, Object.assign({}, base, extra || {}));
const out = {
  base: run(),
  baseText: JSON.stringify(run()),
  againText: JSON.stringify(run()),
  open: run({ status: "open" }),
  done: run({ status: "done" }),
  hold: run({ status: "hold" }),
  model: run({ model: "haiku" }),
  showDone: run({ showDone: { B: true } }),
  unfold: run({ open: { A: true, C: false } }),
  noRun: L.roadmapLayout(snap, { deps: [] }),
  empty: L.roadmapLayout({ phases: [], tasks: [] }, {}),
  spaced: run({ spacing: 2 }),
  spacedDef: run({ spacing: 1 }),
};
const raw = { project: { id: "x", title: "x" }, summary: {}, overall: { project: { done: 3, total: 8 } },
  phases: phases, tasks: tasks, jobs: [], blocked: [] };
const s = state.createStore();
s.projects = [{ id: "x", name: "x", progress: 0, tasks_left: 5, running: 0, need_user: 0, errors_count: 0,
stale: false }];
s.snapshots.x = state.normalizeSnapshot(raw, 0);
function html(view) {
  const vm = state.buildViewModel(s, { name: "project", id: "x", section: "roadmap", view: view, item: null,
    filters: {} }, { mode: null, open: {} }, 0);
  vm.snapshotList = [s.snapshots.x];
  vm.control = null;
  return roadmap.sectionView(vm);
}
out.lanes = html(null);
out.map = html("map");
console.log(JSON.stringify(out));
"""


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RoadmapMapLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "m.mjs")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SCRIPT)
            out = subprocess.run(["node", path, WEB], capture_output=True, text=True, check=True).stdout
        cls.out = json.loads(out)

    def ids(self, lay):
        return [c["id"] for c in lay["cards"]]

    def test_one_station_per_phase_in_plan_order_on_one_line(self):
        lay = self.out["base"]
        self.assertEqual([c["id"] for c in lay["cols"]], ["A", "B", "C"])
        xs = [c["x"] for c in lay["cols"]]
        self.assertEqual(xs, sorted(xs))
        self.assertEqual({c["cy"] for c in lay["cols"]}, {lay["line"]["y"]})
        self.assertEqual(lay["line"]["x1"], lay["cols"][0]["cx"])
        self.assertEqual(lay["line"]["x2"], lay["cols"][-1]["cx"])

    def test_done_phase_starts_folded_and_unfolds_in_place(self):
        cols = {c["id"]: c for c in self.out["base"]["cols"]}
        self.assertFalse(cols["A"]["open"])
        self.assertLess(cols["A"]["w"], cols["B"]["w"])
        self.assertNotIn("A.1", self.ids(self.out["base"]))
        unfold = {c["id"]: c for c in self.out["unfold"]["cols"]}
        self.assertTrue(unfold["A"]["open"])
        self.assertFalse(unfold["C"]["open"])
        self.assertNotIn("C.1", self.ids(self.out["unfold"]))

    def test_done_tasks_fold_into_a_stub_that_opens(self):
        base = self.out["base"]
        self.assertNotIn("B.1", self.ids(base))
        stub = [s for s in base["stubs"] if s["phase"] == "B"][0]
        self.assertEqual(stub["count"], 1)
        self.assertFalse(stub["open"])
        self.assertIn("B.1", self.ids(self.out["showDone"]))
        self.assertTrue([s for s in self.out["showDone"]["stubs"] if s["phase"] == "B"][0]["open"])

    def test_cards_stack_without_overlap_in_their_column(self):
        cards = [c for c in self.out["base"]["cards"] if c["phase"] == "B"]
        for a, b in zip(cards, cards[1:]):
            self.assertGreaterEqual(b["y"], a["y"] + a["h"])
        col = [c for c in self.out["base"]["cols"] if c["id"] == "B"][0]
        for c in cards:
            self.assertGreaterEqual(c["x"], col["x"])
            self.assertLessEqual(c["x"] + c["w"], col["x"] + col["w"])

    def test_status_comes_from_state_jobs_and_blockers(self):
        st = {c["id"]: c["status"] for c in self.out["base"]["cards"]}
        self.assertEqual(st["B.2"], "doing")
        self.assertEqual(st["B.3"], "todo")
        self.assertEqual(st["B.4"], "hold")
        self.assertEqual(st["C.1"], "blocked")
        self.assertEqual(st["C.2"], "doing")
        run = {c["id"]: c["running"] for c in self.out["base"]["cards"]}
        self.assertTrue(run["C.2"])
        self.assertFalse(run["B.2"])

    def test_filters_by_status_and_model(self):
        self.assertEqual(self.ids(self.out["open"]), ["B.2", "B.3", "B.4", "C.1", "C.2"])
        self.assertEqual(self.out["open"]["stubs"], [])
        self.assertEqual(self.ids(self.out["done"]), ["B.1"])
        self.assertEqual(self.ids(self.out["hold"]), ["B.4"])
        self.assertEqual(self.ids(self.out["model"]), ["B.3", "B.4", "C.2"])

    def test_now_is_the_phase_with_a_running_job_else_the_first_open_phase(self):
        self.assertEqual(self.out["base"]["now"]["phase"], "C")
        self.assertEqual(self.out["noRun"]["now"]["phase"], "B")
        self.assertEqual([c["id"] for c in self.out["base"]["cols"] if c["now"]], ["C"])

    def test_dependency_arrows_only_between_shown_cards(self):
        edges = {(e["from"], e["to"]) for e in self.out["base"]["edges"]}
        self.assertEqual(edges, {("task:B.3", "task:C.1"), ("task:B.2", "task:B.3")})
        for e in self.out["base"]["edges"]:
            self.assertTrue(e["d"].startswith("M"))

    def test_progress_and_size(self):
        cols = {c["id"]: c for c in self.out["base"]["cols"]}
        self.assertEqual(cols["B"]["pct"], 25)
        self.assertEqual(cols["B"]["doing"], 1)
        lay = self.out["base"]
        self.assertGreaterEqual(lay["width"], cols["C"]["x"] + cols["C"]["w"])
        self.assertGreaterEqual(lay["height"], max(c["y"] + c["h"] for c in lay["cards"]))

    def test_spacing_two_widens_the_gaps_and_keeps_the_card_size(self):
        a, b = self.out["base"], self.out["spaced"]
        self.assertEqual(self.out["spacedDef"], a)
        self.assertGreater(b["cards"][1]["y"] - b["cards"][0]["y"], a["cards"][1]["y"] - a["cards"][0]["y"])
        self.assertEqual(b["cards"][0]["w"], a["cards"][0]["w"])
        self.assertEqual(b["cards"][0]["h"], a["cards"][0]["h"])
        self.assertGreater(b["cols"][1]["x"] - b["cols"][0]["x"], a["cols"][1]["x"] - a["cols"][0]["x"])

    def test_pure_and_empty_safe(self):
        self.assertEqual(self.out["baseText"], self.out["againText"])
        self.assertEqual(self.out["empty"]["cols"], [])
        self.assertIsNone(self.out["empty"]["line"])
        self.assertIsNone(self.out["empty"]["now"])

    def test_map_tab_next_to_lanes_and_timeline(self):
        lanes = self.out["lanes"]
        self.assertIn('href="#/p/x/roadmap/map"', lanes)
        self.assertIn(">Lanes</a>", lanes)
        self.assertIn(">Timeline</a>", lanes)
        page = self.out["map"]
        self.assertIn('href="#/p/x/roadmap/map" aria-current="page">Map</a>', page)
        self.assertIn("data-rmm-host", page)
        self.assertIn('data-rmm-rev="', page)
        self.assertIn('id="rmm-legend"', page)
        for op in ("in", "out", "fit", "now", "full"):
            self.assertIn('data-rmm-op="' + op + '"', page)
        for s in ("all", "open", "doing", "blocked", "hold", "done"):
            self.assertIn('data-rmm-status="' + s + '"', page)
        self.assertIn('aria-label="Filter by model"', page)
        self.assertNotIn('class="lanes"', page)


class RoadmapMapSourceTests(unittest.TestCase):
    def setUp(self):
        self.js = read("web", "js", "views", "roadmap_map.js")
        self.css = read("web", "css", "roadmap_map.css")

    def test_reuses_the_graph_viewport(self):
        self.assertIn('import { mountViewport, flowCentre } from "../graph/viewport.js";', self.js)
        self.assertIn('from "../graph/roadmap_layout.js"', self.js)
        self.assertIn('from "../graph/layout.js"', self.js)
        self.assertIn('"rb.space.roadmap"', self.js)

    def test_svg_is_csp_safe(self):
        self.assertIn("createElementNS", self.js)
        self.assertNotIn('"style"', self.js)
        self.assertNotIn("setAttribute(\"style", self.js)
        self.assertNotIn("innerHTML", self.js)

    def test_keyboard_menu_and_details_paths(self):
        for needle in ('"contextmenu"', '"ContextMenu"', 'e.key === "F10" && e.shiftKey', 'role", "menu"',
                       'role="menuitem"', '"ArrowDown"', '"Escape"', 'e.key === "Enter"', 'item: id',
                       '"Open in Work"', '"Copy ref"', '"Ask head"', 'data-action="copy-ref"'):
            self.assertIn(needle, self.js, needle)

    def test_fills_the_space_without_page_scroll(self):
        self.assertIn(".rmm-page{display:flex;flex-direction:column", self.css)
        self.assertIn("height:100%;min-height:0", self.css)
        self.assertIn(".rmm-stage{position:relative;flex:1", self.css)
        self.assertIn(".rmm-page.is-full{position:fixed;inset:0", self.css)

    def test_actions_overlay_the_map_box_top_right(self):
        self.assertIn("'<div class=\"rmm-stage\">' + overlayHtml() +", self.js)
        self.assertIn('class="rmm-ov"', self.js)
        self.assertIn(".rmm-ov{position:absolute;z-index:4;top:var(--sp-2);right:var(--sp-2)", self.css)
        self.assertIn(".rmm-ov .btn{height:var(--h-small)", self.css)
        self.assertIn("line-height:var(--h-small)", self.css)
        self.assertIn("gap:var(--sp-2)", self.css)
        self.assertIn(".rmm-host{flex:1;min-width:0;min-height:0;display:flex;box-sizing:border-box;", self.css)

    def test_reduced_motion_and_tokens_only(self):
        self.assertIn("@media (prefers-reduced-motion:reduce)", self.css)
        self.assertNotRegex(self.css, r"#[0-9a-fA-F]{3,8}\b")

    def test_css_loads_on_demand(self):
        self.assertIn('"/css/roadmap_map.css"', self.js)


if __name__ == "__main__":
    unittest.main()
