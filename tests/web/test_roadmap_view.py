"""Roadmap lanes (R7.110): counts, the doing chip from a running job, long lanes fold, no money in lanes."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(REPO, "web")
SCRIPT = """
import { pathToFileURL } from "node:url";
const web = process.argv[2];
const load = (n) => import(pathToFileURL(web + "/js/" + n).href);
const state = await load("state.js");
const roadmap = await load("views/roadmap.js");
const tasks = [];
for (let i = 1; i <= 15; i++) tasks.push({ id: "A." + i, phase: "A", title: "t" + i, state: "todo" });
tasks.push({ id: "B.1", phase: "B", title: "b", state: "partial" });
const raw = { project: { id: "x", title: "x" }, summary: {}, overall: { project: { done: 0, total: 16 } },
  phases: [{ id: "A", name: "Alpha", state: "todo", done: 0, total: 15, progress: 0 },
           { id: "B", name: "Beta", state: "partial", done: 0, total: 1, progress: 0.5 }],
  tasks: tasks, jobs: [{ id: "j1", task: "B.1", status: "running" }], blocked: [] };
const s = state.createStore();
s.projects = [{ id: "x", name: "x", progress: 0, tasks_left: 16, running: 1, need_user: 0, errors_count: 0, stale: false }];
s.snapshots.x = state.normalizeSnapshot(raw, 0);
function html(open) {
  const vm = state.buildViewModel(s, { name: "project", id: "x", section: "roadmap", view: null, item: null,
    filters: {} }, { mode: null, open: open || {} }, 0);
  vm.snapshotList = [s.snapshots.x];
  vm.control = null;
  return roadmap.sectionView(vm);
}
console.log(JSON.stringify({ folded: html(), unfolded: html({ "more:A": true }) }));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RoadmapViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.mjs")
            with open(path, "w") as fh:
                fh.write(SCRIPT)
            out = subprocess.run(["node", path, WEB], capture_output=True, text=True, check=True).stdout
        cls.out = json.loads(out)

    def test_counts_and_legend(self):
        h = self.out["folded"]
        self.assertIn("0/15 done", h)
        self.assertIn("15 open", h)
        self.assertIn("doing = a job is running", h)

    def test_long_lane_folds_and_unfolds(self):
        self.assertEqual(self.out["folded"].count('data-task="A.'), 8 * 3)  # card, up, down buttons
        self.assertIn("Show 7 more", self.out["folded"])
        self.assertEqual(self.out["unfolded"].count('data-task="A.'), 15 * 3)
        self.assertIn("Show first 8", self.out["unfolded"])

    def test_doing_from_running_job(self):
        h = self.out["folded"]
        self.assertIn("▶ doing", h)
        self.assertIn("▶ 1 doing", h)
        self.assertEqual(h.count("▶ 1 doing"), 1)

    def test_no_money_in_lanes(self):
        for word in ("budget", "spent", "est "):
            self.assertNotIn(word, self.out["folded"])


if __name__ == "__main__":
    unittest.main()
