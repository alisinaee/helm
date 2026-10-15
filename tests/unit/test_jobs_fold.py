"""H2 (R7.84): a job that ends done marks its task verify (work finished, needs a check) and keeps the status. A commit
that binds the task makes it done, clears verify, and closes the asks whose tasks are all done.

Every test runs in a temp git repo inside a temp ROADMAP_HOME. Nothing touches the real home or the network.
"""

import json
import os
import subprocess
import unittest
from unittest import mock

from roadmap.services import gitops, head as head_svc, jobs
from roadmap.store import schema
from tests.unit.test_project_support import ProjectCase


class FoldCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.folder = os.path.realpath(self.folder)
        self.data = os.path.join(self.folder, "docs")
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)
        self.init_and_add()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test Person")
        self.git("config", "user.email", "test@example.invalid")
        self.commit_file("README.md", "Init")
        self.set_tasks({"R7.44": "todo", "R7.45": "todo"})

    def git(self, *args):
        done = subprocess.run(["git"] + list(args), cwd=self.folder, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def commit_file(self, name, message):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as fh:
            fh.write(name + "\n")
        self.git("add", "--", name)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def set_tasks(self, statuses):
        tasks = [{"id": tid, "phase": "R7", "title": "task " + tid, "status": st, "tokensK": 0, "model": "haiku",
                  "thinking": "medium"} for tid, st in statuses.items()]
        schema.write_data("tasks", os.path.join(self.data, "tasks.json"), {"phases": [], "tasks": tasks})

    def task(self, tid):
        return next(t for t in jobs.task_records(self.data) if t["id"] == tid)

    def ask(self, text, task_ids):
        rec = head_svc.capture(self.data, text, src="cli", kind="ask")
        head_svc.update(self.data, rec["id"], by="person", links=["+task:" + t for t in task_ids])
        return rec["id"]

    def row(self, eid):
        return next(r for r in head_svc.rows(self.data) if r["id"] == eid)


class VerifyFlagTests(FoldCase):
    def test_done_job_sets_verify_and_keeps_partial(self):
        job = jobs.start_job(self.data, "fix", "haiku", task="R7.44")
        jobs.finish_job(self.data, job["id"], "done")
        task = self.task("R7.44")
        self.assertEqual(task["status"], "partial")
        self.assertIs(task.get("verify"), True)

    def test_done_job_with_another_running_job_sets_nothing(self):
        first = jobs.start_job(self.data, "fix", "haiku", task="R7.44")
        jobs.start_job(self.data, "more", "haiku", task="R7.44")
        jobs.finish_job(self.data, first["id"], "done")
        self.assertNotIn("verify", self.task("R7.44"))

    def test_failed_job_sets_no_verify(self):
        job = jobs.start_job(self.data, "fix", "haiku", task="R7.44")
        jobs.finish_job(self.data, job["id"], "failed", reason="boom")
        self.assertNotIn("verify", self.task("R7.44"))
        self.assertEqual(self.task("R7.44")["status"], "todo")


class CommitDoneTests(FoldCase):
    def test_bound_commit_marks_done_and_clears_verify(self):
        job = jobs.start_job(self.data, "fix", "haiku", task="R7.44")
        jobs.finish_job(self.data, job["id"], "done")
        sha = self.commit_file("a.txt", "R7.44 add a")
        self.assertEqual(gitops.bind_message_commit(self.data, sha, "R7.44 add a"), ["R7.44"])
        task = self.task("R7.44")
        self.assertEqual(task["status"], "done")
        self.assertNotIn("verify", task)
        self.assertEqual(task["refs"], ["commit:" + sha])

    def test_binding_same_commit_twice_changes_nothing(self):
        sha = self.commit_file("a.txt", "R7.44 once")
        jobs.bind_commit(self.data, sha, ["R7.44"])
        before = self.task("R7.44")
        jobs.bind_commit(self.data, sha, ["R7.44"])
        self.assertEqual(self.task("R7.44"), before)

    def test_commit_closes_ask_whose_tasks_are_all_done(self):
        eid = self.ask("ship the export", ["R7.44", "R7.45"])
        sha1 = self.commit_file("b.txt", "R7.44 first")
        gitops.bind_message_commit(self.data, sha1, "R7.44 first")
        self.assertNotEqual(self.row(eid)["status"], "done")
        sha2 = self.commit_file("c.txt", "R7.45 second")
        gitops.bind_message_commit(self.data, sha2, "R7.45 second")
        self.assertEqual(self.row(eid)["status"], "done")
        with open(os.path.join(self.data, "head.jsonl"), encoding="utf-8") as fh:
            notes = [json.loads(line).get("note") for line in fh if '"note"' in line and eid in line]
        self.assertIn("auto: R7.44 " + sha1[:7] + ", R7.45 " + sha2[:7], notes)


if __name__ == "__main__":
    unittest.main()
