"""The System views side panel (R10.33): web/js/views/system-panel.js renders the facts of the selected node from
arch.details: aligned rows (row-grid) for facts, depends on / used by (buttons that select the node), files with
lines and commits, recent commits and jobs; module and store kinds; escaping; empty input gives nothing."""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(os.path.dirname(TESTS), "web")
NODE = shutil.which("node")
SCRIPT = r"""
const { pathToFileURL } = await import("node:url");
const m = await import(pathToFileURL(process.argv[1] + "/js/views/system-panel.js").href);
const comp = { kind: "component", title: "HTTP <API>", layer: "api", language: "Python", notes: "Routes.",
  entries: ["r/s.py"], fileCount: 12, lines: 1600, commits30: 5, heat: { runningJobs: 1, openWork: 2 },
  globs: ["roadmap/http/**"], dependsOn: [{ id: "c:core", label: "Core", count: 8, note: "uses log" }],
  usedBy: [{ id: "c:web", label: "Web", count: 0, note: "GET snapshot" }],
  files: [{ path: "roadmap/http/routes.py", lines: 1200, commits: 4 }],
  commits: [{ sha: "abc1234", subject: "R1: fix <x>", at: 1790000000 }],
  jobs: [{ id: "j1", task: "R1", model: "opus", status: "running", title: "fix" }] };
const mod = { kind: "module", title: "web/js", fileCount: 3, lines: 90, files: [{ path: "web/js/a.js", lines: 30,
  commits: 0 }], dependsOn: [], usedBy: [], packages: ["react"], component: { id: "c:web", label: "Web" } };
const st = { kind: "store", title: "jobs.json", tracked: ["docs/jobs.json"], tables: [],
  readers: [{ path: "roadmap/services/jobs.py", mode: "reads, writes" }] };
const board = [];
for (let i = 1; i <= 17; i++) board.push({ id: "R" + i, title: "Task " + i, status: i === 1 ? "done" : "doing",
model: "haiku" });
board[1] = { id: "R2", title: "Evil <b>x</b>", status: "hold", model: "opus" };
const bound = { kind: "component", title: 'Board "C"', progress: { done: 1, total: 17, pct: 6 }, board,
  work: [{ id: "W3", title: "Human <card>", status: "todo", kind: "feature" }] };
const bare = { kind: "component", title: "Bare" };
const cont = { kind: "container", title: "Box", progress: { done: 0, total: 1, pct: 0 },
  board: [{ id: "R9", title: "T", status: "todo", model: "" }], work: [], refId: "box-1" };
console.log(JSON.stringify({ bound: m.panelHtml("my-pid", "c:api", bound), bare: m.panelHtml("my-pid", "c:bare", bare),
  cont: m.panelHtml("my-pid", "k:box", cont), full: m.panelHtml("my pid", "c:api", comp), mod: m.panelHtml("p",
  "m:web/js", mod),
  store: m.panelHtml("p", "s:jobs", st), none: m.panelHtml("p", null, null), missing: m.panelHtml("p", "x", null),
  human: [m.human(999), m.human(1600), m.human(-1)] }));
"""


@unittest.skipIf(NODE is None, "node is not installed")
class SystemPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run([NODE, "--experimental-default-type=module", "-e", SCRIPT, WEB],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        cls.out = json.loads(proc.stdout)

    def test_component_facts_in_aligned_rows(self):
        html = self.out["full"]
        for text in ("HTTP &lt;API&gt;", "Routes.", "r/s.py", "roadmap/http/**", "Commits (30 days)", "Open Work",
                     "roadmap/http/routes.py", "abc1234", "R1: fix &lt;x&gt;", "opus", "running"):
            self.assertIn(text, html)
        self.assertNotIn("<API>", html)
        self.assertIn('class="row-grid fin-row"', html)
        self.assertRegex(html, r'Commits \(30 days\)</span><span class="rg-num" title="5">5</span>')
        self.assertRegex(html, r'Lines</span><span class="rg-num" title="1.6k">1.6k</span>')

    def test_board_tasks_progress_and_work(self):
        html = self.out["bound"]
        self.assertIn("Board tasks (17)", html)
        self.assertIn("+2 more", html)
        self.assertNotIn("Task 17", html)
        self.assertIn('href="#/p/my-pid/roadmap/i/R1"', html)
        self.assertIn('chip chip-success">done', html)
        self.assertIn('chip chip-info">doing', html)
        self.assertIn('chip chip-warning">hold', html)
        self.assertIn('chip chip-neutral">todo', self.out["cont"])
        self.assertIn("Work items (1)", html)
        self.assertIn('href="#/p/my-pid/work/i/W3"', html)
        self.assertIn("1/17 tasks done", html)
        self.assertIn('data-pct="6"', html)
        self.assertIn("Agent jobs", self.out["full"])

    def test_actions_and_empty_state(self):
        html = self.out["bound"]
        self.assertIn('data-ref="rb:my-pid/component/api"', html)
        self.assertIn('data-action="copy-ref"', html)
        self.assertIn('data-sys-op="ask" data-sys-id="c:api" data-sys-label="Board &quot;C&quot;"', html)
        self.assertIn('href="#/p/my-pid/work">Open in Work', html)
        self.assertIn('data-ref="rb:my-pid/component/box-1"', self.out["cont"])
        self.assertIn("Board tasks (1)", self.out["cont"])
        bare = self.out["bare"]
        self.assertIn("No tasks bound yet.", bare)
        self.assertNotIn("tasks done", bare)
        self.assertNotIn("Board tasks", bare)

    def test_task_text_is_escaped(self):
        html = self.out["bound"]
        self.assertIn("Evil &lt;b&gt;x&lt;/b&gt;", html)
        self.assertIn("Human &lt;card&gt;", html)
        self.assertNotIn("<b>x</b>", html)
        self.assertNotIn("<card>", html)

    def test_related_nodes_are_buttons_that_select(self):
        html = self.out["full"]
        self.assertIn('data-sys-go="c:core"', html)
        self.assertIn('data-sys-go="c:web"', html)
        self.assertIn("Depends on", html)
        self.assertIn("Used by", html)
        self.assertIn('href="#/p/my%20pid/git"', html)

    def test_module_and_store(self):
        self.assertIn("Packages", self.out["mod"])
        self.assertIn("react", self.out["mod"])
        self.assertIn('data-sys-go="c:web"', self.out["mod"])
        self.assertIn("Module (folder)", self.out["mod"])
        self.assertIn("Read and written by", self.out["store"])
        self.assertIn("docs/jobs.json", self.out["store"])

    def test_close_and_empty(self):
        self.assertIn('data-sys-op="close"', self.out["full"])
        self.assertEqual(self.out["none"], "")
        self.assertEqual(self.out["missing"], "")
        self.assertEqual(self.out["human"], ["999", "1.6k", "0"])

    def test_wired_into_view(self):
        with open(os.path.join(WEB, "js", "views", "system.js"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("system-panel.js", src)
        self.assertRegex(src, r'"Escape"')
        with open(os.path.join(WEB, "js", "views", "system-panel.js"), encoding="utf-8") as f:
            panel = f.read()
        self.assertIsNone(re.search(r"\sstyle\s*=|innerHTML|<script", panel))
        self.assertTrue(all(len(line) <= 120 for line in panel.splitlines()))


if __name__ == "__main__":
    unittest.main()
