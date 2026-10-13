"""The Work section (WP31): Board, List and Tree rendered in node from the golden snapshot, plus static checks.

tests/web/render_work.mjs renders the views with no DOM. The snapshot is the golden fixture with a few extra facts
added in a temporary copy (subtasks, a blocker, a comment, a needs-you flag and a budget row), so the subtask, flag,
comment and meter paths are covered. The checks: nothing throws, the card, row and subtask counts match the snapshot,
every aria-controls names an id in the same output, no inline style or on*= handler appears, work.css is within its
6 KB budget, the sort and filter helpers give the expected results, and the Work modules are lint clean.
Skipped with a message when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_work.mjs")
SNAPSHOT = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
WORK_FILES = ["work.js", "board.js", "list.js", "tree.js"]

CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
CARD = re.compile(r'<li class="wk-card')
ROW = re.compile(r'<tr class="[^"]*" data-wk-task=')
SUB = re.compile(r'data-wk="sub"')
GROUP_HEAD = re.compile(r'<tr class="wk-group-head">')
PHASE = re.compile(r'<section class="wk-phase">')


def augmented_snapshot(path):
    """Write a copy of the golden snapshot with subtasks, a blocker, a comment and a budget row; return its path."""
    with open(SNAPSHOT, encoding="utf-8") as fh:
        raw = json.load(fh)
    live = [t for t in raw["tasks"] if t.get("state") != "deferred"]
    first, second, third = live[0]["id"], live[1]["id"], live[2]["id"]
    for task in raw["tasks"]:
        if task["id"] == first:
            task["subs"] = [{"t": "step one", "d": True}, {"t": "step two", "d": False}]
        if task["id"] == second:
            task["needsUser"] = True
        if task["id"] == third:
            task["subs"] = [{"t": "only step", "d": False}]
    raw["blocked"] = [third]
    raw["comments"] = {first: [{"by": "ali", "at": "2026-10-12T10:00:00Z", "t": "a note"}]}
    raw["budget"] = {"tasks": {first: {"spent": 40.0, "limit": 100.0, "pct": 40.0}}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    return path, len(live)


def render(snapshot_path):
    node = shutil.which("node")
    proc = subprocess.run(
        [node, "--experimental-default-type=module", RENDER, WEB, snapshot_path],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if proc.returncode != 0:
        raise AssertionError("render failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class WorkViewTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the Work render check is skipped")
        cls.tmp = tempfile.mkdtemp(prefix="wk-test-")
        path, live = augmented_snapshot(os.path.join(cls.tmp, "snapshot.json"))
        cls.live = live
        cls.out = render(path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmp", ""), ignore_errors=True)

    def test_views_render_and_are_non_empty(self):
        for name in ("board", "list", "listSorted", "tree", "boardEmptyFilter"):
            self.assertIn(name, self.out)
            self.assertGreater(len(self.out[name]), 300, name)

    def test_board_has_four_columns_and_one_card_per_open_task(self):
        html = self.out["board"]
        for label in ("Todo", "Doing", "Hold", "Done"):
            self.assertIn('<span>' + label + '</span>', html, label)
        self.assertEqual(len(CARD.findall(html)), self.live)
        self.assertGreaterEqual(html.count('data-wk="status"'), self.live)

    def test_board_cards_show_flags_and_meter(self):
        html = self.out["board"]
        self.assertIn("needs you", html)
        self.assertIn("blocked", html)
        self.assertIn("1/2 subtasks", html)
        self.assertIn("1 comment", html)
        self.assertIn("meter-fill", html)

    def test_list_rows_match_tasks_and_group_by_phase(self):
        html = self.out["list"]
        self.assertEqual(len(ROW.findall(html)), self.live)
        self.assertGreater(len(GROUP_HEAD.findall(html)), 1)
        self.assertIn('aria-sort="none"', html)
        self.assertIn('data-wk="select"', html)
        self.assertIn('data-wk="group"', html)
        ungrouped = self.out["listSorted"]
        self.assertEqual(len(GROUP_HEAD.findall(ungrouped)), 0)
        self.assertEqual(len(ROW.findall(ungrouped)), self.live)

    def test_tree_has_phases_and_subtask_checkboxes(self):
        html = self.out["tree"]
        self.assertGreater(len(PHASE.findall(html)), 1)
        self.assertEqual(len(SUB.findall(html)), 3)
        self.assertIn('checked', html)

    def test_filter_that_matches_nothing_shows_fewer_cards(self):
        self.assertLess(len(CARD.findall(self.out["boardEmptyFilter"])), self.live)

    def test_no_inline_style_or_handlers(self):
        for name in ("board", "list", "listSorted", "tree", "boardEmptyFilter"):
            self.assertIsNone(INLINE.search(self.out[name]), name)
            self.assertNotIn("<script", self.out[name], name)

    def test_aria_controls_name_an_id_in_the_same_output(self):
        for name in ("board", "list", "tree"):
            html = self.out[name]
            ids = set(IDS.findall(html))
            for ref in CONTROLS.findall(html):
                self.assertIn(ref, ids, name + " aria-controls " + ref)

    def test_sort_and_filter_helpers(self):
        ids = self.out["sortIdDesc"]
        self.assertEqual(len(ids), self.live)
        self.assertEqual(ids, sorted(ids, key=lambda s: [int(p) if p.isdigit() else p for p in
                                                         re.split(r"(\d+)", s)], reverse=True))
        self.assertEqual(self.out["nextSort"], ["id:asc", "id:desc", "title:asc"])
        self.assertEqual(self.out["filters"], ["needs", "model:haiku", "status:todo", "phase:P1"])
        self.assertEqual(self.out["toggled"], ["needs,blocked", "blocked"])

    def test_work_css_is_within_budget(self):
        size = os.path.getsize(os.path.join(WEB, "css", "work.css"))
        self.assertLessEqual(size, 6 * 1024, "work.css is %d bytes" % size)

    def test_work_modules_exist_and_are_lint_clean(self):
        for name in WORK_FILES:
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", "views", name)), name)
        sys.path.insert(0, os.path.join(REPO, "tools"))
        try:
            import lint_js
        finally:
            sys.path.pop(0)
        issues = [i for i in lint_js.run(REPO) if any(("views/" + n) in i for n in WORK_FILES)]
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
