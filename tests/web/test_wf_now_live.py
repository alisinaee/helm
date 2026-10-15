"""R7.112 (B-1): "You are here" follows live running jobs only.

The Now node is the task that owns the newest running job. A partial task with no running job is not "here": Now
falls back to the next open task, the flag and its legend line are hidden (graph.live is false). Model checks run in
node on web/js/graph/model.js; the render and legend gates are checked in source. The node checks are skipped when node
is not installed.
"""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
NODE = shutil.which("node")
MODEL = os.path.join(WEB, "js", "graph", "model.js")


def snap(tasks, spans=None):
    return {"now": 1791979200000, "project": {"id": "p", "title": "Demo"},
            "phases": [{"id": "P1", "title": "One", "approved": True}], "tasks": tasks, "jobs": [],
            "queue": [], "issues": [], "workflow": {"spans": spans or [], "edges": {"after": [], "block": []}}}


def task(tid, state):
    return {"id": tid, "title": tid, "phase": "P1", "state": state, "model": "haiku", "at": {}, "tokensK": 1}


def run(snapshot):
    script = ("import { buildGraph } from " + json.dumps("file://" + MODEL) + ";\n"
              "const g = buildGraph(" + json.dumps(snapshot) + ", { expand: true });\n"
              "process.stdout.write(JSON.stringify({ current: g.current, live: g.live }));\n")
    proc = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True,
                          check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("model failed: " + proc.stderr[-600:])
    return json.loads(proc.stdout)


def running(jid, tid, start):
    return [jid, tid, "haiku", "worker", None, start, None, "running", None]


@unittest.skipIf(NODE is None, "node is not installed")
class LiveNowTest(unittest.TestCase):
    def test_partial_task_without_running_job_is_not_here(self):
        tasks = [task("P1.1", "done"), task("P1.2", "partial"), task("P1.3", "todo")]
        got = run(snap(tasks))
        self.assertFalse(got["live"])
        self.assertEqual("task:P1.3", got["current"])

    def test_running_job_owner_is_here_even_when_partial_tasks_exist(self):
        tasks = [task("P1.1", "partial"), task("P1.2", "partial"), task("P1.3", "todo")]
        got = run(snap(tasks, spans=[running("J1", "P1.2", 1791979000)]))
        self.assertEqual({"current": "task:P1.2", "live": True}, got)

    def test_newest_running_job_wins_over_an_older_one(self):
        tasks = [task("P1.1", "doing"), task("P1.2", "doing")]
        spans = [running("J1", "P1.1", 1791978000), running("J2", "P1.2", 1791979000)]
        self.assertEqual("task:P1.2", run(snap(tasks, spans=spans))["current"])

    def test_no_tasks_or_no_running_jobs_hide_the_flag(self):
        self.assertFalse(run(snap([]))["live"])
        got = run(snap([task("P1.1", "doing")]))
        self.assertFalse(got["live"])
        self.assertEqual("start", got["current"])


class LiveNowSourceTest(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_render_draws_the_flag_only_for_a_live_now(self):
        src = self.read("web/js/graph/render.js")
        self.assertIn("nowMarks(g.live ? flow.now : null)", src)

    def test_legend_line_follows_the_live_flag(self):
        src = self.read("web/js/views/workflow.js")
        self.assertIn("mapHasNow = !!(flow.now && flow.now.flag && graph.live);", src)


if __name__ == "__main__":
    unittest.main()
