"""Event-driven status (A2): a job start moves its todo task to partial, a commit naming task ids binds commit:<sha> to
those tasks and their running jobs, and an ask closes (auto) once every task bound to it is done.

Every test runs in a temp git repo inside a temp ROADMAP_HOME. Nothing touches the real home or the network.
"""

import json
import os
import subprocess
import unittest
from unittest import mock

from roadmap.services import commands, gitops, hooks, head as head_svc, jobs
from roadmap.store import schema
from tests.unit.test_project_support import ProjectCase


class EventCase(ProjectCase):
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
        self.write("README.md", "hello\n")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "Init")
        self.set_tasks({"R7.44": "todo", "R7.45": "todo", "R7.46": "doing"})

    def git(self, *args):
        done = subprocess.run(["git"] + list(args), cwd=self.folder, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def set_tasks(self, statuses):
        tasks = [{"id": tid, "phase": "R7", "title": "task " + tid, "status": st, "tokensK": 0, "model": "haiku",
                  "thinking": "medium"} for tid, st in statuses.items()]
        schema.write_data("tasks", os.path.join(self.data, "tasks.json"), {"phases": [], "tasks": tasks})

    def task(self, tid):
        return next(t for t in jobs.task_records(self.data) if t["id"] == tid)

    def set_status(self, tid, status):
        tasks = jobs.task_records(self.data)
        for t in tasks:
            if t["id"] == tid:
                t["status"] = status
        schema.write_data("tasks", os.path.join(self.data, "tasks.json"), {"phases": [], "tasks": tasks})

    def commit_file(self, name, message):
        self.write(name, name + "\n")
        self.git("add", "--", name)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def ask(self, text, task_ids):
        rec = head_svc.capture(self.data, text, src="cli", kind="ask")
        head_svc.update(self.data, rec["id"], by="person", links=["+task:" + t for t in task_ids])
        return rec["id"]

    def head_records(self):
        with open(os.path.join(self.data, "head.jsonl"), encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def row(self, eid):
        return next(r for r in head_svc.rows(self.data) if r["id"] == eid)


class StartMarksPartialTests(EventCase):
    def test_start_on_a_todo_task_makes_it_partial(self):
        jobs.start_job(self.data, "work", "haiku", task="R7.44")
        self.assertEqual(self.task("R7.44")["status"], "partial")

    def test_start_leaves_a_doing_task_alone(self):
        jobs.start_job(self.data, "work", "haiku", task="R7.46")
        self.assertEqual(self.task("R7.46")["status"], "doing")

    def test_start_without_task_changes_nothing(self):
        jobs.start_job(self.data, "work", "haiku")
        self.assertEqual(self.task("R7.44")["status"], "todo")


class CommitBindingTests(EventCase):
    def test_commit_message_binds_sha_to_task_and_running_job(self):
        job = jobs.start_job(self.data, "fix export", "haiku", task="R7.44")
        sha = self.commit_file("a.txt", "R7.44 fix export")
        self.assertEqual(jobs.bind_commit(self.data, sha, ["R7.44"]), ["R7.44"])
        self.assertIn("commit:" + sha, self.task("R7.44")["refs"])
        running = next(j for j in jobs.list_jobs(self.data) if j["id"] == job["id"])
        self.assertIn("commit:" + sha, running["refs"])

    def test_binding_the_same_commit_twice_adds_it_once(self):
        sha = self.commit_file("a.txt", "R7.44 once")
        jobs.bind_commit(self.data, sha, ["R7.44"])
        jobs.bind_commit(self.data, sha, ["R7.44"])
        self.assertEqual(self.task("R7.44")["refs"], ["commit:" + sha])

    def test_unknown_task_ids_bind_nothing(self):
        sha = self.commit_file("a.txt", "R9.9 nothing known")
        self.assertEqual(jobs.bind_commit(self.data, sha, ["R9.9"]), [])
        self.assertNotIn("refs", self.task("R7.44"))

    def test_commit_op_reports_done_candidate_and_keeps_status(self):
        self.write("b.txt", "b\n")
        message = "R7.45 add export"
        out = commands.run("git.commit", {"paths": ["b.txt"], "message": message}, "cli", self.data)
        sha = self.git("rev-parse", "HEAD")
        self.assertEqual(out["data"]["candidates"], ["R7.45"])
        self.assertIn("commit:" + sha, self.task("R7.45")["refs"])
        self.assertEqual(self.task("R7.45")["status"], "done")

    def test_bind_message_commit_reads_ids_from_the_message(self):
        sha = self.commit_file("c.txt", "R7.44 and R7.45 together")
        bound = gitops.bind_message_commit(self.data, sha, "R7.44 and R7.45 together")
        self.assertEqual(bound, ["R7.44", "R7.45"])


class HookCommitTests(EventCase):
    def fire_bash(self, command):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": self.folder,
                   "session_id": "sess-1", "tool_input": {"command": command}, "tool_response": {"stdout": ""}}
        return hooks.run_hook(json.dumps(payload))

    def test_bash_git_commit_binds_the_new_head(self):
        jobs.start_job(self.data, "fix", "haiku", task="R7.44")
        sha = self.commit_file("d.txt", "R7.44 from the hook")
        self.fire_bash("git commit -m 'R7.44 from the hook'")
        self.assertIn("commit:" + sha, self.task("R7.44")["refs"])

    def test_bash_that_is_not_a_commit_binds_nothing(self):
        sha = self.commit_file("e.txt", "R7.44 not via hook")
        self.fire_bash("git status")
        self.assertNotIn("refs", self.task("R7.44"))
        self.assertNotIn(sha, json.dumps(jobs.task_records(self.data)))


class AskFoldTests(EventCase):
    def test_ask_closes_with_real_shas_when_all_its_tasks_are_done(self):
        sha1 = self.commit_file("f.txt", "R7.44 first")
        sha2 = self.commit_file("g.txt", "R7.45 second")
        eid = self.ask("please export and import", ["R7.44", "R7.45"])
        jobs.bind_commit(self.data, sha1, ["R7.44"])
        jobs.bind_commit(self.data, sha2, ["R7.45"])
        self.set_status("R7.44", "done")
        self.set_status("R7.45", "done")
        self.assertEqual(head_svc.fold_asks(self.data), [eid])
        self.assertEqual(self.row(eid)["status"], "done")
        notes = [r.get("note") for r in self.head_records() if r.get("t") == "u" and r.get("id") == eid and r.get("note")]
        self.assertEqual(notes, ["auto: R7.44 " + sha1[:7] + ", R7.45 " + sha2[:7]])
        self.assertEqual(head_svc.fold_asks(self.data), [])

    def test_ask_with_an_unfinished_task_stays_open(self):
        eid = self.ask("keep the export open", ["R7.44", "R7.46"])
        self.set_status("R7.44", "done")
        self.assertEqual(head_svc.fold_asks(self.data), [])
        self.assertNotEqual(self.row(eid)["status"], "done")


if __name__ == "__main__":
    unittest.main()
