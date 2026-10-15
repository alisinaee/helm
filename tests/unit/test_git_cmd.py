"""Command group git (GIT-SPEC step 5) and the job done commit link.

Every test runs in a temp git repo inside a temp ROADMAP_HOME. Nothing touches the network, the real home or the
real projects. CLAUDECODE is cleared so the calls count as the person unless a test sets it for an agent.
"""

import json
import os
import shutil
import subprocess
import unittest
from unittest import mock

from tests.unit.test_project_support import ProjectCase, run_cli


class GitCmdCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.folder = os.path.realpath(self.folder)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)
        self.project = self.init_and_add()
        self.pid = self.project["id"]
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test Person")
        self.git("config", "user.email", "test@example.invalid")
        self.write("README.md", "hello\n")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "Init")

    def git(self, *args):
        done = subprocess.run(["git"] + list(args), cwd=self.folder, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def head(self):
        return self.git("rev-parse", "HEAD")

    def cli(self, *argv):
        """Run a git command in json mode as the person and return (exit code, data or error)."""
        code, out, _ = run_cli(["git"] + list(argv) + ["--project", self.pid, "--json"])
        envelope = json.loads(out)
        return code, envelope.get("data") if envelope.get("ok") else envelope.get("error")

    def cli_text(self, *argv):
        code, out, err = run_cli(["git"] + list(argv) + ["--project", self.pid])
        return code, out, err


class StatusLogTest(GitCmdCase):
    def test_status_reports_branch_and_counts(self):
        self.write("new.txt", "x\n")
        code, data = self.cli("status")
        self.assertEqual(code, 0)
        self.assertEqual(data["branch"], "main")
        self.assertFalse(data["detached"])
        self.assertGreaterEqual(data["untracked"], 1)
        self.assertTrue(any(row["path"] == "new.txt" and row["owner"] == "unattributed" for row in data["files"]))

    def test_status_text_is_short(self):
        self.write("new.txt", "x\n")
        code, out, _ = self.cli_text("status")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertLessEqual(len(lines), 8)
        self.assertEqual(lines[0], "main")

    def test_not_a_repo_says_so(self):
        shutil.rmtree(os.path.join(self.folder, ".git"))
        code, data = self.cli("status")
        self.assertNotEqual(code, 0)
        self.assertEqual(data["message"], "Not a git repo")
        self.assertEqual(data["next"], "git init")

    def test_log_shows_trailer_links_and_filters(self):
        self.write("a.txt", "a\n")
        code, _ = self.cli("commit", "a.txt", "-m", "Add a", "--task", "R7.29", "--job", "j3")
        self.assertEqual(code, 0)
        code, data = self.cli("log", "--task", "R7.29")
        self.assertEqual(code, 0)
        self.assertEqual(len(data["commits"]), 1)
        self.assertEqual(data["commits"][0]["job"], "j3")
        code, data = self.cli("log", "--job", "j9")
        self.assertEqual(data["commits"], [])

    def test_log_rejects_zero_count(self):
        code, data = self.cli("log", "-n", "0")
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "usage")


class CommitBranchPushTest(GitCmdCase):
    def test_commit_takes_only_the_named_path(self):
        self.write("a.txt", "a\n")
        self.write("b.txt", "b\n")
        code, data = self.cli("commit", "a.txt", "-m", "Add a")
        self.assertEqual(code, 0)
        self.assertEqual(data["files"], 1)
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["a.txt"])
        self.assertIn("b.txt", self.git("status", "--porcelain"))

    def test_commit_refuses_path_outside_project(self):
        code, data = self.cli("commit", "../outside.txt", "-m", "Nope")
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "usage")

    def test_commit_writes_trailers(self):
        self.write("a.txt", "a\n")
        self.cli("commit", "a.txt", "-m", "Add a", "--task", "R7.29", "--job", "j5")
        body = self.git("log", "-1", "--format=%B")
        self.assertIn("Task: R7.29", body)
        self.assertIn("Job: j5", body)

    def test_branch_new_and_switch_as_person(self):
        code, _ = self.cli("branch", "new", "feature-x")
        self.assertEqual(code, 0)
        code, out, _ = self.cli_text("branches")
        self.assertIn("feature-x", out)
        code, _ = self.cli("branch", "switch", "feature-x")
        self.assertEqual(code, 0)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "feature-x")

    def test_agent_may_only_create_agent_branches(self):
        os.environ["CLAUDECODE"] = "1"
        self.addCleanup(os.environ.pop, "CLAUDECODE", None)
        code, data = self.cli("branch", "new", "feature-y")
        self.assertNotEqual(code, 0)
        code, _ = self.cli("branch", "new", "agent/w1")
        self.assertEqual(code, 0)

    def test_branch_switch_needs_a_name(self):
        code, data = self.cli("branch", "switch")
        self.assertNotEqual(code, 0)
        self.assertEqual(data["code"], "usage")

    def test_push_is_refused_by_default_policy(self):
        code, data = self.cli("push")
        self.assertNotEqual(code, 0)
        self.assertTrue(data["message"])

    def test_show_lists_the_files_of_a_commit(self):
        self.write("a.txt", "a\n")
        self.cli("commit", "a.txt", "-m", "Add a")
        sha = self.head()
        code, out, _ = self.cli_text("show", sha[:7], "--stat")
        self.assertEqual(code, 0)
        self.assertIn("a.txt", out)

    def test_show_rejects_a_non_hex_id(self):
        code, data = self.cli("show", "--", "HEAD")
        self.assertNotEqual(code, 0)


class JobDoneLinkTest(GitCmdCase):
    def test_job_done_lists_commits_with_its_job_trailer(self):
        code, job = self.cli_job("start", "Add a", "haiku")
        self.assertEqual(code, 0)
        job_id = job["id"]
        self.write("a.txt", "a\n")
        self.cli("commit", "a.txt", "-m", "Add a", "--job", job_id)
        code, out, _ = run_cli(["job", "done", job_id, "--project", self.pid, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)["data"]
        self.assertEqual(len(data["commits"]), 1)
        self.assertEqual(data["commits"][0], self.head())

    def test_job_done_without_a_git_repo_still_finishes(self):
        shutil.rmtree(os.path.join(self.folder, ".git"))
        code, job = self.cli_job("start", "No repo", "haiku")
        code, out, _ = run_cli(["job", "done", job["id"], "--project", self.pid, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["commits"], [])

    def cli_job(self, *argv):
        code, out, _ = run_cli(["job"] + list(argv) + ["--project", self.pid, "--json"])
        return code, json.loads(out)["data"]


if __name__ == "__main__":
    unittest.main()
