"""The system map layout (R10.22, A4), run in node over web/js/graph/syslayout.js.

Checks on generated systems (a fixed-seed 24-card system, a small chain, and edge cases): no two cards overlap, every
card sits inside the width and height, cards keep layer order left to right, every route is orthogonal, starts on the
source card's right side and ends on the target card's left side, and no segment crosses the inside of any card. The
output is the same for a second run and for the input shuffled (order does not matter). Unknown ends, self loops and
duplicate edges are dropped with a warning, and an undeclared layer goes to "other" last. 24 cards lay out in under
50 ms (best of five runs). The node checks are skipped when node is not installed.
"""

import json
import os
import random
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
SYSLAYOUT = os.path.join(WEB, "js", "graph", "syslayout.js")
NODE = shutil.which("node")
CARD_W = 200
CARD_H = 56

# stdin: {"cases": {name: system}}. stdout: {name: {layout, text, again, shuffled, ms}} (ms is the best of five runs).
SCRIPT = r"""
(async () => {
  const { readFileSync } = await import("node:fs");
  const { join } = await import("node:path");
  const { pathToFileURL } = await import("node:url");
  const web = process.argv[1];
  const { systemLayout } = await import(pathToFileURL(join(web, "js", "graph", "syslayout.js")).href);
  const input = JSON.parse(readFileSync(0, "utf8"));
  const out = {};
  const reverse = (sys) => ({
    layers: sys.layers || [],
    components: (sys.components || []).slice().reverse(),
    edges: (sys.edges || []).slice().reverse(),
  });
  for (const name of Object.keys(input.cases)) {
    const sys = input.cases[name];
    const layout = systemLayout(sys);
    let best = Infinity;
    for (let k = 0; k < 5; k += 1) {
      const t0 = performance.now();
      systemLayout(sys);
      best = Math.min(best, performance.now() - t0);
    }
    out[name] = {
      layout,
      text: JSON.stringify(layout),
      again: JSON.stringify(systemLayout(sys)),
      shuffled: JSON.stringify(systemLayout(reverse(sys))),
      ms: best,
    };
  }
  process.stdout.write(JSON.stringify(out));
})();
"""


def generated_system(seed, n_cards, layers, n_edges):
    rnd = random.Random(seed)
    components = []
    for i in range(n_cards):
        components.append({
            "id": "c-%02d" % i,
            "name": "Component %d" % i,
            "layer": layers[i % len(layers)],
            "kind": "module",
        })
    edges = set()
    while len(edges) < n_edges:
        a = rnd.randrange(n_cards)
        b = rnd.randrange(n_cards)
        if a != b:
            edges.add((a, b))
    return {
        "version": 1,
        "layers": layers,
        "components": components,
        "edges": [{"from": "c-%02d" % a, "to": "c-%02d" % b, "label": "x", "kind": "call"}
                  for a, b in sorted(edges)],
    }


def chain_system():
    return {
        "version": 1,
        "layers": ["ui", "service", "data"],
        "components": [
            {"id": "web-ui", "name": "Web UI", "layer": "ui"},
            {"id": "api", "name": "API", "layer": "service"},
            {"id": "store", "name": "Store", "layer": "data"},
            {"id": "tool", "name": "Tool", "layer": "ui"},
        ],
        "edges": [
            {"from": "web-ui", "to": "api"},
            {"from": "api", "to": "store"},
            {"from": "web-ui", "to": "store"},
            {"from": "store", "to": "web-ui"},
            {"from": "tool", "to": "tool"},
            {"from": "api", "to": "missing"},
            {"from": "web-ui", "to": "api"},
        ],
    }


def other_system():
    return {
        "layers": ["ui"],
        "components": [
            {"id": "a", "layer": "ui"},
            {"id": "b", "layer": "mystery"},
            {"id": "c"},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }


CASES = {
    "grid24": generated_system(7, 24, ["ui", "service", "cli", "data", "external"], 40),
    "chain": chain_system(),
    "other": other_system(),
    "empty": {},
}


def run_node(cases):
    proc = subprocess.run([NODE, "--experimental-default-type=module", "-e", SCRIPT, WEB],
                          input=json.dumps({"cases": cases}), capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError("node failed: " + proc.stderr)
    return json.loads(proc.stdout)


def overlaps(a, b):
    return (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
            and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


def crosses_inside(seg, card):
    # Open rectangle shrunk by half a pixel, so a segment that only touches a border does not count.
    x0, y0 = card["x"] + 0.5, card["y"] + 0.5
    x1, y1 = card["x"] + card["w"] - 0.5, card["y"] + card["h"] - 0.5
    (ax, ay), (bx, by) = seg
    if ay == by:
        return y0 < ay < y1 and min(ax, bx) < x1 and max(ax, bx) > x0
    if ax == bx:
        return x0 < ax < x1 and min(ay, by) < y1 and max(ay, by) > y0
    return False


@unittest.skipIf(NODE is None, "node is not installed")
class SystemLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_node(CASES)

    def layout(self, name):
        return self.out[name]["layout"]

    def test_no_card_overlaps_and_all_inside(self):
        for name in ("grid24", "chain", "other"):
            lay = self.layout(name)
            cards = lay["cards"]
            for i, a in enumerate(cards):
                self.assertTrue(0 <= a["x"] and a["x"] + a["w"] <= lay["width"], name)
                self.assertTrue(0 <= a["y"] and a["y"] + a["h"] <= lay["height"], name)
                for b in cards[i + 1:]:
                    self.assertFalse(overlaps(a, b), (name, a["id"], b["id"]))

    def test_layer_order_left_to_right(self):
        lay = self.layout("grid24")
        xs = {}
        for c in lay["cards"]:
            xs.setdefault(c["layer"], set()).add(c["x"])
        self.assertTrue(all(len(v) == 1 for v in xs.values()))
        order = [layer for layer, _ in sorted(((l, next(iter(v))) for l, v in xs.items()), key=lambda p: p[1])]
        self.assertEqual(order, lay["layers"])
        self.assertEqual(lay["layers"], ["ui", "service", "cli", "data", "external"])

    def test_routes_orthogonal_and_on_card_borders(self):
        for name in ("grid24", "chain", "other"):
            lay = self.layout(name)
            cards = {c["id"]: c for c in lay["cards"]}
            self.assertEqual(len(lay["routes"]), len(CASES[name].get("edges", [])) if name != "chain" else 4, name)
            for r in lay["routes"]:
                pts = r["points"]
                for p, q in zip(pts, pts[1:]):
                    self.assertTrue(p[0] == q[0] or p[1] == q[1], (name, r["from"], r["to"]))
                src, dst = cards[r["from"]], cards[r["to"]]
                self.assertEqual(pts[0], [src["x"] + CARD_W, src["y"] + CARD_H / 2])
                self.assertEqual(pts[-1], [dst["x"], dst["y"] + CARD_H / 2])
                self.assertTrue(r["d"].startswith("M "))

    def test_no_route_crosses_a_card(self):
        for name in ("grid24", "chain"):
            lay = self.layout(name)
            for r in lay["routes"]:
                pts = r["points"]
                for p, q in zip(pts, pts[1:]):
                    for card in lay["cards"]:
                        self.assertFalse(crosses_inside((p, q), card), (name, r["from"], r["to"], card["id"]))

    def test_deterministic_and_order_independent(self):
        for name in CASES:
            self.assertEqual(self.out[name]["text"], self.out[name]["again"], name)
            self.assertEqual(self.out[name]["text"], self.out[name]["shuffled"], name)

    def test_edge_cases_are_reported_not_fatal(self):
        chain = self.layout("chain")
        self.assertEqual(len(chain["routes"]), 4)
        self.assertTrue(any("missing" in w for w in chain["warnings"]))
        other = self.layout("other")
        self.assertEqual(other["layers"], ["ui", "other"])
        self.assertEqual([c["layer"] for c in other["cards"]], ["ui", "other", "other"])
        empty = self.layout("empty")
        self.assertEqual((empty["cards"], empty["routes"], empty["columns"]), ([], [], []))
        self.assertGreater(empty["width"], 0)

    def test_twenty_four_cards_under_50_ms(self):
        self.assertLess(self.out["grid24"]["ms"], 50)

    def test_module_has_no_dom_or_markup(self):
        with open(SYSLAYOUT, encoding="utf-8") as f:
            src = f.read()
        for pat in (r"\bdocument\b", r"\binnerHTML\b", r"\bMath\.random\b", r"\bDate\.now\b"):
            self.assertIsNone(re.search(pat, src), pat)


if __name__ == "__main__":
    unittest.main()
