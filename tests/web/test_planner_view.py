"""The Planner view (WP53): rendered in node from tests/fixtures/planner_snapshot.json by tests/web/render_planner.mjs,
plus static checks on the CSS, the markup rules and the lint.

The checks: seven feature rows, the sub-feature after its parent, a shared task listed under both of its features,
the uncovered and orphan callouts, the empty state, the add form, the Acc box state, every aria-controls naming an id
in the same output, no inline style or on*= handler, the row-grid on every row, planner.css within 3 KB with no raw
colours, and the lint is clean for planner.js. Skipped with a message when node is not installed.
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
RENDER = os.path.join(TESTS, "web", "render_planner.mjs")
SNAPSHOT = os.path.join(TESTS, "fixtures", "planner_snapshot.json")
CSS = os.path.join(WEB, "css", "planner.css")
INDEX = os.path.join(WEB, "index.html")
sys.path.insert(0, os.path.join(REPO, "tools"))

FEAT = re.compile(r'<li class="pl-feat')
SUB = re.compile(r'<li class="pl-feat pl-sub')
CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def render_all():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([node, RENDER, WEB, SNAPSHOT], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError("render_planner.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class PlannerViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = render_all()

    def test_every_case_renders_and_controls_resolve(self):
        for name, html in self.out.items():
            self.assertTrue(html, name)
            ids = set(IDS.findall(html))
            for target in CONTROLS.findall(html):
                self.assertIn(target, ids, name + ": " + target)

    def test_no_inline_style_or_handler_and_no_script(self):
        for name, html in self.out.items():
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("<script", html, name)

    def test_one_row_per_feature_with_the_sub_feature_after_its_parent(self):
        html = self.out["defaultView"]
        self.assertEqual(len(FEAT.findall(html)), 7)
        self.assertEqual(len(SUB.findall(html)), 1)
        self.assertLess(html.index('data-id="F11"'), html.index('<li class="pl-feat pl-sub'))
        self.assertTrue('class="pl-row row-grid' in html, "feature rows use the row grid")
        self.assertTrue('class="pl-head pl-row row-grid rg-head"' in html, "header uses the row grid")

    def test_shared_task_is_listed_under_both_features(self):
        self.assertEqual(self.out["defaultView"].count('data-task="R1.3"'), 2)

    def test_callouts_name_uncovered_features_and_orphan_tasks(self):
        html = self.out["defaultView"]
        self.assertTrue("! 2 uncovered features" in html, "uncovered callout")
        self.assertIn("F11b Start wakes a session", html)
        self.assertIn("! 3 orphan tasks", html)
        self.assertEqual(html.count('data-pl="assign"'), 3)

    def test_uncovered_filter_keeps_only_those_rows(self):
        html = self.out["uncoveredFilter"]
        self.assertEqual(len(FEAT.findall(html)), 2)

    def test_no_match_and_empty_state(self):
        self.assertTrue("No features match these filters." in self.out["noMatch"], "no match text")
        empty = self.out["emptyFeatures"]
        self.assertIn("No features yet.", empty)
        self.assertIn("9 tasks are orphans.", empty)
        self.assertNotIn("pl-feat", empty)
        self.assertIn('data-pl="adding"', empty)

    def test_add_form_only_when_adding(self):
        self.assertIn('data-pl-form="add"', self.out["addForm"])
        self.assertNotIn('data-pl-form="add"', self.out["defaultView"])

    def test_accept_box_reflects_the_stored_acceptance(self):
        html = self.out["defaultView"]
        f1 = html[html.index('data-id="F1" data-state="done"'):]
        self.assertIn("checked", f1[:f1.index("aria-label")+200])
        f2 = html[html.index('data-id="F2" data-state="doing"'):]
        self.assertNotIn(" checked", f2[:f2.index("⋯")])

    def test_the_menu_opens_only_for_the_chosen_feature(self):
        html = self.out["openAndMenu"]
        self.assertTrue('<div class="pl-menu" id="pl-menu-F2" role="group"' in html, "F2 menu open")
        self.assertTrue('id="pl-menu-F3" role="group" aria-label="Actions for F3" hidden>' in html, "F3 menu closed")
        self.assertTrue('disabled aria-label="Remove F2 (unlink its tasks first)"' in html, "remove disabled")

    def test_every_control_is_a_native_element(self):
        for name, html in self.out.items():
            self.assertNotIn('role="button"', html, name)
            self.assertNotIn("tabindex", html, name)

    def test_planner_css_is_small_and_uses_tokens_only(self):
        with open(CSS, encoding="utf-8") as fh:
            css = fh.read()
        self.assertLessEqual(len(css.encode("utf-8")), 3072)
        self.assertIsNone(HEX.search(css))

    def test_index_links_the_stylesheet_once(self):
        with open(INDEX, encoding="utf-8") as fh:
            index = fh.read()
        self.assertEqual(index.count('href="/css/planner.css"'), 1)

    def test_lint_is_clean_for_the_planner(self):
        import lint_js

        issues = [issue for issue in lint_js.run(REPO) if "planner" in issue]
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
