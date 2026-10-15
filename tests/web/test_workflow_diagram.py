"""The workflow diagram renderer and viewport (WP72), run in node by tests/web/render_diagram.mjs over
tests/fixtures/graph.

Checks: no style attribute, no inline handler, no eval, no new Function and no innerHTML in web/js/graph/*.js or in the
Map code of views/workflow.js; the graph modules are imported only by the Map (dynamic import inside loadGraph, never
statically); graph.css stays within 6 KB, uses tokens only (no hex or rgb colours) and is linked once from index.html;
the CSS total stays under the 72 KB cap; the gesture state machine pans 40 px without a tap, taps only within 6 px,
pinches to a larger scale, double-taps to zoom, clamps the zoom to 0.25 to 3, and moves focus to the nearest node; the
built SVG gives every focusable node an aria-label, role and tabindex, has no style attribute, and defines the hatch
pattern once; focus mode's closure contains the node and both its upstream and downstream nodes. The node checks are
skipped when node is not installed.
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
GRAPH_DIR = os.path.join(WEB, "js", "graph")
WORKFLOW = os.path.join(WEB, "js", "views", "workflow.js")
RENDER = os.path.join(TESTS, "web", "render_diagram.mjs")
FIXTURES = os.path.join(TESTS, "fixtures", "graph")
GRAPH_CSS = os.path.join(WEB, "css", "graph.css")
GRAPH_CSS_MAX = 6 * 1024
CSS_TOTAL_MAX = 72 * 1024  # raised with the R7.12 copy column (see test_shell.py)
FORBIDDEN = [
    (re.compile(r"\sstyle\s*="), "style attribute"),
    (re.compile(r"\son[a-z]{3,}\s*="), "inline handler"),
    (re.compile(r"\beval\s*\("), "eval"),
    (re.compile(r"new\s+Function\b"), "new Function"),
    (re.compile(r"\binnerHTML\b"), "innerHTML"),
    (re.compile(r"\binsertAdjacentHTML\b"), "insertAdjacentHTML"),
]
HEX_OR_RGB = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(")
NODE = shutil.which("node")


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def graph_sources():
    return sorted(os.path.join(GRAPH_DIR, name) for name in os.listdir(GRAPH_DIR) if name.endswith(".js"))


def render():
    proc = subprocess.run([NODE, "--experimental-default-type=module", RENDER, WEB, FIXTURES],
                          capture_output=True, text=True, check=False, timeout=120)
    if proc.returncode != 0:
        raise AssertionError("render_diagram.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class DiagramSourceTests(unittest.TestCase):

    def test_graph_sources_have_no_style_handler_eval_or_innerhtml(self):
        for path in graph_sources():
            self.assertNoForbidden(read_text(path), os.path.basename(path))

    def test_map_code_in_workflow_has_no_style_handler_eval_or_innerhtml(self):
        text = read_text(WORKFLOW)
        block = text[text.index("// The Map (WP72)"):text.index("\nexport function sectionView")]
        self.assertNoForbidden(block, "workflow.js Map code")

    def assertNoForbidden(self, text, label):
        for pattern, what in FORBIDDEN:
            hit = pattern.search(text)
            self.assertIsNone(hit, "%s uses %s: %r" % (label, what, hit and hit.group(0)))

    def test_graph_modules_are_imported_only_by_the_map(self):
        text = read_text(WORKFLOW)
        self.assertIsNone(re.search(r'^import[^\n]*"\.\./graph/', text, re.MULTILINE), "static graph import")
        dynamic = re.findall(r'import\("\.\./graph/([a-z]+)\.js"\)', text)
        self.assertEqual(sorted(dynamic), ["layout", "minimap", "model", "render"])
        load = text[text.index("function loadGraph()"):text.index("function narrow()")]
        self.assertEqual(len(re.findall(r'import\("\.\./graph/', load)), 4)

    def test_viewport_and_render_are_separate_modules(self):
        self.assertTrue(os.path.isfile(os.path.join(GRAPH_DIR, "viewport.js")))
        self.assertTrue(os.path.isfile(os.path.join(GRAPH_DIR, "render.js")))
        self.assertLessEqual(len(read_text(os.path.join(GRAPH_DIR, "viewport.js")).splitlines()), 490)


class DiagramCssTests(unittest.TestCase):

    def test_graph_css_is_within_budget_and_uses_tokens_only(self):
        size = os.path.getsize(GRAPH_CSS)
        self.assertLessEqual(size, GRAPH_CSS_MAX, "graph.css is %d bytes" % size)
        self.assertIsNone(HEX_OR_RGB.search(read_text(GRAPH_CSS)), "graph.css has a literal colour")

    def test_css_total_stays_under_the_cap(self):
        total = 0
        css_dir = os.path.join(WEB, "css")
        for name in os.listdir(css_dir):
            if name.endswith(".css"):
                total += os.path.getsize(os.path.join(css_dir, name))
        self.assertLessEqual(total, CSS_TOTAL_MAX, "CSS total is %d bytes" % total)

    def test_index_links_graph_css_once(self):
        self.assertEqual(read_text(os.path.join(WEB, "index.html")).count('href="/css/graph.css"'), 1)


@unittest.skipIf(NODE is None, "node is not installed")
class DiagramNodeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = render()

    def test_pan_of_40_px_moves_the_view_and_is_not_a_tap(self):
        pan = self.out["pan40"]
        self.assertEqual(pan["res"], "end")
        self.assertEqual(pan["view"]["x"], 40)
        self.assertEqual(pan["view"]["k"], 1)

    def test_a_pointer_within_6_px_is_a_tap_and_leaves_the_view(self):
        self.assertEqual(self.out["tap"]["res"], "tap")
        self.assertEqual(self.out["tap"]["view"], {"k": 1, "x": 0, "y": 0})
        self.assertEqual(self.out["jitterAt6"]["res"], "tap")

    def test_two_pointers_pinch_the_scale_up(self):
        pinch = self.out["pinch"]
        self.assertGreater(pinch["view"]["k"], 1.9)
        self.assertEqual(pinch["res"], ["none", "end"])

    def test_two_quick_taps_double_zoom_and_a_slow_second_tap_does_not(self):
        self.assertEqual(self.out["doubleTap"]["first"], "tap")
        self.assertEqual(self.out["doubleTap"]["second"], "double")
        self.assertEqual(self.out["doubleTap"]["k"], 2)
        self.assertEqual(self.out["slowTwoTaps"]["second"], "tap")

    def test_wheel_zooms_in_for_a_negative_delta_and_the_zoom_is_clamped(self):
        self.assertGreater(self.out["wheelIn"]["view"]["k"], 1)
        self.assertEqual(self.out["zoomClamp"], {"max": 3, "min": 0.25})

    def test_zoom_keeps_the_point_under_the_cursor(self):
        self.assertEqual(self.out["zoomKeepsPoint"], {"x": 100, "y": 50})

    def test_keys_map_to_zoom_fit_pan_focus_and_clear(self):
        keys = self.out["keys"]
        self.assertEqual(keys["plus"], {"op": "zoom", "f": 1.25})
        self.assertEqual(keys["minus"], {"op": "zoom", "f": 0.8})
        self.assertEqual(keys["zero"], {"op": "fit"})
        self.assertEqual(keys["escape"], {"op": "clear"})
        # R7.14 D: Left and Right walk the path order; Up and Down move to the nearest node.
        self.assertEqual(keys["arrow"], {"op": "walk", "step": -1})
        self.assertEqual(keys["shiftArrow"], {"op": "pan", "dx": 40, "dy": 0})
        self.assertIsNone(keys["other"])

    def test_arrows_move_focus_to_the_nearest_node_in_that_direction(self):
        near = self.out["nearest"]
        self.assertEqual(near["right"], "b")
        self.assertEqual(near["down"], "c")
        self.assertIsNone(near["left"])
        self.assertEqual(near["fromD_up"], "b")

    def test_fit_and_open_views_keep_the_diagram_readable(self):
        self.assertAlmostEqual(self.out["fit"]["k"], 1.92, places=2)
        self.assertEqual(self.out["open"]["k"], 1)
        self.assertEqual(self.out["openWide"]["k"], 0.6)
        self.assertEqual(self.out["openWide"]["y"], 16)

    def test_every_fixture_builds_one_focusable_node_per_interactive_node(self):
        cases = self.out["cases"]
        self.assertEqual(set(cases), {"350-tasks", "chain", "cycle", "empty", "fan-in", "with-blockers"})
        for name, case in cases.items():
            # R7.14 C draws Start and End pills as well, so the SVG has two nodes more than the graph.
            self.assertEqual(case["svgNodes"], case["interactiveNodes"] + 2, name)
            self.assertEqual(case["styledElements"], [], name)
            self.assertEqual(case["hatchDefs"], 1, name)
            self.assertTrue(case["closureContainsSelf"], name)
            self.assertTrue(case["edgeBothWays"], name)

    def test_every_focusable_node_has_an_aria_label_role_and_tabindex(self):
        for name, case in self.out["cases"].items():
            for node in case["nodes"]:
                self.assertTrue(node["label"], "%s %s has no aria-label" % (name, node["id"]))
                self.assertEqual(node["role"], "button", name)
                self.assertEqual(node["tabindex"], "-1", name)

    def test_the_viewport_starts_at_the_identity_transform(self):
        for name, case in self.out["cases"].items():
            self.assertEqual(case["transform"], "translate(0 0) scale(1)", name)

    def test_closure_of_a_missing_node_is_empty(self):
        for name, case in self.out["cases"].items():
            self.assertIsNone(case["closureOfMissing"], name)


if __name__ == "__main__":
    unittest.main()
