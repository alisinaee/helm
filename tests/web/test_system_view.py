"""The System views (R10.33): web/js/views/system.js renders the view switcher, layered diagrams (bands, shaped nodes,
edges with arrowheads and labels), sequence diagrams, the data matrix, and the empty/error states."""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_system.mjs")
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script|innerHTML', re.IGNORECASE)


def read(*parts):
    with open(os.path.join(WEB, *parts), encoding="utf-8") as fh:
        return fh.read()


def render():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([node, "--experimental-default-type=module", RENDER, WEB],
                          capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


class SystemViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = render()

    def test_switcher_has_every_view_and_components_is_the_default(self):
        self.assertEqual(self.out["views"], ["context", "containers", "components", "modules", "layers", "flows",
                                             "data"])
        html = self.out["ok"]
        self.assertIn("aria-busy", self.out["okLoading"])
        for label in ("Context", "Containers", "Components", "Modules", "Layers", "Flows", "Data"):
            self.assertIn(">%s</button>" % label, html)
        self.assertIn('data-sys-view="components" aria-pressed="true"', html)
        self.assertIn("12 source files · 3.4k lines · 40 imports", html)
        self.assertIn("system.json: bad", html)
        self.assertIn("C4 level 3", html)

    def test_components_are_drawn_in_bands_with_labelled_arrows(self):
        html = self.out["ok"]
        self.assertEqual(len(re.findall(r'class="wfg-n[" ]', html)), 3)
        self.assertIn(">Web app [browser]</text>", html)
        self.assertIn('data-sys="c:api"', html)
        self.assertEqual(html.count('marker-end="url(#sys-a-'), 3)
        self.assertIn('<marker id="sys-a-x"', html)
        self.assertIn(">GET snapshot</text>", html)
        self.assertIn('stroke-dasharray="6 4"', html)  # the cycle edge
        self.assertIn("<title>Web UI with a very long component name", html)
        self.assertNotIn(">Web UI with a very long component name</text>", html)
        self.assertIn('fill="var(--surface-2)"', html)  # colours are token vars

    def test_activity_marks_from_details(self):
        html = self.out["ok"]
        self.assertIn("1 job(s) running", html)
        self.assertIn("4 commits in 30 days", html)

    def test_shapes_for_people_stores_and_externals(self):
        svg = self.out["containers"]
        self.assertIn('rx="25"', svg)  # person pill
        self.assertRegex(svg, r'<path d="M0 7a94 7 0 0 1 188 0v36')  # store cylinder
        self.assertIn('stroke-dasharray="5 3"', svg)  # external system
        self.assertIn('marker-end="url(#sys-a-d)"', svg)

    def test_sequence_diagram(self):
        svg = self.out["flow"]
        self.assertEqual(svg.count("<line "), 3)  # one lifeline per participant
        for n in range(1, 5):
            self.assertIn(">%d.</tspan>" % n, svg)
        self.assertIn('stroke-dasharray="5 4"', svg)  # the reply
        self.assertIn("h34v14h-30", svg)  # the self call loop

    def test_data_matrix(self):
        svg = self.out["matrix"]
        self.assertEqual(svg.count("<circle "), 20)
        self.assertEqual(svg.count('fill="none" stroke="var(--info)"'), 8)
        self.assertIn("rotate(-55)", svg)

    def test_opening_view_never_above_100_or_below_60_percent(self):
        small, big = self.out["open"]
        self.assertEqual(small["k"], 1)
        self.assertEqual(big["k"], 0.6)
        self.assertEqual(big["x"], 12)

    def test_missing_api_old_service_and_errors(self):
        self.assertIn("System map needs the API", self.out["missing"])
        self.assertIn('data-sys-op="retry"', self.out["missing"])
        self.assertIn("could not be read", self.out["broken"])
        self.assertNotIn("aria-busy", self.out["broken"])
        self.assertIn("Restart the service", self.out["old"])
        self.assertIn("Pick a project", self.out["global"])

    def test_source_rules(self):
        for path in (("js", "views", "system.js"), ("js", "graph", "syslayout.js"), ("css", "system.css")):
            text = read(*path)
            self.assertIsNone(INLINE.search(text), path)
            if path[0] == "js":
                self.assertTrue(all(len(line) <= 120 for line in text.splitlines()), path)
        self.assertLessEqual(len(read("css", "system.css").encode()), 400)
        self.assertIn("/css/system.css", read("index.html"))
        self.assertIn('id: "system"', read("js", "routes.js"))


if __name__ == "__main__":
    unittest.main()
