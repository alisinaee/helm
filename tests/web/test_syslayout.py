"""The System views layout (R10.33), run in node over web/js/graph/syslayout.js.

layeredLayout: on generated views (a fixed-seed 30-node view in 5 groups, a small chain, edge cases) no two nodes
overlap, every node sits inside its band box and the drawing, bands do not overlap, every edge starts on a side of its
source and ends on a side of its target, every placed label covers no node and no other label, the output is the same
for a second run, unknown ends / self loops / duplicates are dropped, an unknown group gets its own band, callers sit
above callees inside a band, a tall drawing flows into columns on a wide canvas, and 30 nodes lay out in under 50 ms.
sequenceLayout: one row per step in order, self calls loop. matrixLayout: one cell per edge at its row and column.
"""

import json
import os
import random
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(os.path.dirname(TESTS), "web")
NODE = shutil.which("node")

SCRIPT = r"""
(async () => {
  const { readFileSync } = await import("node:fs");
  const { join } = await import("node:path");
  const { pathToFileURL } = await import("node:url");
  const m = await import(pathToFileURL(join(process.argv[1], "js", "graph", "syslayout.js")).href);
  const input = JSON.parse(readFileSync(0, "utf8"));
  const out = { cases: {} };
  for (const [name, view] of Object.entries(input.cases)) {
    const opts = { aspect: view.aspect || 1 };
    const lay = m.layeredLayout(view, opts);
    let ms = Infinity;
    for (let i = 0; i < 5; i++) {
      const t = process.hrtime.bigint();
      m.layeredLayout(view, opts);
      ms = Math.min(ms, Number(process.hrtime.bigint() - t) / 1e6);
    }
    out.cases[name] = { lay, again: m.layeredLayout(view, opts), ms };
  }
  out.seq = m.sequenceLayout(input.flow);
  out.mx = m.matrixLayout(input.matrix);
  out.consts = { NODE_W: m.NODE_W, NODE_H: m.NODE_H, LABEL_H: 16 };
  console.log(JSON.stringify(out));
})();
"""


def big_view(seed=7, n=30, groups=5):
    rnd = random.Random(seed)
    gs = [{"id": "g%d" % i, "label": "Group %d" % i} for i in range(groups)]
    nodes = [{"id": "n%d" % i, "label": "Node %d" % i, "group": "g%d" % (i % groups)} for i in range(n)]
    edges = []
    for _ in range(n * 2):
        a, b = rnd.sample(range(n), 2)
        edges.append({"from": "n%d" % a, "to": "n%d" % b, "label": "uses n%d" % b, "kind": "call",
                      "count": rnd.randint(1, 9), "derived": rnd.random() < 0.5})
    return {"groups": gs, "nodes": nodes, "edges": edges}


CASES = {
    "big": big_view(),
    "chain": {"groups": [{"id": "a", "label": "A"}],
              "nodes": [{"id": x, "label": x, "group": "a"} for x in ("top", "mid", "low")],
              "edges": [{"from": "top", "to": "mid", "label": "calls", "kind": "call"},
                        {"from": "mid", "to": "low", "label": "calls", "kind": "call"}]},
    "edge": {"groups": [{"id": "a", "label": "A"}],
             "nodes": [{"id": "x", "label": "x", "group": "a"}, {"id": "y", "label": "y", "group": "zz"}],
             "edges": [{"from": "x", "to": "y", "label": "ok", "kind": "call"},
                       {"from": "x", "to": "y", "label": "dup", "kind": "call"},
                       {"from": "x", "to": "x", "label": "self", "kind": "call"},
                       {"from": "x", "to": "ghost", "label": "unknown", "kind": "call"}]},
    "tall": dict({"groups": [{"id": "g%d" % i, "label": "G%d" % i} for i in range(6)],
                  "nodes": [{"id": "n%d" % i, "label": "n%d" % i, "group": "g%d" % i} for i in range(6)],
                  "edges": []}, aspect=3),
}
FLOW = {"participants": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "steps": [{"from": "a", "to": "b", "label": "go"}, {"from": "b", "to": "b", "label": "self"},
                  {"from": "b", "to": "a", "label": "back", "reply": True}, {"from": "a", "to": "ghost", "label": "x"}]}
MATRIX = {"nodes": [{"id": "c1", "label": "C1"}, {"id": "c2", "label": "C2"}, {"id": "s1", "label": "s1"},
                    {"id": "s2", "label": "s2"}],
          "edges": [{"from": "c1", "to": "s1", "label": "reads, writes"}, {"from": "c2", "to": "s2", "label": "reads"}]}


def overlap(a, b):
    return (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and
            a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


def start_end(d):
    nums = [float(x) for x in d.replace("M", " ").replace("C", " ").split()]
    return (nums[0], nums[1]), (nums[-2], nums[-1])


def on_side(pt, n, slack=3):
    x, y = pt
    inside_x = n["x"] - slack <= x <= n["x"] + n["w"] + slack
    return inside_x and (abs(y - n["y"]) <= slack or abs(y - (n["y"] + n["h"])) <= slack)


@unittest.skipIf(NODE is None, "node is not installed")
class SysLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.dumps({"cases": CASES, "flow": FLOW, "matrix": MATRIX})
        proc = subprocess.run([NODE, "-e", SCRIPT, WEB], input=payload, capture_output=True, text=True,
                              check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        cls.out = json.loads(proc.stdout)

    def lay(self, name):
        return self.out["cases"][name]["lay"]

    def test_no_overlap_and_inside_bands(self):
        for name in CASES:
            lay = self.lay(name)
            nodes = lay["nodes"]
            for i, a in enumerate(nodes):
                for b in nodes[i + 1:]:
                    self.assertFalse(overlap(a, b), (name, a["id"], b["id"]))
                box = lay["groups"][a["band"]]
                self.assertTrue(box["x"] <= a["x"] and a["x"] + a["w"] <= box["x"] + box["w"], (name, a["id"]))
                self.assertTrue(box["y"] <= a["y"] and a["y"] + a["h"] <= box["y"] + box["h"], (name, a["id"]))
                self.assertLessEqual(a["x"] + a["w"], lay["width"])
                self.assertLessEqual(a["y"] + a["h"], lay["height"])
            for i, a in enumerate(lay["groups"]):
                for b in lay["groups"][i + 1:]:
                    self.assertFalse(overlap(a, b), (name, a["id"], b["id"]))

    def test_edges_run_from_side_to_side(self):
        for name in CASES:
            lay = self.lay(name)
            nodes = {n["id"]: n for n in lay["nodes"]}
            for e in lay["edges"]:
                s, t = start_end(e["d"])
                self.assertTrue(on_side(s, nodes[e["from"]]), (name, e))
                self.assertTrue(on_side(t, nodes[e["to"]]), (name, e))

    def test_labels_cover_no_node_and_no_label(self):
        lay = self.lay("big")
        boxes = [{"x": e["lx"] - e["lw"] / 2, "y": e["ly"] - 8, "w": e["lw"], "h": 16}
                 for e in lay["edges"] if e["lx"] is not None]
        self.assertGreater(len(boxes), 5)
        for i, a in enumerate(boxes):
            for n in lay["nodes"]:
                self.assertFalse(overlap(a, n), (a, n["id"]))
            for b in boxes[i + 1:]:
                self.assertFalse(overlap(a, b), (a, b))

    def test_deterministic_and_fast(self):
        for name in CASES:
            self.assertEqual(self.out["cases"][name]["lay"], self.out["cases"][name]["again"], name)
        self.assertLess(self.out["cases"]["big"]["ms"], 50)

    def test_bad_edges_dropped_and_unknown_group_banded(self):
        lay = self.lay("edge")
        self.assertEqual([(e["from"], e["to"], e["label"]) for e in lay["edges"]], [("x", "y", "ok")])
        self.assertEqual([g["id"] for g in lay["groups"]], ["a", "zz"])

    def test_callers_above_callees_inside_a_band(self):
        nodes = {n["id"]: n for n in self.lay("chain")["nodes"]}
        self.assertLess(nodes["top"]["y"], nodes["mid"]["y"])
        self.assertLess(nodes["mid"]["y"], nodes["low"]["y"])

    def test_tall_drawing_flows_into_columns(self):
        lay = self.lay("tall")
        self.assertGreater(len({g["x"] for g in lay["groups"]}), 1)
        self.assertGreater(lay["width"], lay["groups"][0]["w"])

    def test_sequence_rows_and_self_call(self):
        seq = self.out["seq"]
        self.assertEqual([r["n"] for r in seq["rows"]], [1, 2, 3])
        self.assertTrue(seq["rows"][1]["self"])
        self.assertTrue(seq["rows"][2]["reply"])
        ys = [r["y"] for r in seq["rows"]]
        self.assertEqual(ys, sorted(ys))
        self.assertEqual(len(seq["heads"]), 2)

    def test_matrix_cells(self):
        mx = self.out["mx"]
        self.assertEqual([r["id"] for r in mx["rows"]], ["c1", "c2"])
        self.assertEqual([c["id"] for c in mx["cols"]], ["s1", "s2"])
        self.assertEqual([c["write"] for c in mx["cells"]], [True, False])


SCRIPT2 = r"""
(async () => {
  const { readFileSync } = await import("node:fs");
  const { join } = await import("node:path");
  const { pathToFileURL } = await import("node:url");
  const m = await import(pathToFileURL(join(process.argv[1], "js", "graph", "syslayout.js")).href);
  const input = JSON.parse(readFileSync(0, "utf8"));
  const small = input.small;
  const out = {};
  out.collapsed = m.collapseGroups(small, new Set(["A"]));
  out.container = m.collapseGroups(input.container, new Set(["api"]));
  out.sub = m.subgraph(small, "A");
  const before = m.layeredLayout(small, { aspect: 1 });
  const after = m.layeredLayout(small, { aspect: 1, collapsed: new Set(["A"]) });
  out.before = before;
  out.after = after;
  out.shift = m.anchorShift(before, after, "B");
  out.shiftA = m.anchorShift(before, after, "A");
  out.shiftNone = m.anchorShift(before, after, "nope");
  const big = input.big;
  const col = new Set(["g0", "g2"]);
  out.big = m.layeredLayout(big, { aspect: 1, collapsed: col });
  let ms = Infinity;
  for (let i = 0; i < 5; i++) {
    const t = process.hrtime.bigint();
    m.layeredLayout(big, { aspect: 1, collapsed: col });
    ms = Math.min(ms, Number(process.hrtime.bigint() - t) / 1e6);
  }
  out.ms = ms;
  out.inputKept = JSON.stringify(small) === JSON.stringify(input.small);
  console.log(JSON.stringify(out));
})();
"""

SMALL = {"groups": [{"id": "A", "label": "Alpha"}, {"id": "B", "label": "Beta"}],
         "nodes": [{"id": "a1", "label": "a1", "group": "A"}, {"id": "a2", "label": "a2", "group": "A"},
                   {"id": "b1", "label": "b1", "group": "B"}, {"id": "b2", "label": "b2", "group": "B"}],
         "edges": [{"from": "a1", "to": "a2", "label": "inner"}, {"from": "a1", "to": "b1", "label": "x"},
                   {"from": "a2", "to": "b1", "label": "y", "count": 3}, {"from": "a2", "to": "b2", "label": "x"},
                   {"from": "b1", "to": "b2", "label": "z"}]}
CONTAINER = {"groups": [{"id": "g", "label": "G"}],
             "nodes": [{"id": "api", "label": "API", "group": "g"},
                       {"id": "r1", "label": "r1", "group": "g", "parent": "api"},
                       {"id": "r2", "label": "r2", "group": "g", "parent": "api"},
                       {"id": "db", "label": "db", "group": "g"}],
             "edges": [{"from": "r1", "to": "db", "label": "q"}, {"from": "r2", "to": "db", "label": "q"},
                       {"from": "r1", "to": "r2", "label": "inner"}]}


@unittest.skipIf(NODE is None, "node is not installed")
class SysLayoutCollapseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.dumps({"small": SMALL, "container": CONTAINER, "big": big_view(n=60, groups=6)})
        proc = subprocess.run([NODE, "-e", SCRIPT2, WEB], input=payload, capture_output=True, text=True,
                              check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        cls.out = json.loads(proc.stdout)

    def test_collapse_merges_edges_with_counts(self):
        c = self.out["collapsed"]
        self.assertEqual([n["id"] for n in c["nodes"]], ["g:A", "b1", "b2"])
        g = c["nodes"][0]
        self.assertEqual((g["kind"], g["label"], g["sub"], g["members"], g["collapsed"]),
                         ("group", "Alpha", "2 parts", ["a1", "a2"], True))
        self.assertEqual([x["id"] for x in c["groups"]], ["B"])
        es = {(e["from"], e["to"]): e for e in c["edges"]}
        self.assertEqual(set(es), {("g:A", "b1"), ("g:A", "b2"), ("b1", "b2")})
        self.assertEqual((es[("g:A", "b1")]["count"], es[("g:A", "b1")]["label"]), (4, "2 links"))
        self.assertEqual(es[("g:A", "b2")]["label"], "x")
        self.assertFalse(any(e["from"] == e["to"] for e in c["edges"]))
        self.assertTrue(self.out["inputKept"])

    def test_collapse_container_hides_children(self):
        c = self.out["container"]
        self.assertEqual([n["id"] for n in c["nodes"]], ["api", "db"])
        self.assertEqual(c["nodes"][0]["members"], ["r1", "r2"])
        self.assertEqual([(e["from"], e["to"], e["count"], e["label"]) for e in c["edges"]],
                         [("api", "db", 2, "q")])

    def test_toggles_exist(self):
        for lay in (self.out["before"], self.out["after"]):
            for g in lay["groups"]:
                self.assertFalse(g["collapsed"])
                self.assertEqual(g["toggle"]["size"], 20)
                self.assertEqual((g["toggle"]["x"] > g["x"], g["toggle"]["y"] >= g["y"]), (True, True))
                self.assertLessEqual(g["toggle"]["y"] + 20, g["y"] + g["h"])
        node = [n for n in self.out["after"]["nodes"] if n["id"] == "g:A"][0]
        self.assertTrue(node["collapsed"])
        self.assertEqual(node["toggle"]["size"], 20)
        self.assertIsNone(self.out["before"]["nodes"][0].get("toggle"))

    def test_subgraph_boundary_nodes(self):
        s = self.out["sub"]
        kinds = {n["id"]: n.get("kind") for n in s["nodes"]}
        self.assertEqual(set(kinds), {"a1", "a2", "b1", "b2"})
        self.assertEqual((kinds["b1"], kinds["b2"], kinds["a1"]), ("external", "external", None))
        self.assertEqual([n["sub"] for n in s["nodes"] if n["id"] == "b1"], ["outside"])
        self.assertEqual([g["id"] for g in s["groups"]], ["A"])
        self.assertEqual(len(s["edges"]), 4)
        self.assertFalse(any(e["from"] == "b1" and e["to"] == "b2" for e in s["edges"]))

    def test_anchor_shift(self):
        b = {n["id"]: n for n in self.out["before"]["groups"]}["B"]
        a = {n["id"]: n for n in self.out["after"]["groups"]}["B"]
        self.assertEqual(self.out["shift"], {"dx": a["x"] - b["x"], "dy": a["y"] - b["y"]})
        self.assertNotEqual(self.out["shift"]["dy"], 0)
        self.assertIn("dx", self.out["shiftA"])
        self.assertEqual(self.out["shiftNone"], {"dx": 0, "dy": 0})

    def test_no_overlap_after_collapse_and_fast(self):
        lay = self.out["big"]
        ids = {n["id"] for n in lay["nodes"]}
        self.assertTrue({"g:g0", "g:g2"} <= ids)
        for i, a in enumerate(lay["nodes"]):
            for b in lay["nodes"][i + 1:]:
                self.assertFalse(overlap(a, b), (a["id"], b["id"]))
        for i, a in enumerate(lay["groups"]):
            for b in lay["groups"][i + 1:]:
                self.assertFalse(overlap(a, b))
        self.assertLess(self.out["ms"], 50)



SPACE_SCRIPT = r"""
(async () => {
  const { join } = await import("node:path");
  const { pathToFileURL } = await import("node:url");
  const m = await import(pathToFileURL(join(process.argv[1], "js", "graph", "syslayout.js")).href);
  const view = { groups: [{ id: "a", label: "A" }], nodes: [{ id: "x", group: "a" }, { id: "y", group: "a" }],
    edges: [] };
  const one = m.layeredLayout(view, { space: 1 });
  const two = m.layeredLayout(view, { space: 2 });
  const gap = (l) => l.nodes[1].x - l.nodes[0].x - l.nodes[0].w;
  const v2 = { groups: [{ id: "a" }, { id: "b" }], nodes: [{ id: "x", group: "a" }, { id: "y", group: "b" },
    { id: "z", group: "b" }], edges: [{ from: "x", to: "y", label: "p" }, { from: "x", to: "z", label: "q" }] };
  const rk = (l) => l.groups[1].y - l.groups[0].y - l.groups[0].h;
  const r1 = m.layeredLayout(v2, { space: 1, aspect: 0.2 });
  const r2 = m.layeredLayout(v2, { space: 2, aspect: 0.2 });
  console.log(JSON.stringify({ rk1: rk(r1), rk2: rk(r2), lab: r2.edges.every((e) => e.lx !== null), g1: gap(one), g2: gap(two), w1: one.nodes[0].w, w2: two.nodes[0].w,
    clamp: [m.clampSpace(9), m.clampSpace(0.1), m.clampSpace("x")] }));
})();
"""


@unittest.skipUnless(NODE, "node not installed")
class SpaceFactor(unittest.TestCase):
    def test_factor_two_widens_gap_not_boxes(self):
        out = subprocess.run([NODE, "-e", SPACE_SCRIPT, WEB], capture_output=True, text=True, check=True).stdout
        r = json.loads(out)
        self.assertEqual(r["g2"], 2 * r["g1"])
        self.assertEqual(r["rk2"], 2 * r["rk1"])
        self.assertTrue(r["lab"])
        self.assertEqual(r["w1"], r["w2"])
        self.assertEqual(r["clamp"], [2.5, 0.6, 1])


BUNDLE_SCRIPT = r"""
(async () => {
  const { join } = await import("node:path");
  const { pathToFileURL } = await import("node:url");
  const m = await import(pathToFileURL(join(process.argv[1], "js", "graph", "syslayout.js")).href);
  const nodes = [{ id: "s", group: "a" }].concat([1, 2, 3, 4].map((i) => ({ id: "t" + i, group: "b" })));
  const edges = [1, 2, 3, 4].map((i) => ({ from: "s", to: "t" + i, label: "uses " + i }));
  const l = m.layeredLayout({ groups: [{ id: "a" }, { id: "b" }], nodes: nodes, edges: edges }, { space: 2 });
  console.log(JSON.stringify({ n: l.edges.length, label: l.edges[0].label, b: (l.edges[0].bundle || []).length }));
})();
"""


@unittest.skipUnless(NODE, "node not installed")
class Bundling(unittest.TestCase):
    def test_parallel_edges_collapse_to_one_with_count(self):
        out = subprocess.run([NODE, "-e", BUNDLE_SCRIPT, WEB], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), {"n": 1, "label": "\u00d74", "b": 4})


if __name__ == "__main__":
    unittest.main()
