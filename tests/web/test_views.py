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

    def test_timers_are_marked_and_running_phase_stays_folded_by_default(self):
        html = self.views["default"]
        self.assertIn('data-started-ms="', html)
        self.assertNotIn("Repo layout, tooling, lint, CI skeleton", html)

    def test_minimal_view_collapses_the_other_sections(self):
        html = self.views["minimal"]
        self.assertIn("Phases", html)
        self.assertGreaterEqual(html.count('aria-expanded="false"'), 5)

    def test_minimal_view_opens_no_phase_by_itself(self):
        for name in ("default", "minimal"):
            html = self.views[name]
            self.assertIsNone(re.search(r'class="phase-row[^"]*is-open', html), name)
            self.assertNotIn("Repo layout, tooling, lint, CI skeleton", html, name)

    def test_expanded_view_shows_running_phase_task_rows(self):
        self.assertIn("Repo layout, tooling, lint, CI skeleton", self.views["expanded"])

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


class FinishedRowTests(unittest.TestCase):
    """A finished-job title drops a leading model word that the model chip already shows.

    The full title stays in the title attribute.
    """

    def test_short_title_strips_only_the_matching_model_prefix(self):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed")
        script = (
            "const m = await import(process.argv[1]);"
            "const cases = [{model:'haiku', title:'haiku: WP2 store'}, {model:'opus', title:'Opus: plan'},"
            "{model:'haiku', title:'opus: mismatch'}, {model:null, title:'haiku: none'}, {model:'agy', title:'agy:x'}];"
            "console.log(JSON.stringify(cases.map(c => m.shortTitle(c))));"
        )
        url = "file://" + os.path.join(WEB, "js", "views", "running.js")
        proc = subprocess.run([shutil.which("node"), "--input-type=module", "-e", script, url],
                              capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertEqual(json.loads(proc.stdout), ["WP2 store", "plan", "opus: mismatch", "haiku: none", "agy:x"])

    def test_finished_titles_keep_the_full_text_in_the_title_attribute(self):
        html = render()["expanded"]
        self.assertIn('<p class="fin-title rg-t" title="', html)


class StaticModuleTests(unittest.TestCase):

    def test_section_modules_exist(self):
        for name in ("phases", "tasks", "running", "needsyou", "next", "recent", "extras", "legend"):
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", "views", name + ".js")), name)



if __name__ == "__main__":
    sys.exit(unittest.main())
