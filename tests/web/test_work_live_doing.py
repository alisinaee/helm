"""R7.78: the Work board's Doing column follows live running jobs. Node renders board.js with a small snapshot in
memory (no file is written): a partial task with a running job is Doing, a partial task with none is Todo with the
started chip, todo with a running job is Doing, and hold and done keep their column. Skipped when node is missing."""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")

SCRIPT = """
const web = process.env.WEB;
const snap = JSON.parse(process.env.SNAP);
const load = (name) => import("file://" + web + "/js/" + name);
const state = await load("state.js");
const board = await load("views/board.js");
const now = Date.parse("2026-10-15T12:00:00Z");
const norm = state.normalizeSnapshot(snap, now);
const tasks = board.workTasks(norm, now);
const ctx = { pid: "demo", snap: norm, shown: tasks, col: "doing", fine: false, view: "board", filters: {},
  F: board.parseFilters(""), all: tasks };
const html = board.boardView(ctx);
const out = {};
for (const t of tasks) out[t.id] = { col: board.columnKey(t.state), started: t.started, running: t.running };
const doingStart = html.indexOf('id="wk-col-doing"');
const doingEnd = html.indexOf('id="wk-col-hold"');
out.doingIds = [];
const re = /data-wk-task="([^"]+)"/g;
let m;
while ((m = re.exec(html.slice(doingStart, doingEnd))) !== null) out.doingIds.push(m[1]);
out.startedChips = (html.match(/chip-neutral">started</g) || []).length;
console.log(JSON.stringify(out));
"""


def snapshot():
    def task(tid, status):
        return {"id": tid, "phase": "P1", "title": tid + " title", "state": status, "model": "haiku",
                "tokensK": 1, "needsUser": False, "subs": [], "feats": [], "check": "none", "checkK": 0,
                "note": None}
    return {
        "server_time": "2026-10-15T12:00:00+00:00", "errors": [], "jobs": [
            {"id": "j1", "task": "P1.1", "title": "run", "model": "haiku", "status": "running",
             "started": "2026-10-15T11:59:00+00:00", "ended": None, "elapsed_s": 60, "tokensK": None},
            {"id": "j2", "task": "P1.4", "title": "run", "model": "haiku", "status": "running",
             "started": "2026-10-15T11:59:00+00:00", "ended": None, "elapsed_s": 60, "tokensK": None}],
        "project": {"id": "demo", "title": "demo"}, "tasks_updated": "2026-10-15",
        "phases": [{"id": "P1", "name": "Work", "state": "todo", "done": 0, "total": 6, "progress": 0.0}],
        "tasks": [task("P1.1", "partial"), task("P1.2", "partial"), task("P1.3", "todo"),
                  task("P1.4", "todo"), task("P1.5", "hold"), task("P1.6", "done")],
        "summary": {}, "blocked": [], "comments": {}, "budget": {}, "needsYou": [], "spikes": [], "rh": [],
        "next": [], "log": [], "overall": {}, "agents": {"running": [], "groups": {}, "roots": []},
    }


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class WorkLiveDoingTests(unittest.TestCase):
    def run_node(self):
        env = dict(os.environ, WEB=WEB, SNAP=json.dumps(snapshot()))
        proc = subprocess.run(["node", "--input-type=module", "-e", SCRIPT], env=env, capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_doing_is_exactly_the_tasks_with_a_running_job(self):
        out = self.run_node()
        self.assertEqual(out["P1.1"]["col"], "doing")
        self.assertEqual(out["P1.4"]["col"], "doing")
        self.assertEqual(sorted(out["doingIds"]), ["P1.1", "P1.4"])

    def test_partial_without_a_job_is_todo_with_started_chip(self):
        out = self.run_node()
        self.assertEqual(out["P1.2"]["col"], "todo")
        self.assertTrue(out["P1.2"]["started"])
        self.assertFalse(out["P1.3"]["started"])
        self.assertGreaterEqual(out["startedChips"], 1)

    def test_hold_and_done_keep_their_column(self):
        out = self.run_node()
        self.assertEqual(out["P1.5"]["col"], "hold")
        self.assertEqual(out["P1.6"]["col"], "done")
        self.assertEqual(out["P1.1"]["running"], 1)


if __name__ == "__main__":
    unittest.main()
