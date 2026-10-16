"""R10.7 / H173: the Planner is the fourth view of Work. The Work section renders it from the same snapshot, old
planner routes redirect to it, and a hostile plan (parent cycles, duplicate ids, a self parent) neither throws nor
hangs. Runs in node (no DOM). Skipped when node is not installed."""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")

NODE_CODE = """
const web = process.argv[1];
const state = await import(web + "/js/state.js");
const work = await import(web + "/js/views/work.js");
const planner = await import(web + "/js/views/planner.js");
const routes = await import(web + "/js/routes.js");
const rows = JSON.parse(process.argv[2]);
const now = Date.parse("2026-10-13T12:00:00Z");
const snap = { project: { id: "demo", title: "demo" }, tasks: [], features: { rows: rows, uncovered: [], orphans: [],
  counts: {} } };
const store = state.createStore();
store.projects = [{ id: "demo", name: "demo" }];
store.snapshots.demo = state.normalizeSnapshot(snap, now);
const route = { name: "project", id: "demo", section: "work", view: "planner", item: null, filters: {} };
const vm = state.buildViewModel(store, route, { mode: null, open: {} }, now);
const t0 = Date.now();
const html = work.sectionView(vm);
const plan = planner.plannerHtml(vm.project.snapshot, { status: "", open: {}, edit: null, pick: null, project: "demo",
  focus: "" });
console.log(JSON.stringify({ html: html, plan: plan, ms: Date.now() - t0,
  ids: routes.SECTIONS.map((s) => s.id),
  legacy: [routes.legacyPlannerHash("#/p/demo/planner"), routes.legacyPlannerHash("#/p/demo/planner?f=F5"),
    routes.legacyPlannerHash("#/p/demo/planner?f=bad"), routes.legacyPlannerHash("#/all/planner"),
    routes.legacyPlannerHash("#/p/demo/work/planner")] }));
"""


def row(fid, parent=None):
    return {"id": fid, "label": fid, "title": "Item " + fid, "phase": None, "done": 0, "total": 0, "blocked": 0,
            "state": "todo", "parent": parent}


def render(rows):
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([node, "--input-type=module", "-e", NODE_CODE, Path(WEB).as_uri(), json.dumps(rows)],
                          capture_output=True, text=True, check=False, timeout=30)
    if proc.returncode != 0:
        raise AssertionError("work.js failed in node: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class WorkPlannerTest(unittest.TestCase):
    def test_work_renders_the_planner_view_with_the_view_switch(self):
        out = render([row("F1"), row("F2", "F1")])
        html = out["html"]
        self.assertIn('data-section="planner"', html)
        self.assertIn('data-wk="view" data-view="planner"', html)
        self.assertIn('aria-pressed="true" data-wk="view" data-view="planner"', html)
        self.assertIn("2 plan items", html)
        self.assertEqual(html.count('<h2 class="page-title">Work</h2>'), 1)
        self.assertNotIn("planner", out["ids"])

    def test_old_planner_routes_redirect_to_work_planner(self):
        legacy = render([])["legacy"]
        self.assertEqual(legacy, ["#/p/demo/work/planner", "#/p/demo/work/planner?f=F5", "#/p/demo/work/planner",
                                  "#/all/work", None])

    def test_hostile_plan_does_not_throw_or_hang(self):
        rows = [row("F1", "F2"), row("F2", "F1"), row("F3", "F3"), row("F4"), row("F4"), row("F5", "F9")]
        out = render(rows)
        self.assertLess(out["ms"], 2000)
        self.assertIn("pl-feat-F4", out["plan"])


if __name__ == "__main__":
    unittest.main()
