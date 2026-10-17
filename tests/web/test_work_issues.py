"""Issues on the Work board (R7.97): issue cards in the status columns, the blocker badge, the Kind filter, the issue
buttons, and the Issues section gone from navigation with its old links sent to Work.

The checks render the Board in node from the golden snapshot with two issues added (an open bug and a doing blocker
on the first live task). The node script is passed inline, so no helper file is needed. Skipped with a message when
node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
SNAPSHOT = os.path.join(TESTS, "fixtures", "golden_snapshot.json")

NODE_SCRIPT = """
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const web = process.argv[1];
const raw = JSON.parse(readFileSync(process.argv[2], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const work = await load("views/work.js");
const routes = await load("routes.js");
const now = Date.parse("2026-10-13T12:00:00Z");
const store = state.createStore();
store.projects = [{ id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 0,
  need_user: 0, errors_count: 0, stale: false }];
store.snapshots.splitnet = state.normalizeSnapshot(raw, now);
function viewOf(filters) {
  const vm = state.buildViewModel(store, { name: "project", id: "splitnet", section: "work", view: "board",
    item: null, filters: filters }, { mode: null, open: {} }, now);
  return work.sectionView(vm);
}
const out = {
  board: viewOf({}),
  issuesOnly: viewOf({ f: "kind:issue" }),
  tasksOnly: viewOf({ f: "kind:task" }),
  blockedIssues: viewOf({ f: "kind:issue,blocked" }),
  legacyItem: routes.legacyIssuesHash("#/p/splitnet/issues/i/I1"),
  legacyBlockers: routes.legacyIssuesHash("#/p/splitnet/issues?f=blockers"),
  legacyPlain: routes.legacyIssuesHash("#/p/splitnet/issues"),
  notLegacy: routes.legacyIssuesHash("#/p/splitnet/work/board"),
  sections: routes.SECTIONS.map(function (s) {
    return s.id;
  }),
};
console.log(JSON.stringify(out));
"""

INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)


def augmented_snapshot(path):
    """Write a copy of the golden snapshot with two issues: I1 open bug, I2 doing blocker on the first live task."""
    with open(SNAPSHOT, encoding="utf-8") as fh:
        raw = json.load(fh)
    live = [t["id"] for t in raw["tasks"] if t.get("state") != "deferred"]
    task = live[0]
    raw["issues"] = [
        {"id": "I1", "kind": "bug", "title": "Crash on save", "sev": 1, "status": "open", "tasks": []},
        {"id": "I2", "kind": "blocker", "title": "Missing fixture", "sev": 2, "status": "doing", "tasks": [task]},
    ]
    raw["blocked"] = [task]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    return task


def columns(html):
    """The Board columns by data-state: each column's markup, from its section opening to the next one."""
    parts = html.split('<section class="wk-col" ')[1:]
    out = {}
    for part in parts:
        state = re.search(r'data-state="([a-z]+)"', part).group(1)
        out[state] = part
    return out


class WorkIssuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("node is not installed; the Work issue render checks are skipped")
        cls.tmp = tempfile.mkdtemp(prefix="work-issues-")
        path = os.path.join(cls.tmp, "snapshot.json")
        cls.task = augmented_snapshot(path)
        proc = subprocess.run(
            [cls.node, "--input-type=module", "-e", NODE_SCRIPT, WEB, path],
            capture_output=True, text=True, check=False, timeout=120,
        )
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_open_and_doing_issues_sit_in_todo_and_doing(self):
        cols = columns(self.out["board"])
        self.assertIn('data-wk-issue="I1"', cols["todo"])
        self.assertIn('data-wk-issue="I2"', cols["partial"])
        self.assertNotIn('data-wk-issue="I2"', cols["todo"])

    def test_issue_card_has_kind_chips(self):
        html = self.out["board"]
        self.assertIn('<span class="chip chip-neutral">issue</span>', html)
        self.assertIn('<span class="chip chip-danger">blocker</span>', html)
        self.assertIn('<span class="chip chip-neutral">sev1</span>', html)

    def test_blocked_task_shows_the_blocker_badge(self):
        cols = columns(self.out["board"])
        card = re.search(r'<li class="wk-card[^"]*" data-wk-task="%s".*?</li>' % re.escape(self.task),
                         "".join(cols.values()), re.S)
        self.assertIsNotNone(card)
        self.assertIn('href="#/p/splitnet/work/board/i/I2', card.group(0))
        self.assertIn("⛔ I2", card.group(0))

    def test_issue_buttons_use_issue_status(self):
        html = self.out["board"]
        self.assertIn('data-wk="issue-status" data-issue="I1" data-to="doing"', html)
        self.assertIn('data-wk="issue-status" data-issue="I1" data-to="closed"', html)
        self.assertIn('data-wk="issue-status" data-issue="I1" data-to="wontfix"', html)
        self.assertNotIn('data-issue="I2" data-to="doing"', html)
        self.assertIn('data-wk="issue-status" data-issue="I2" data-to="closed"', html)

    def test_kind_filter_chips_and_each_kind(self):
        html = self.out["board"]
        self.assertIn('data-tb-token="kind:task"', html)
        self.assertIn('data-tb-token="kind:issue"', html)
        self.assertIn('data-tb-token="kind:all"', html)
        self.assertNotIn('data-tb-token="kind:all" checked', html)
        self.assertIn('data-tb-token="kind:issue" checked', self.out["issuesOnly"])
        self.assertNotIn('data-wk-task="', self.out["issuesOnly"])
        self.assertIn('data-wk-issue="I1"', self.out["issuesOnly"])
        self.assertNotIn('data-wk-issue="', self.out["tasksOnly"])
        self.assertIn('data-wk-task="%s"' % self.task, self.out["tasksOnly"])

    def test_blocked_filter_keeps_only_blocker_issues(self):
        html = self.out["blockedIssues"]
        self.assertIn('data-wk-issue="I2"', html)
        self.assertNotIn('data-wk-issue="I1"', html)
        self.assertNotIn('data-wk-task="', html)

    def test_no_inline_style_or_handlers(self):
        for key in ("board", "issuesOnly", "blockedIssues"):
            self.assertIsNone(INLINE.search(self.out[key]), key)

    def test_old_issues_links_go_to_work_with_kind_issue(self):
        self.assertEqual(self.out["legacyItem"], "#/p/splitnet/work/i/I1?f=kind:issue")
        self.assertEqual(self.out["legacyBlockers"], "#/p/splitnet/work?f=kind:issue,blocked")
        self.assertEqual(self.out["legacyPlain"], "#/p/splitnet/work?f=kind:issue")
        self.assertIsNone(self.out["notLegacy"])

    def test_issues_are_not_a_section(self):
        self.assertNotIn("issues", self.out["sections"])
        self.assertIn("work", self.out["sections"])


if __name__ == "__main__":
    unittest.main()
