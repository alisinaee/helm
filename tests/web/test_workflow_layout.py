"""The workflow flow layout (R7.14 B), run in node by an inline script on the model of graph/model.js.

Checks: frames sit left to right in phase order; no two boxes overlap and every node sits in its frame; tasks snake in
rows of up to four (odd rows run right to left); every edge, sequence edges included, has a right-angled path; a
parallel group stacks in one column; the Now flag sits over the current node; the 350-task snapshot stays at 300 nodes
or fewer; 100 tasks lay out in under 50 ms; the output is byte-identical on a second run; layout() keeps its old fields.
The node checks are skipped when node is not installed.
"""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
FIXTURES = os.path.join(TESTS, "fixtures", "graph")
NODE = shutil.which("node")
SCRIPT = r"""
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
import { join } from "node:path";
const web = process.argv[1];
const load = (name) => import(pathToFileURL(join(web, "js", "graph", name)).href);
const { buildGraph } = await load("model.js");
const { flowLayout, layout } = await load("layout.js");
const cases = JSON.parse(readFileSync(0, "utf8"));
const out = {};
for (const c of cases) {
  const graph = buildGraph(c.snap, {});
  const flow = flowLayout(graph, c.opts || {});
  const again = flowLayout(buildGraph(c.snap, {}), c.opts || {});
  let ms = null;
  if (c.perf) {
    ms = Infinity;
    for (let i = 0; i < 5; i += 1) {
      const t0 = performance.now();
      flowLayout(graph, c.opts || {});
      ms = Math.min(ms, performance.now() - t0);
    }
  }
  const legacy = c.legacy ? Object.keys(layout(graph, "dependency", "week", Number(c.snap.now) || 0)) : null;
  out[c.name] = { graph, flow, text: JSON.stringify(flow), againText: JSON.stringify(again), ms, legacy };
}
process.stdout.write(JSON.stringify(out));
"""


def task(tid, phase, state="todo", title=None):
    return {"id": tid, "title": title or tid, "phase": phase, "state": state, "model": "haiku", "tokensK": 1,
            "at": {}}


def snapshot(phases, tasks, now=1000):
    return {"now": now, "project": {"title": "Demo"}, "phases": [{"id": p, "title": p, "approved": True}
                                                              for p in phases],
            "tasks": tasks, "jobs": [], "queue": [], "issues": [],
            "workflow": {"spans": [], "edges": {"after": [], "block": []}}}


def run(cases):
    proc = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, WEB], input=json.dumps(cases),
                          capture_output=True, text=True, check=False, timeout=120)
    if proc.returncode != 0:
        raise AssertionError("flow layout failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def inside(box, frame):
    return (box["x"] >= frame["x"] and box["y"] >= frame["y"] and
            box["x"] + box["w"] <= frame["x"] + frame["w"] and box["y"] + box["h"] <= frame["y"] + frame["h"])


def overlaps(a, b):
    return (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and
            a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


def lane_of(graph):
    return {n["id"]: (n["lane"] if n["lane"] is not None else "_") for n in graph["nodes"]}


@unittest.skipUnless(NODE, "node is not installed")
class WorkflowFlowLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def load(name):
            with open(os.path.join(FIXTURES, name + ".json"), encoding="utf8") as fh:
                return json.load(fh)

        snake = snapshot(["P1"], [task("P1.%d" % k, "P1") for k in range(1, 11)])
        group = snapshot(["P1", "P2"], [task("P1.1", "P1", "doing"), task("P1.2", "P1"), task("P1.3", "P1", "doing"),
                                       task("P2.1", "P2")])
        big = snapshot(["P%d" % p for p in range(1, 6)],
                       [task("P%d.%d" % (p, k), "P%d" % p) for p in range(1, 6) for k in range(1, 71)])
        wide = snapshot(["P1"], [task("P1.%d" % k, "P1") for k in range(1, 101)])
        folded = snapshot(["P%d" % p for p in range(1, 5)], [task("P%d.%d" % (p, k), "P%d" % p)
                                                            for p in range(1, 5) for k in range(1, 3)])
        cases = [
            {"name": "snake", "snap": snake, "opts": {"expandAll": True}},
            {"name": "group", "snap": group, "opts": {"expandAll": True}},
            {"name": "big", "snap": big},
            {"name": "big_expand", "snap": big, "opts": {"expandAll": True}},
            {"name": "wide", "snap": wide, "perf": True, "opts": {"expandAll": True}},
            {"name": "fixture_350", "snap": load("350-tasks"), "legacy": True},
            {"name": "fixture_350_open", "snap": load("350-tasks"), "opts": {"expandAll": True}},
            {"name": "chain", "snap": load("chain"), "opts": {"expandAll": True}},
            {"name": "fan_in", "snap": load("fan-in"), "opts": {"expandAll": True}},
            {"name": "blockers", "snap": load("with-blockers"), "opts": {"expandAll": True}},
            {"name": "cycle", "snap": load("cycle"), "opts": {"expandAll": True}},
            {"name": "empty", "snap": load("empty")},
            {"name": "folded", "snap": folded, "opts": {"collapseAll": True}},
        ]
        cls.out = run(cases)
        cls.again = run(cases)

    def flow(self, name):
        return self.out[name]["flow"]

    def test_frames_left_to_right_in_phase_order(self):
        for name in ("big_expand", "chain", "fan_in", "blockers"):
            with self.subTest(case=name):
                frames = self.flow(name)["frames"]
                self.assertEqual([f["lane"] for f in frames], [p["id"] for p in
                                                             self.out[name]["graph"]["lanes"]])
                xs = [f["x"] for f in frames]
                self.assertEqual(sorted(xs), xs)
                for a, b in zip(frames, frames[1:]):
                    self.assertGreaterEqual(b["x"], a["x"] + a["w"])

    def test_no_overlaps_and_nodes_inside_their_frame(self):
        for name, case in self.out.items():
            flow = case["flow"]
            boxes = list(flow["boxes"].items())
            with self.subTest(case=name):
                for i, (id_a, a) in enumerate(boxes):
                    for id_b, b in boxes[i + 1:]:
                        self.assertFalse(overlaps(a, b), "%s and %s overlap" % (id_a, id_b))
                frames = {f["lane"]: f for f in flow["frames"]}
                lanes = lane_of(case["graph"])
                for node_id, box in boxes:
                    if node_id in ("start", "end") or node_id.startswith("phase:"):
                        continue
                    lane = lanes.get(node_id)
                    if lane in frames and not frames[lane]["collapsed"]:
                        self.assertTrue(inside(box, frames[lane]), "%s outside its frame" % node_id)

    def test_tasks_snake_in_rows_of_four(self):
        boxes = self.flow("snake")["boxes"]
        xs = [boxes["task:P1.%d" % k]["x"] for k in range(1, 11)]
        ys = [boxes["task:P1.%d" % k]["y"] for k in range(1, 11)]
        self.assertEqual(xs[:4], sorted(xs[:4]))
        self.assertEqual(xs[4:8], sorted(xs[4:8], reverse=True))
        self.assertEqual(xs[8:], sorted(xs[8:]))
        self.assertEqual(len(set(ys[:4])), 1)
        self.assertEqual(len(set(ys[4:8])), 1)
        self.assertEqual(xs[3], xs[4])
        self.assertEqual(xs[7], xs[8])
        self.assertEqual(xs[0], xs[7])

    def test_every_edge_has_a_path(self):
        for name, case in self.out.items():
            graph = case["graph"]
            routes = case["flow"]["routes"]
            with self.subTest(case=name):
                collapsed = set(case["flow"]["collapsed"])
                for edge in list(graph["edges"]) + list(graph["sequence"]):
                    if lane_of(graph).get(edge["from"]) == lane_of(graph).get(edge["to"]) in collapsed:
                        self.assertNotIn(edge["id"], routes)
                        continue
                    self.assertIn(edge["id"], routes)
                    points = routes[edge["id"]]
                    self.assertGreaterEqual(len(points), 2)
                    for px, py in points:
                        self.assertIsInstance(px, int)
                        self.assertIsInstance(py, int)
                    for (ax, ay), (bx, by) in zip(points, points[1:]):
                        self.assertTrue(ax == bx or ay == by, "%s is not right-angled" % edge["id"])

    def test_folded_frames_chain_one_arrow_left_to_right(self):
        flow = self.flow("folded")
        graph = self.out["folded"]["graph"]
        self.assertEqual(4, len(flow["collapsed"]))
        lanes = lane_of(graph)
        frames = {f["lane"]: f for f in flow["frames"]}
        routes = flow["routes"]
        drawn = 0
        for edge in graph["sequence"]:
            src = lanes.get(edge["from"])
            dst = lanes.get(edge["to"])
            if src is not None and src == dst:
                self.assertNotIn(edge["id"], routes, "an edge inside one folded frame is drawn")
                continue
            points = routes[edge["id"]]
            drawn += 1
            start = frames[src] if src is not None else flow["boxes"]["start"]
            end = frames[dst] if dst is not None else flow["boxes"]["end"]
            self.assertEqual([start["x"] + start["w"], start["y"] + start["h"] // 2], points[0], edge["id"])
            self.assertEqual([end["x"], end["y"] + end["h"] // 2], points[-1], edge["id"])
            self.assertLess(points[0][0], points[-1][0], "%s runs backwards" % edge["id"])
            for (ax, ay), (bx, by) in zip(points, points[1:]):
                self.assertGreaterEqual(bx, ax, "%s loops back" % edge["id"])
        self.assertEqual(5, drawn)

    def test_parallel_group_stacks_in_one_column(self):
        flow = self.flow("group")
        self.assertEqual(1, len(flow["parallel"]))
        members = flow["parallel"][0]["members"]
        self.assertEqual(["task:P1.1", "task:P1.3"], members)
        self.assertEqual(flow["boxes"]["task:P1.1"]["x"], flow["boxes"]["task:P1.3"]["x"])
        self.assertLess(flow["boxes"]["task:P1.1"]["y"], flow["boxes"]["task:P1.3"]["y"])

    def test_now_flag_sits_over_the_current_node(self):
        flow = self.flow("chain")
        now = flow["now"]
        self.assertEqual(now["node"], self.out["chain"]["graph"]["current"])
        self.assertEqual(now["box"], flow["boxes"][now["node"]])
        self.assertEqual(now["flag"]["x"], now["box"]["x"])
        self.assertLess(now["flag"]["y"] + now["flag"]["h"], min(f["y"] for f in flow["frames"]))

    def test_350_tasks_stay_within_300_nodes(self):
        default = self.flow("fixture_350")
        self.assertLessEqual(default["count"], 300)
        self.assertFalse(default["capped"])
        big = self.flow("big")
        self.assertLessEqual(big["count"], 300)
        self.assertFalse(big["capped"])
        self.assertIn("P5", big["collapsed"])
        self.assertGreaterEqual(self.flow("fixture_350_open")["count"], default["count"])

    def test_100_tasks_lay_out_under_50_ms(self):
        self.assertLess(self.out["wide"]["ms"], 50)

    def test_byte_identical_on_a_second_run(self):
        for name, case in self.out.items():
            with self.subTest(case=name):
                self.assertEqual(case["text"], case["againText"])
                self.assertEqual(case["text"], self.again[name]["text"])

    def test_layout_keeps_its_old_fields(self):
        keys = self.out["fixture_350"]["legacy"]
        for key in ("pos", "paths", "lanes", "width", "height", "cycles", "ticks", "nowX", "flow"):
            self.assertIn(key, keys)

    def test_empty_graph_has_only_start_and_end(self):
        flow = self.flow("empty")
        self.assertEqual([], flow["frames"])
        self.assertEqual({"start", "end"}, set(flow["boxes"]))
        self.assertEqual({}, flow["routes"])


if __name__ == "__main__":
    unittest.main()
