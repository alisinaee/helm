"""The System view (R10.23, A5): web/js/views/system.js renders cards, edges with markers, and the empty/error states."""

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

    def test_loading_then_cards(self):
        self.assertIn("aria-busy", self.out["okLoading"])
        html = self.out["ok"]
        self.assertEqual(html.count('wfg-n sys-card'), 3)
        self.assertIn('data-sys="api"', html)
        self.assertIn("Open full screen", html)
        self.assertIn("#/full/ok/system", html)
        self.assertIn("system.json: bad", html)

    def test_long_name_is_clipped_with_tooltip(self):
        html = self.out["ok"]
        self.assertIn("<title>Web UI with a very long component name", html)
        self.assertNotIn(">Web UI with a very long component name</text>", html)

    def test_edges_have_arrow_markers(self):
        html = self.out["ok"]
        self.assertEqual(html.count('marker-end="url(#sys-arrow)"'), 3)
        self.assertIn('<marker id="sys-arrow"', html)
        self.assertIn("wfg-e-dependency", html)

    def test_heat_mode_buttons_and_bars(self):
        html = self.out["ok"]
        for label in ("Off", "Commits", "Jobs", "Work"):
            self.assertIn(">%s</button>" % label, html)
        self.assertIn('data-sys-heat="commits" aria-pressed="true"', html)
        self.assertIn('class="sys-heat wfg-nowbar"', html)

    def test_missing_api_and_errors_have_retry(self):
        self.assertIn("System map needs the API", self.out["missing"])
        self.assertIn('data-sys-op="retry"', self.out["missing"])
        self.assertIn("could not be read", self.out["broken"])
        self.assertIn('data-sys-op="retry"', self.out["broken"])
        self.assertNotIn("aria-busy", self.out["broken"])

    def test_empty_and_global(self):
        self.assertIn("No structure found", self.out["emptyBody"])
        self.assertIn("Pick a project", self.out["global"])

    def test_source_rules(self):
        for path in (("js", "views", "system.js"), ("css", "system.css")):
            text = read(*path)
            self.assertIsNone(INLINE.search(text), path)
            if path[0] == "js":
                self.assertTrue(all(len(line) <= 120 for line in text.splitlines()), path)
        self.assertLessEqual(len(read("css", "system.css").encode()), 400)
        self.assertIn("/css/system.css", read("index.html"))
        self.assertIn('id: "system"', read("js", "routes.js"))
