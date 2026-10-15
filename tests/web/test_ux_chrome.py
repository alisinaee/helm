"""UX group A (docs/UX-AUDIT.md R8.1-3, R8.18-19): nav badges for blockers and inbox rows, phone bottom nav labels,
the skeleton's busy region, and focus rings in the shell and the right panel.

The badge and skeleton checks run web/js in node (skipped when node is missing). The CSS checks read the stylesheets."""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
CSS = os.path.join(WEB, "css")

SCRIPT = """
import { pathToFileURL } from "node:url";
const web = process.argv[1];
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const nav = await load("views/nav.js");
const dom = await load("dom.js");
const snap = {
  questions: [{ id: "Q1" }, { id: "Q2" }],
  needsYou: [{ kind: "task", id: "t1" }, { kind: "question", id: "Q9" }],
  issues: [{ kind: "blocker" }, { kind: "bug" }],
  runningCount: 0,
  tasks: [],
};
const counts = nav.countsFor({ snapshotList: [snap, { questions: [], needsYou: [], issues: [], tasks: [] }] });
const one = nav.countsFor({
  snapshotList: [{ questions: [], needsYou: [], issues: [{ kind: "blocker" }], tasks: [] }],
});
const inboxHtml = nav.navView({ route: { section: "inbox" }, ui: {}, snapshotList: [snap] });
const issuesHtml = nav.navView({ route: { section: "issues" }, ui: {}, snapshotList: [snap] });
console.log(JSON.stringify({ counts, one, inboxHtml, issuesHtml, skel: dom.skeletonHtml(["w-60"]) }));
"""


def read(name):
    with open(os.path.join(CSS, name), encoding="utf-8") as fh:
        return fh.read()


def run_node():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT, WEB], capture_output=True, text=True,
                          check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class NavBadgeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = run_node()

    def test_inbox_count_is_questions_plus_needs_you_tasks(self):
        self.assertEqual(self.out["counts"]["inbox"], 3)

    def test_issues_count_is_open_blockers(self):
        self.assertEqual(self.out["counts"]["issues"], 1)
        self.assertEqual(self.out["one"]["issues"], 1)

    def test_inbox_badge_is_drawn_and_says_waiting(self):
        self.assertIn('data-tone="neutral">3<span class="sr-only"> waiting for you', self.out["inboxHtml"])

    def test_issues_badge_is_danger_and_singular_for_one(self):
        html = self.out["issuesHtml"]
        self.assertIn('data-tone="danger">1<span class="sr-only"> open blocker</span>', html)


class SkeletonTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = run_node()

    def test_skeleton_is_a_busy_region_with_spoken_loading(self):
        skel = self.out["skel"]
        self.assertTrue(skel.startswith('<div aria-busy="true"><span class="sr-only">Loading</span>'), skel)
        self.assertIn('<div aria-hidden="true"><span class="skel w-60"></span></div>', skel)
        self.assertTrue(skel.endswith("</div></div>"))


class FocusAndPhoneCssTests(unittest.TestCase):

    def test_phone_bottom_nav_shows_its_labels(self):
        shell = read("shell.css")
        self.assertIn('.app[data-nav="mini"] .bnav-i .nav-l{position:static;', shell)

    def test_bottom_nav_icons_are_heavier_for_contrast(self):
        self.assertIn(".bnav-i .ico{stroke-width:2.2}", read("shell.css"))

    def test_shell_and_panel_have_explicit_focus_rings(self):
        self.assertIn(".nav-i:focus-visible", read("shell.css"))
        self.assertIn(".p-row:focus-visible", read("panel.css"))

    def test_skeleton_respects_reduced_motion(self):
        components = read("components.css")
        self.assertIn("@media (prefers-reduced-motion: reduce) {\n  .skel {\n    animation: none;", components)


if __name__ == "__main__":
    unittest.main()
