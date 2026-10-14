"""WP47 workflow data: task stamps (at), the after list with its checks and --after, $ROADMAP_PARENT_JOB and the
automatic worker parent, the snapshot's workflow key (spans, edges, caps) and plan round trips.

Everything runs in a temp ROADMAP_HOME with a temp project; nothing touches the real home or services."""

import datetime
import io
import json
import os
import re
import unittest
from unittest import mock

from roadmap.core import planfmt, snapshot
from roadmap.errors import EXIT_USAGE
from roadmap.services import jobs
from tests.unit.test_project_support import ProjectCase, run_cli, write_json

PINNED = datetime.datetime(2026, 10, 14, 12, 0, 0, tzinfo=datetime.timezone.utc)
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
OLD_TASKS = {
    "schemaVersion": 1,
    "updated": "2026-10-13",
    "phases": [{"id": "P1", "name": "Core", "status": "todo"}],
    "tasks": [
        {"id": "P1.1", "phase": "P1", "title": "First", "status": "todo", "tokensK": 10, "thinking": "low",
         "model": "haiku", "needsUser": False, "check": "none", "checkK": 0},
        {"id": "P1.2", "phase": "P1", "title": "Second", "status": "todo", "tokensK": 20, "thinking": "low",
         "model": "haiku", "needsUser": False, "check": "none", "checkK": 0},
        {"id": "P1.3", "phase": "P1", "title": "Third", "status": "todo", "tokensK": 30, "thinking": "low",
         "model": "haiku", "needsUser": False, "check": "none", "checkK": 0},
        {"id": "P1.4", "phase": "P1", "title": "Fourth", "status": "todo", "tokensK": 40, "thinking": "low",
         "model": "haiku", "needsUser": False, "check": "none", "checkK": 0},
        {"id": "P1.5", "phase": "P1", "title": "Fifth", "status": "todo", "tokensK": 50, "thinking": "low",
         "model": "haiku", "needsUser": False, "check": "none", "checkK": 0},
        {"id": "P1.6", "phase": "P1", "title": "Sixth", "status": "todo", "tokensK": 60, "thinking": "low",
         "model": "haiku", "needsUser": False, "check": "none", "checkK": 0},
    ],
}


class WorkflowCase(ProjectCase):
    def setUp(self):
        super().setUp()
        project = self.init_and_add()
        patcher = mock.patch.dict(os.environ, {"ROADMAP_PROJECT": project["id"]})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tasks_file = os.path.join(self.data, "tasks.json")
        self.jobs_file = os.path.join(self.data, "jobs.json")
        write_json(self.tasks_file, OLD_TASKS)

    def read_tasks(self):
        with open(self.tasks_file, encoding="utf-8") as fh:
            return json.load(fh)

    def task(self, tid):
        return next(t for t in self.read_tasks()["tasks"] if t["id"] == tid)

    def raw(self):
        with open(self.tasks_file, "rb") as fh:
            return fh.read()


class StampAndByteTests(WorkflowCase):
    def test_old_file_is_byte_identical_after_reads(self):
        before = self.raw()
        for argv in (["task", "list"], ["task", "show", "P1.1"], ["plan", "export"], ["status"]):
            code, _, err = run_cli(argv)
            self.assertEqual(code, 0, (argv, err))
        self.assertEqual(self.raw(), before)

    def test_status_change_stamps_its_status_only(self):
        code, _, _ = run_cli(["task", "start", "P1.1"])
        self.assertEqual(code, 0)
        at = self.task("P1.1")["at"]
        self.assertEqual(list(at), ["partial"])
        self.assertRegex(at["partial"], ISO_RE)
        code, _, _ = run_cli(["task", "done", "P1.1"])
        self.assertEqual(code, 0)
        at = self.task("P1.1")["at"]
        self.assertEqual(set(at), {"partial", "done"})
        self.assertEqual(self.task("P1.1")["status"], "done")

    def test_missing_at_is_fine_for_other_tasks(self):
        run_cli(["task", "done", "P1.1"])
        self.assertNotIn("at", self.task("P1.2"))


class AfterTests(WorkflowCase):
    def test_set_after_then_clear(self):
        code, _, err = run_cli(["task", "set", "P1.3", "--after", "P1.1,P1.2"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.task("P1.3")["after"], ["P1.1", "P1.2"])
        code, _, _ = run_cli(["task", "set", "P1.3", "--after", ""])
        self.assertEqual(code, 0)
        self.assertNotIn("after", self.task("P1.3"))

    def test_self_reference_is_usage_error(self):
        code, _, err = run_cli(["task", "set", "P1.1", "--after", "P1.1"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("next: roadmap task show P1.1", err)
        self.assertNotIn("after", self.task("P1.1"))

    def test_unknown_id_is_usage_error_with_next_line(self):
        code, _, err = run_cli(["task", "set", "P1.2", "--after", "P9.9"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("P9.9", err)
        self.assertIn("next:", err)
        self.assertNotIn("after", self.task("P1.2"))

    def test_cycle_is_rejected_and_file_unchanged(self):
        self.assertEqual(run_cli(["task", "set", "P1.2", "--after", "P1.1"])[0], 0)
        self.assertEqual(run_cli(["task", "set", "P1.3", "--after", "P1.2"])[0], 0)
        before = self.raw()
        code, _, err = run_cli(["task", "set", "P1.1", "--after", "P1.3"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("loop", err)
        self.assertEqual(self.raw(), before)

    def test_more_than_five_ids_is_rejected(self):
        code, _, err = run_cli(["task", "set", "P1.6", "--after", "P1.1,P1.2,P1.3,P1.4,P1.5,P1.1"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("6 ids", err)

    def test_set_file_line_with_after_and_dry_run(self):
        line = "P1.4 after=P1.1,P1.2\n"
        with mock.patch("sys.stdin", io.StringIO(line)):
            code, _, _ = run_cli(["task", "set", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertNotIn("after", self.task("P1.4"))
        with mock.patch("sys.stdin", io.StringIO(line)):
            code, _, _ = run_cli(["task", "set"])
        self.assertEqual(code, 0)
        self.assertEqual(self.task("P1.4")["after"], ["P1.1", "P1.2"])


class PlanRoundTripTests(WorkflowCase):
    def test_after_survives_format_then_parse(self):
        task = {"id": "P1.3", "phase": "P1", "title": "Third", "status": "todo", "tokensK": 5, "thinking": "low",
                "model": "haiku", "needsUser": False, "check": "none", "checkK": 0,
                "after": ["P1.1", "P1.2"]}
        line = planfmt.format_task(task)
        self.assertIn(" a:P1.1,P1.2 | ", line)
        records, errors = planfmt.parse_plan(line + "\n")
        self.assertEqual(errors, [])
        self.assertEqual(records[0]["after"], ["P1.1", "P1.2"])

    def test_old_lines_parse_with_no_after(self):
        records, errors = planfmt.parse_plan("T P1.3 todo 5 haiku/low | Third\n")
        self.assertEqual(errors, [])
        self.assertIsNone(records[0]["after"])

    def test_bad_after_token_is_reported_with_line(self):
        _, errors = planfmt.parse_plan("T P1.3 todo 5 haiku/low a:P1.x | Third\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("line 1", errors[0])

    def test_plan_export_prints_after(self):
        code, _, err = run_cli(["task", "set", "P1.2", "--after", "P1.1"])
        self.assertEqual(code, 0, err)
        code, out, _ = run_cli(["plan", "export"])
        self.assertEqual(code, 0)
        self.assertIn("a:P1.1", out)


class ParentTests(WorkflowCase):
    def setUp(self):
        super().setUp()
        self.env = {}

    def start(self, role=None, parent=None, title="job"):
        return jobs.start_job(self.data, title, "haiku", parent=parent, role=role, environ=self.env)

    def test_env_parent_is_recorded(self):
        lead = self.start(title="lead")
        self.env["ROADMAP_PARENT_JOB"] = lead["id"]
        child = self.start(role="worker", title="child")
        self.assertEqual(child["parent"], lead["id"])
        self.assertEqual(child["role"], "worker")

    def test_explicit_parent_beats_env(self):
        first = self.start(title="a")
        second = self.start(title="b")
        self.env["ROADMAP_PARENT_JOB"] = first["id"]
        child = self.start(parent=second["id"], role="worker")
        self.assertEqual(child["parent"], second["id"])

    def test_unknown_env_parent_is_not_found(self):
        self.env["ROADMAP_PARENT_JOB"] = "j99"
        with self.assertRaises(Exception) as ctx:
            self.start(title="x")
        self.assertEqual(ctx.exception.code, "not_found")

    def test_worker_gets_the_only_running_lead(self):
        lead = jobs.start_job(self.data, "lead", "head", environ=self.env)
        child = self.start(role="worker", title="w")
        self.assertEqual(child["parent"], lead["id"])

    def test_two_running_leads_give_no_automatic_parent(self):
        self.start(role=None, title="plain")
        jobs.start_job(self.data, "lead one", "head", environ=self.env)
        jobs.start_job(self.data, "lead two", "head", environ=self.env)
        with self.assertRaises(Exception) as ctx:  # a worker with no parent and no single lead is refused as before
            self.start(role="worker", title="w")
        self.assertEqual(ctx.exception.code, "usage")

    def test_plain_job_with_no_env_has_no_parent(self):
        child = self.start(title="solo")
        self.assertNotIn("parent", child)


class SnapshotWorkflowTests(unittest.TestCase):
    CONFIG = {"id": "demo", "title": "Demo"}

    def tasks_text(self, count=250):
        tasks = []
        for n in range(1, count + 1):
            tasks.append({"id": "P1.%d" % n, "phase": "P1", "title": "Task %d" % n, "status": "todo",
                          "tokensK": 1, "model": "haiku", "thinking": "low"})
        tasks[1]["after"] = ["P1.1"]
        tasks[2]["after"] = ["P1.1", "P1.2", "P1.404"]
        return json.dumps({"schemaVersion": 1, "updated": "2026-10-14", "phases": [{"id": "P1", "name": "Core",
                                                                                     "status": "todo"}],
                           "tasks": tasks})

    def jobs_text(self, count=250, start=None):
        start = start or PINNED - datetime.timedelta(hours=1)
        rows = []
        for n in range(1, count + 1):
            began = start + datetime.timedelta(minutes=n)
            rows.append({"id": "j%d" % n, "title": "job %d" % n, "model": "haiku", "task": "P1.%d" % (n % 250 + 1),
                         "role": "worker", "parent": "j1" if n > 1 else None, "status": "done",
                         "started": began.isoformat(timespec="seconds"),
                         "ended": (began + datetime.timedelta(seconds=90)).isoformat(timespec="seconds"),
                         "tokensK": 12.345})
        return json.dumps({"schemaVersion": 1, "jobs": rows})

    def build(self, files):
        return snapshot.build_snapshot(files, self.CONFIG, PINNED)

    def test_spans_are_capped_at_200_newest_and_small(self):
        snap = self.build({"tasks.json": self.tasks_text(), "jobs.json": self.jobs_text()})
        spans = snap["workflow"]["spans"]
        self.assertEqual(len(spans), 200)
        self.assertEqual(spans[-1][0], "j250")
        self.assertEqual(spans[0][0], "j51")
        self.assertLessEqual(len(json.dumps(snap["workflow"], separators=(",", ":"))), 20 * 1024)
        self.assertEqual(spans[-1][:5], ["j250", "P1.1", "haiku", "worker", "j1"])
        self.assertIsInstance(spans[-1][5], int)
        self.assertEqual(spans[-1][8], 12.3)

    def test_jobs_older_than_seven_days_are_dropped(self):
        old = PINNED - datetime.timedelta(days=8)
        snap = self.build({"jobs.json": self.jobs_text(count=3, start=old)})
        self.assertEqual(snap["workflow"]["spans"], [])

    def test_running_span_has_null_end(self):
        text = json.dumps({"schemaVersion": 1, "jobs": [{"id": "j1", "title": "t", "model": "sonnet",
                                                         "status": "running",
                                                         "started": (PINNED - datetime.timedelta(minutes=5))
                                                         .isoformat(timespec="seconds")}]})
        span = self.build({"jobs.json": text})["workflow"]["spans"][0]
        self.assertIsNone(span[6])
        self.assertEqual(span[7], "running")
        self.assertIsNone(span[8])

    def test_edges_after_and_block(self):
        issues = json.dumps({"schemaVersion": 1, "issues": [
            {"id": "I1", "title": "Blocked", "kind": "blocker", "status": "open", "sev": 1, "tasks": ["P1.2"]},
            {"id": "I2", "title": "Note", "kind": "note", "status": "open", "sev": 3, "tasks": ["P1.3"]}]})
        snap = self.build({"tasks.json": self.tasks_text(count=4), "issues.json": issues})
        edges = snap["workflow"]["edges"]
        self.assertEqual(edges["after"], [["P1.1", "P1.2"], ["P1.1", "P1.3"], ["P1.2", "P1.3"]])
        self.assertEqual(edges["block"], [["I1", "P1.2"]])

    def test_empty_project_has_empty_workflow(self):
        snap = self.build({})
        self.assertEqual(snap["workflow"], {"spans": [], "edges": {"after": [], "block": []}})


if __name__ == "__main__":
    unittest.main()
