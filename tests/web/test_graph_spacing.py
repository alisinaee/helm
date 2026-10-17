"""The Map spacing factor (R11.115): layout.js (workflow Map) and roadmap_layout.js (Roadmap map) scale the gaps
between nodes, columns, rows and the group padding, never a node box. Node checks run in node and are skipped when
node is not installed. Source checks always run: the spacing buttons, the [ and ] keys, the double-click reset and the
per-map localStorage keys are in both views, with aria labels and no style attribute.
"""

import json
import os
import re
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
const L = await load("graph/layout.js");
const R = await load("graph/roadmap_layout.js");
const graph = {
  lanes: [{ id: "P" }],
  nodes: [
    { id: "a", type: "task", lane: "P", state: "todo", time: 0 },
    { id: "b", type: "task", lane: "P", state: "todo", time: 0 },
    { id: "c", type: "task", lane: "P", state: "todo", time: 0 },
  ],
  edges: [{ id: "e1", from: "a", to: "b", type: "dependency" }, { id: "e2", from: "a", to: "c", type: "dependency" }],
  sequence: [],
};
const flow = (s) => L.flowLayout(graph, { spacing: s }).boxes;
const dep = (s) => L.layout(graph, "dependency", "today", 0, s).pos;
const phases = [
  { id: "A", name: "Alpha", state: "todo", done: 0, total: 2 },
  { id: "B", name: "Beta", state: "todo", done: 0, total: 2 },
];
const tasks = [
  { id: "A.1", phase: "A", title: "a1", state: "todo", model: "haiku" },
  { id: "A.2", phase: "A", title: "a2", state: "todo", model: "haiku" },
  { id: "B.1", phase: "B", title: "b1", state: "todo", model: "haiku" },
  { id: "B.2", phase: "B", title: "b2", state: "todo", model: "haiku" },
];
const snap = { phases, tasks };
const ro = (s) => R.roadmapLayout(snap, { deps: [], spacing: s });
const out = {
  flow1: flow(1), flow2: flow(2), flow25: flow(2.5), flowLow: flow(0.6), flowHigh: flow(9), flowDef: flow(undefined),
  dep1: dep(1), dep2: dep(2),
  road1: ro(1), road2: ro(2), roadDef: ro(undefined),
  roadText1: JSON.stringify(ro(1)), roadTextDef: JSON.stringify(ro(undefined)),
  spaceOf: [L.spacingOf(0.1), L.spacingOf(6), L.spacingOf("x"), L.stepSpacing(6, 1), L.stepSpacing(0.2, -1),
    L.stepSpacing(1, 1), L.stepSpacing(3, 1), L.stepSpacing(3.5, -1)],
};
console.log(JSON.stringify(out));
"""


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class SpacingLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.mjs")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SCRIPT)
            out = subprocess.run(["node", path, WEB], capture_output=True, text=True, check=True).stdout
        cls.out = json.loads(out)

    def test_flow_factor_two_widens_the_gap_and_keeps_node_widths(self):
        a1, b1 = self.out["flow1"]["a"], self.out["flow1"]["b"]
        a2, b2 = self.out["flow2"]["a"], self.out["flow2"]["b"]
        self.assertGreater(b2["x"] - a2["x"], b1["x"] - a1["x"])
        self.assertEqual(a2["w"], a1["w"])
        self.assertEqual(b2["w"], b1["w"])
        self.assertEqual(a2["h"], a1["h"])

    def test_flow_gap_between_neighbours_scales_with_the_factor(self):
        a1, b1 = self.out["flow1"]["a"], self.out["flow1"]["b"]
        a2, b2 = self.out["flow2"]["a"], self.out["flow2"]["b"]
        self.assertEqual((b1["x"] - a1["x"]) - a1["w"], 24)
        self.assertEqual((b2["x"] - a2["x"]) - a2["w"], 48)

    def test_flow_factor_is_clamped_and_one_is_the_default(self):
        self.assertEqual(self.out["flowDef"], self.out["flow1"])
        self.assertNotEqual(self.out["flowHigh"], self.out["flow25"])
        self.assertGreater(self.out["flowHigh"]["b"]["x"] - self.out["flowHigh"]["a"]["x"],
                           self.out["flow25"]["b"]["x"] - self.out["flow25"]["a"]["x"])
        low = self.out["flowLow"]["b"]["x"] - self.out["flowLow"]["a"]["x"]
        self.assertLess(low, self.out["flow1"]["b"]["x"] - self.out["flow1"]["a"]["x"])

    def test_dependency_column_pitch_grows_and_node_width_stays(self):
        p1, p2 = self.out["dep1"], self.out["dep2"]
        self.assertGreater(p2["b"]["x"] - p2["a"]["x"], p1["b"]["x"] - p1["a"]["x"])
        self.assertEqual(p2["a"]["w"], p1["a"]["w"])
        self.assertEqual(p2["a"]["h"], p1["a"]["h"])
        self.assertGreater(p2["c"]["y"] - p2["b"]["y"], p1["c"]["y"] - p1["b"]["y"])

    def test_roadmap_factor_two_widens_column_and_card_gaps_keeps_card_size(self):
        r1, r2 = self.out["road1"], self.out["road2"]
        c1 = {c["id"]: c for c in r1["cols"]}
        c2 = {c["id"]: c for c in r2["cols"]}
        self.assertGreater(c2["B"]["x"] - c2["A"]["x"], c1["B"]["x"] - c1["A"]["x"])
        self.assertEqual(c2["A"]["w"], c1["A"]["w"])
        k1 = [c for c in r1["cards"] if c["phase"] == "A"]
        k2 = [c for c in r2["cards"] if c["phase"] == "A"]
        self.assertGreater(k2[1]["y"] - k2[0]["y"], k1[1]["y"] - k1[0]["y"])
        self.assertEqual(k2[0]["w"], k1[0]["w"])
        self.assertEqual(k2[0]["h"], k1[0]["h"])

    def test_roadmap_default_is_unchanged(self):
        self.assertEqual(self.out["roadTextDef"], self.out["roadText1"])

    def test_spacing_helpers_clamp_and_step(self):
        low, high, bad, up_at_top, down_at_bottom, one_up, three_up, down_from_35 = self.out["spaceOf"]
        self.assertEqual(low, 0.2)
        self.assertEqual(high, 6)
        self.assertEqual(bad, 1)
        self.assertEqual(up_at_top, 6.5)
        self.assertEqual(down_at_bottom, 0.2)
        self.assertEqual(one_up, 1.2)
        self.assertEqual(three_up, 3.5)
        self.assertEqual(down_from_35, 3)


class SpacingSourceTests(unittest.TestCase):
    def test_both_views_carry_the_controls(self):
        wf = read("web", "js", "views", "workflow.js")
        rm = read("web", "js", "views", "roadmap_map.js")
        for js in (wf, rm):
            self.assertIn('aria-label="Less space"', js)
            self.assertIn('aria-label="More space"', js)
            self.assertIn('"Spacing"', js)
            self.assertIn('"]"', js)
            self.assertIn('"["', js)
            self.assertIn("dblclick", js)
            self.assertIn("readSpacing(SPACE_KEY)", js)
            self.assertIn("writeSpacing(SPACE_KEY", js)
        self.assertIn('"rb.space.workflow"', wf)
        self.assertIn('"rb.space.roadmap"', rm)

    def test_controls_have_no_style_attribute_and_no_inline_handler(self):
        for rel in (("web", "js", "views", "workflow.js"), ("web", "js", "views", "roadmap_map.js")):
            js = read(*rel)
            self.assertIsNone(re.search(r"\sstyle\s*=", js), rel)
            self.assertIsNone(re.search(r"\son[a-z]{3,}\s*=", js), rel)

    def test_storage_is_wrapped_in_try(self):
        js = read("web", "js", "graph", "layout.js")
        self.assertRegex(js, r"function readSpacing[\s\S]*?try \{")
        self.assertRegex(js, r"function writeSpacing[\s\S]*?try \{")


if __name__ == "__main__":
    unittest.main()
