"""The Workflow Table (R7.114, web/js/views/wf_table.js): one row per task, sorted Needs you, Running, Failed, Queued,
Done; the filter row (All, Needs you, Running, Failed, Done); the next action per state; numbers in fixed right-aligned
columns; the empty state; no inline style or handler; escaped data.

A small synthetic snapshot is laid out by web/js/views/workflow.js in node, then the table is rendered. Skipped
when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
NOW_S = 1791980000  # seconds; the render pins Date.now to it

# Spans: [job, task, model, role, parent, start_s, end_s, status, tokensK]
SNAPSHOT = {
    "project": {"id": "alpha", "title": "Alpha"},
    "phases": [],
    "tasks": [
        {"id": "T1", "title": "Done one", "phase": "P1", "state": "done", "model": "haiku"},
        {"id": "T2", "title": "Running <b>two</b>", "phase": "P1", "state": "doing", "model": "sonnet"},
        {"id": "T3", "title": "Failed three", "phase": "P1", "state": "doing", "model": "opus"},
        {"id": "T4", "title": "Queued four", "phase": "P1", "state": "todo", "model": ""},
        {"id": "T5", "title": "Blocked five", "phase": "P1", "state": "block", "model": ""},
        {"id": "T6", "title": "Old done six", "phase": "P1", "state": "done", "model": "haiku"},
    ],
    "jobs": [],
    "queue": [{"task": "T4", "by": "cli"}],
    "blocked": ["T5"],
    "workflow": {
        "spans": [
            ["J1", "T1", "haiku", "worker", None, NOW_S - 600, NOW_S - 300, "done", 10],
            ["J2", "T2", "sonnet", "worker", None, NOW_S - 200, None, "running", 5],
            ["J3", "T3", "opus", "worker", None, NOW_S - 400, NOW_S - 100, "failed", 7],
            ["J4", "T6", "haiku", "worker", None, NOW_S - 5000, NOW_S - 4000, "done", None],
        ],
        "edges": {"after": [], "block": []},
    },
}

SCRIPT = """
import { layout } from "%(wf)s";
import { tableHtml } from "%(table)s";
const snap = %(snap)s;
const now = %(now)s * 1000;
const out = {};
const model = layout(snap, "week", now);
model.now = now;
model.route = { name: "project", id: "alpha", section: "workflow", view: "table", item: null,
  filters: { f: "range:week" } };
out.all = tableHtml(model);
model.route = Object.assign({}, model.route, { filters: { f: "range:week,tf:needs" } });
out.needs = tableHtml(model);
model.route = Object.assign({}, model.route, { filters: { f: "range:week,tf:failed" } });
out.failed = tableHtml(model);
const none = layout({ project: { id: "alpha", title: "Alpha" }, jobs: [], tasks: [], workflow: {} }, "week", now);
none.now = now;
none.route = { name: "project", id: "alpha", section: "workflow", view: "table", item: null, filters: {} };
out.empty = tableHtml(none);
console.log(JSON.stringify(out));
"""


def run_table():
    node = shutil.which("node")
    script = SCRIPT % {
        "wf": "file://" + os.path.join(WEB, "js", "views", "workflow.js"),
        "table": "file://" + os.path.join(WEB, "js", "views", "wf_table.js"),
        "snap": json.dumps(SNAPSHOT),
        "now": NOW_S,
    }
    proc = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True,
                          check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("wf_table render failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def task_rows(html):
    """The (task id, row inner html) of each table body row, in order."""
    rows = re.findall(r"<tr>(.*?)</tr>", html)
    return [(re.match(r'<td class="wf-id">([^<]*)</td>', r).group(1), r)
            for r in rows if r.startswith('<td class="wf-id">')]


def states(html):
    return [re.search(r'<span class="chip [^"]*">([^<]*)</span>', r).group(1) for _, r in task_rows(html)]


class WfTableTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed")
        cls.out = run_table()

    def test_rows_are_one_per_task_sorted_needs_running_failed_queued_done(self):
        ids = [task for task, _ in task_rows(self.out["all"])]
        self.assertEqual(ids, ["T5", "T2", "T3", "T4", "T1", "T6"])
        self.assertEqual(states(self.out["all"]), ["Needs you", "Running", "Failed", "Queued", "Done", "Done"])

    def test_filters_show_their_state_and_all_link_back(self):
        self.assertEqual([task for task, _ in task_rows(self.out["needs"])], ["T5"])
        self.assertEqual([task for task, _ in task_rows(self.out["failed"])], ["T3"])
        self.assertIn('aria-label="Filter tasks"', self.out["all"])
        for label in ("All", "Needs you", "Running", "Failed", "Done"):
            self.assertRegex(self.out["all"], r'<a href="[^"]*"(?: aria-current="page")?>%s</a>' % label)

    def test_next_action_depends_on_the_state(self):
        rows = dict(task_rows(self.out["all"]))
        self.assertIn(">Answer</a>", rows["T5"])
        self.assertIn(">Open in Work</a>", rows["T2"])
        self.assertIn(">Retry in Work</a>", rows["T3"])
        self.assertIn(">Open in Work</a>", rows["T1"])
        for html in rows.values():
            self.assertEqual(html.count('<a class="btn btn-small"'), 1)

    def test_numbers_are_right_aligned_in_fixed_columns(self):
        head = re.search(r"<thead>(.*?)</thead>", self.out["all"]).group(1)
        self.assertEqual(head.count("<th "), 9)
        self.assertEqual(head.count('class="rg-num"'), 4)
        rows = dict(task_rows(self.out["all"]))
        self.assertEqual(rows["T2"].count('class="rg-num num"'), 4)
        self.assertIn('<td class="rg-num num">1/1</td>', rows["T2"])
        self.assertIn('<td class="rg-num num">5k</td>', rows["T2"])
        self.assertIn('<td class="rg-num num">–</td>', rows["T4"])

    def test_title_cell_is_ellipsised_and_data_is_escaped(self):
        rows = dict(task_rows(self.out["all"]))
        self.assertIn('class="hd-c"', rows["T2"])
        self.assertIn("Running &lt;b&gt;two&lt;/b&gt;", rows["T2"])
        self.assertNotIn("<b>two</b>", self.out["all"])

    def test_no_inline_style_or_handler(self):
        self.assertIsNone(re.search(r"\sstyle\s*=|\son[a-z]{3,}\s*=", self.out["all"], re.IGNORECASE))

    def test_empty_range_says_so_and_offers_all(self):
        self.assertIn("No tasks in this range.", self.out["empty"])
        self.assertIn("Show all</a>", self.out["empty"])
        self.assertNotIn("<table", self.out["empty"])


if __name__ == "__main__":
    unittest.main()
