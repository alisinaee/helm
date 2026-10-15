"""R7.78: the Work board's Doing column is the live truth. The snapshot counts running jobs per task (running, left
out when zero), and a failed job that was the last running job on a partial task sets the task back to todo.
A done task keeps its status when its job fails. Temp data folders only."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from roadmap.core.snapshot import build_snapshot
from roadmap.services import jobs

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def tasks_doc(*rows):
    return {"updated": "2026-10-15", "phases": [{"id": "P1", "name": "Work", "state": "todo"}],
            "tasks": list(rows)}


def task(tid, status):
    return {"id": tid, "phase": "P1", "title": tid + " title", "status": status, "model": "haiku", "tokensK": 1}


class SnapshotRunningTests(unittest.TestCase):
    def snap(self, tasks, job_rows):
        files = {"tasks.json": json.dumps(tasks_doc(*tasks))}
        if job_rows is not None:
            files["jobs.json"] = json.dumps({"schemaVersion": 1, "jobs": job_rows})
        return build_snapshot(files, {}, NOW)

    def job(self, jid, tid, status):
        row = {"id": jid, "title": "job", "model": "haiku", "task": tid, "status": status,
               "started": "2026-10-15T11:59:00+00:00", "ended": None if status == "running" else
               "2026-10-15T11:59:30+00:00"}
        return row

    def test_missing_jobs_file_adds_no_running_key(self):
        out = self.snap([task("P1.1", "todo")], None)
        self.assertNotIn("running", out["tasks"][0])

    def test_finished_job_is_not_counted(self):
        out = self.snap([task("P1.1", "partial")], [self.job("j1", "P1.1", "failed")])
        self.assertNotIn("running", out["tasks"][0])


class FinishResetsPartialTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rm-r778-")
        self.tasks_path = os.path.join(self.dir, "tasks.json")
        with open(self.tasks_path, "w", encoding="utf-8") as fh:
            json.dump(tasks_doc(task("P1.1", "todo"), task("P1.2", "todo")), fh)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def status_of(self, tid):
        with open(self.tasks_path, encoding="utf-8") as fh:
            rows = json.load(fh)["tasks"]
        return next(t["status"] for t in rows if t["id"] == tid)

    def test_failed_last_job_sets_partial_back_to_todo(self):
        job = jobs.start_job(self.dir, "work", "haiku", task="P1.1")
        self.assertEqual(self.status_of("P1.1"), "partial")
        jobs.finish_job(self.dir, job["id"], "failed", reason="boom")
        self.assertEqual(self.status_of("P1.1"), "todo")

    def test_failed_job_keeps_partial_while_another_job_runs(self):
        first = jobs.start_job(self.dir, "a", "haiku", task="P1.1")
        jobs.start_job(self.dir, "b", "haiku", task="P1.1")
        jobs.finish_job(self.dir, first["id"], "failed", reason="boom")
        self.assertEqual(self.status_of("P1.1"), "partial")

    def test_done_job_leaves_status_alone(self):
        job = jobs.start_job(self.dir, "work", "haiku", task="P1.1")
        jobs.finish_job(self.dir, job["id"], "done")
        self.assertEqual(self.status_of("P1.1"), "partial")

    def test_other_tasks_untouched(self):
        job = jobs.start_job(self.dir, "work", "haiku", task="P1.1")
        jobs.start_job(self.dir, "other", "haiku", task="P1.2")
        jobs.finish_job(self.dir, job["id"], "failed", reason="boom")
        self.assertEqual(self.status_of("P1.2"), "partial")


if __name__ == "__main__":
    unittest.main()
