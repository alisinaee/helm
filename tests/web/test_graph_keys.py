"""Keyboard on the workflow diagram canvas (R6.34b).

Checks: the SVG canvas has tabindex 0 (one tab stop) and keeps role and aria-label; every node keeps tabindex 0; the
keydown handler is bound to the SVG, so keys work from the canvas and from a focused node; keyPlan maps + - 0 Escape,
arrows and Shift+arrows as the spec says (run in node when node is installed); no style or on* attributes are added.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
GRAPH = os.path.join(REPO, "web", "js", "graph")
NODE = shutil.which("node")


def source(name):
    with open(os.path.join(GRAPH, name), encoding="utf-8") as f:
        return f.read()


class CanvasFocusSourceTest(unittest.TestCase):
    def test_svg_canvas_is_focusable_with_role_and_label(self):
        render = source("render.js")
        m = re.search(r'el\("svg",\s*\{(.*?)\}', render, re.S)
        self.assertIsNotNone(m, "svg element call not found")
        attrs = m.group(1)
        self.assertIn("tabindex: 0", attrs)
        self.assertIn('role: "group"', attrs)
        self.assertIn('"aria-label": "Workflow diagram"', attrs)

    def test_nodes_keep_their_own_tab_stop(self):
        render = source("render.js")
        nodes = re.findall(r'el\("g", \{ class: [^\n]*?tabindex: 0', render)
        self.assertGreaterEqual(len(nodes), 4)

    def test_keydown_is_bound_to_the_svg(self):
        viewport = source("viewport.js")
        self.assertIn('svg.addEventListener("keydown"', viewport)

    def test_no_inline_style_or_handlers_added(self):
        for name in ("render.js", "viewport.js"):
            text = source(name)
            self.assertNotIn("innerHTML", text, name)
            self.assertIsNone(re.search(r'["\']style["\']\s*[:,]', text), name)
            self.assertIsNone(re.search(r'\bon[a-z]+\s*[:=]\s*["\']', text), name)


@unittest.skipUnless(NODE, "node is not installed")
class KeyPlanTest(unittest.TestCase):
    def test_key_plan_mapping(self):
        script = (
            "import(process.argv[1]).then(m => {"
            "const k = (key, shift) => m.keyPlan(key, shift);"
            "console.log(JSON.stringify({"
            "plus: k('+', false), minus: k('-', false), zero: k('0', false), esc: k('Escape', false),"
            "right: k('ArrowRight', false), shiftRight: k('ArrowRight', true), other: k('a', false)"
            "}));});"
        )
        url = "file://" + os.path.join(GRAPH, "viewport.js")
        proc = subprocess.run([NODE, "--experimental-default-type=module", "-e", script, url],
                              capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        out = json.loads(proc.stdout)
        self.assertEqual(out["plus"], {"op": "zoom", "f": 1.25})
        self.assertEqual(out["minus"], {"op": "zoom", "f": 0.8})
        self.assertEqual(out["zero"], {"op": "fit"})
        self.assertEqual(out["esc"], {"op": "clear"})
        # R7.14 D: Right walks the path order (Up and Down keep the nearest-node focus).
        self.assertEqual(out["right"], {"op": "walk", "step": 1})
        self.assertEqual(out["shiftRight"]["op"], "pan")
        self.assertIsNone(out["other"])

class RenderMarkupTest(unittest.TestCase):
    """R7.14 C: the flow markup (arrows, frames, Now flag, copy slot) and the CSS budget, checked in source."""

    def setUp(self):
        self.render = source("render.js")
        with open(os.path.join(REPO, "web", "css", "graph.css"), encoding="utf-8") as f:
            self.css = f.read()

    def test_no_style_attribute_or_handler_is_set(self):
        self.assertNotIn("setAttribute(\"style\"", self.render)
        self.assertNotIn("addEventListener", self.render)
        self.assertIsNone(re.search(r"\bon[a-z]+\s*[:=]\s*[\"']", self.render))

    def test_one_arrow_marker_per_edge_class(self):
        m = re.search(r"const MARKERS = \[(.*?)\];", self.render)
        self.assertIsNotNone(m, "MARKERS list not found")
        names = re.findall(r'"([a-z]+)"', m.group(1))
        self.assertEqual(names, ["sequence", "dependency", "handoff", "blocker", "lead"])
        self.assertIn('"marker-end": marker', self.render)
        self.assertIn('id: "wfg-arrow-" + type', self.render)
        for selector in (".wfg-arrow{", ".wfg-arrow-dependency{", ".wfg-arrow-handoff{", ".wfg-arrow-blocker{",
                         ".wfg-arrow-lead{"):
            self.assertIn(selector, self.css)

    def test_edges_are_classed_and_styled_in_css(self):
        self.assertIn('"wfg-e wfg-e-" + e.type', self.render)
        for name in ("dependency", "handoff", "blocker", "lead"):
            self.assertIn(".wfg-e-%s{" % name, self.css, name)
        self.assertIn("stroke-dasharray", self.css)

    def test_now_flag_is_drawn(self):
        self.assertIn('"You are here"', self.render)
        self.assertIn('"wfg-flag"', self.render)
        self.assertIn(".wfg-flag-box{", self.css)

    def test_every_node_has_an_empty_copy_slot(self):
        self.assertIn('el("g", { class: "wfg-ref" })', self.render)
        self.assertGreaterEqual(self.render.count('"wfg-ref"'), 1)

    def test_reduced_motion_stops_the_pulse(self):
        self.assertIn("prefers-reduced-motion: reduce", self.css)
        self.assertIn(".wfg-s-doing .wfg-glyph{animation:none}", self.css)

    def test_graph_css_stays_within_its_budget(self):
        self.assertLessEqual(len(self.css.encode("utf-8")), 6 * 1024, "graph.css over 6 KB")



if __name__ == "__main__":
    unittest.main()
