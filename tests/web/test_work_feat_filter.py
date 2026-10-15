"""Work section, plan item filter (R7.13 H6): f=feat:<FeatureId> shows the tasks linked to that plan item and to all
its descendants, with a removable chip above the list. The views run in node (no DOM), as in test_planner_view.py."""

import copy
import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
FIXTURE = os.path.join(TESTS, "fixtures", "planner_snapshot.json")
WORK_JS = os.path.join(WEB, "js", "views", "work.js")

NODE_CODE = """
import { readFileSync } from "node:fs";
const [webUrl, snapPath, f] = process.argv.slice(1);
const state = await import(webUrl + "/js/state.js");
const work = await import(webUrl + "/js/views/work.js");
const raw = JSON.parse(readFileSync(snapPath, "utf8"));
const now = Date.parse("2026-10-13T12:00:00Z");
const snap = Object.assign({ project: { id: "splitnet", title: "split-net" } }, raw);
const store = state.createStore();
store.projects = [{ id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 4, running: 0,
  need_user: 0, errors_count: 0, stale: false }];
store.snapshots.splitnet = state.normalizeSnapshot(snap, now);
const filters = f ? { f: f } : {};
const route = { name: "project", id: "splitnet", section: "work", view: "list", item: null, filters: filters };
const vm = state.buildViewModel(store, route, { mode: null, open: {} }, now);
console.log(JSON.stringify({ html: work.sectionView(vm) }));
"""


def scenario():
    """The planner fixture with four tasks: T1 under F1, T2 under the child F1a of F1, T3 under F2, T4 under none."""
    with open(FIXTURE, encoding="utf-8") as fh:
        data = json.load(fh)
    top = data["features"]["rows"][0]
    rows = []
    for fid, parent, label, title in [("F1", None, "P0", "Top item"), ("F1a", "F1", "P0.0", "Child item"),
                                      ("F2", None, "P1", "Other item")]:
        row = copy.deepcopy(top)
        row.update({"id": fid, "parent": parent, "label": label, "title": title})
        rows.append(row)
    data["features"] = {"rows": rows, "uncovered": [], "orphans": [], "counts": {}}
    task = copy.deepcopy(data["tasks"][0])
    tasks = []
    for tid, feats, state in [("T1", ["F1"], "todo"), ("T2", ["F1a"], "todo"), ("T3", ["F2"], "todo"),
                              ("T4", [], "todo")]:
        t = copy.deepcopy(task)
        t.update({"id": tid, "title": "Task " + tid, "state": state, "feats": feats})
        tasks.append(t)
    data["tasks"] = tasks
    return data


class WorkFeatFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if cls.node is None:
            raise unittest.SkipTest("node is not installed")
        cls.dir = Path(os.environ.get("TMPDIR", "/tmp")) / ("wkfeat-%d" % os.getpid())
        cls.dir.mkdir(parents=True, exist_ok=True)
        cls.snap = cls.dir / "snapshot.json"
        cls.snap.write_text(json.dumps(scenario()), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def render(self, f=""):
        proc = subprocess.run([self.node, "--input-type=module", "-e", NODE_CODE, Path(WEB).as_uri(),
                               str(self.snap), f], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise AssertionError("sectionView failed: " + proc.stderr[-800:])
        return json.loads(proc.stdout)["html"]

    def shown_ids(self, html):
        return sorted(set(re.findall(r'data-task="([^"]+)"', html)))

    def test_subtree_includes_children_at_any_depth(self):
        self.assertEqual(self.shown_ids(self.render("feat:F1")), ["T1", "T2"])

    def test_leaf_item_shows_only_its_own_tasks(self):
        self.assertEqual(self.shown_ids(self.render("feat:F2")), ["T3"])

    def test_no_scope_shows_every_task(self):
        self.assertEqual(self.shown_ids(self.render("")), ["T1", "T2", "T3", "T4"])

    def test_chip_is_removable_and_named(self):
        html = self.render("feat:F1")
        self.assertIn('role="group" aria-label="Plan item filter"', html)
        self.assertIn('data-wk="feat-clear"', html)
        self.assertIn('aria-label="Remove filter Plan item: P0 Top item"', html)
        self.assertIn("Plan item: P0 Top item", html)
        self.assertNotIn("data-wk=\"feat-clear\"", self.render(""))

    def test_chip_comes_before_the_list(self):
        html = self.render("feat:F1")
        self.assertLess(html.index("Plan item filter"), html.index("<table") if "<table" in html else
                        html.index("wk-filters"))

    def test_other_filters_combine_with_the_scope(self):
        self.assertEqual(self.shown_ids(self.render("feat:F1,status:done")), [])
        self.assertEqual(self.shown_ids(self.render("feat:F1,status:todo")), ["T1", "T2"])

    def test_filter_bar_chips_keep_the_scope_in_their_links(self):
        html = self.render("feat:F1,status:todo")
        self.assertIn("feat%3AF1", html)

    def test_unknown_plan_item_shows_its_id_and_no_tasks(self):
        html = self.render("feat:F9")
        self.assertIn("Plan item: F9", html)
        self.assertEqual(self.shown_ids(html), [])


class WorkFeatFilterStaticTest(unittest.TestCase):
    def setUp(self):
        with open(WORK_JS, encoding="utf-8") as fh:
            self.src = fh.read()

    def test_no_inline_style_script_or_innerhtml(self):
        self.assertIsNone(re.search(r"\sstyle\s*=", self.src))
        self.assertIsNone(re.search(r"\son[a-z]{3,}\s*=", self.src))
        self.assertNotIn("innerHTML", self.src)

    def test_lines_fit_120_columns(self):
        for number, line in enumerate(self.src.splitlines(), 1):
            self.assertLessEqual(len(line), 120, "line %d is too long" % number)

    def test_feat_token_is_split_off_before_the_tag_filters(self):
        self.assertIn("const F = parseFilters(scope.rest);", self.src)
        self.assertIn("if (tags) params.set(\"f\", tags);", self.src)


if __name__ == "__main__":
    unittest.main()
