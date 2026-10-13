"""Render the project view with the golden snapshot in node (no browser) and check the markup.

The views are plain functions that return HTML strings, so node can import them with no DOM. tests/web/
render_views.mjs builds the view models from tests/fixtures/golden_snapshot.json and prints the HTML of the
default, minimal and expanded project views and of Home. The checks: nothing throws, the sections and key
task and phase text are present, every aria-controls names an element in the same output, and no inline
style or on*= handler appears. Skipped with a message when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_views.mjs")
SNAPSHOT = os.path.join(TESTS, "fixtures", "golden_snapshot.json")

CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)


def render():
    """The rendered views as a dict, or raise SkipTest-compatible errors through the caller."""
    node = shutil.which("node")
    proc = subprocess.run(
        [node, "--experimental-default-type=module", RENDER, WEB, SNAPSHOT],
        capture_output=True, text=True, check=False, timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError("render failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class ProjectViewTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the view render check is skipped")
        cls.views = render()

    def test_every_view_renders_and_is_non_empty(self):
        for name in ("default", "minimal", "expanded", "home"):
            self.assertIn(name, self.views)
            self.assertGreater(len(self.views[name]), 500, name)

    def test_project_sections_are_present(self):
        for title in ("Phases", "Running now", "Needs you", "Next up", "Recent progress", "Extras", "Legend"):
            self.assertIn(">" + title + "</span>", self.views["expanded"], title)

    def test_extras_and_task_text_are_present(self):
        html = self.views["expanded"]
        self.assertIn("Spike board", html)
        self.assertIn("Real-hardware board", html)
        self.assertIn("Spikes and foundations", html)
        self.assertIn("Repo layout, tooling, lint, CI skeleton", html)
        self.assertIn("systemd service, polkit action", html)

    def test_running_phase_opens_by_default_and_timers_are_marked(self):
        html = self.views["default"]
        self.assertIn('data-started-ms="', html)
        self.assertIn("Repo layout, tooling, lint, CI skeleton", html)

    def test_minimal_view_collapses_the_other_sections(self):
        html = self.views["minimal"]
        self.assertIn("Phases", html)
        self.assertGreaterEqual(html.count('aria-expanded="false"'), 5)

    def test_expanded_view_opens_every_section_and_phase(self):
        self.assertNotIn('aria-expanded="false"', self.views["expanded"])

    def test_every_aria_controls_names_an_element(self):
        for name in ("default", "minimal", "expanded"):
            html = self.views[name]
            ids = set(IDS.findall(html))
            missing = [target for target in CONTROLS.findall(html) if target not in ids]
            self.assertEqual(missing, [], name)

    def test_no_inline_style_or_handlers_in_output(self):
        for name, html in self.views.items():
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("<script", html, name)

    def test_home_renders_the_project_card(self):
        self.assertIn("split-net", self.views["home"])
        self.assertIn("#/p/splitnet", self.views["home"])


class StaticModuleTests(unittest.TestCase):

    def test_section_modules_exist(self):
        for name in ("phases", "tasks", "running", "needsyou", "next", "recent", "extras", "legend"):
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", "views", name + ".js")), name)



if __name__ == "__main__":
    sys.exit(unittest.main())
