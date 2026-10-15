"""Git write ops (GIT-SPEC step 3): commit, push, branch, switch, revert, their guards and undo.

Every test runs in a temp repo inside a temp ROADMAP_HOME. Nothing touches the network, the real home or the
real projects. CLAUDECODE is cleared so the calls count as the person unless a test says 'agent'.
"""

import json
import os
import subprocess
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import commands, gitops
from roadmap.store import schema
from tests.unit.test_project_support import ProjectCase


class GitOpsCase(ProjectCase):
    def setUp(self):
        super().setUp()
        # macOS temp dirs sit behind a symlink; git.repo_root refuses a non-canonical project path.
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

    def git(self, *args):
        done = subprocess.run(["git"] + list(args), cwd=self.folder, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def write(self, name, text):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def run_op(self, name, args, source="cli"):
        return commands.run(name, args, source, self.data)

    def write_jobs(self, jobs):
        with open(os.path.join(self.data, "jobs.json"), "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 1, "jobs": jobs}, fh)

    def write_policy(self, **doc):
        schema.write_data("git", os.path.join(self.data, gitops.POLICY_FILE), doc)


class CommitTests(GitOpsCase):
    def test_commit_takes_only_the_named_paths(self):
        self.write("a.txt", "a\n")
        self.write("b.txt", "b\n")
        self.git("add", "b.txt")  # staged by someone else: must stay staged
        reply = self.run_op("git.commit", {"paths": ["a.txt"], "message": "Add a", "task": "R7.12", "job": "j9"})
        self.assertTrue(reply["ok"])
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD"), "a.txt")
        self.assertIn("Task: R7.12", self.git("log", "-1", "--format=%B"))
        self.assertIn("Job: j9", self.git("log", "-1", "--format=%B"))
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "b.txt")

    def test_commit_refuses_an_empty_path_list_and_a_missing_message(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.commit", {"paths": [], "message": "x"})
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        self.write("a.txt", "a\n")
        with self.assertRaises(RoadmapError):
            self.run_op("git.commit", {"paths": ["a.txt"], "message": "  "})

    def test_commit_refuses_paths_outside_the_project_and_option_like_paths(self):
        self.write("a.txt", "a\n")
        for bad in ["../x", "/etc/passwd", "-A", "a\nb"]:
            with self.assertRaises(RoadmapError) as ctx:
                self.run_op("git.commit", {"paths": [bad], "message": "x"})
            self.assertEqual(ctx.exception.exit, EXIT_USAGE)

    def test_commit_refuses_a_path_owned_by_another_running_job(self):
        self.write("a.txt", "a\n")
        self.write_jobs([{"id": "j1", "status": "running", "files": ["a.txt"]}])
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.commit", {"paths": ["a.txt"], "message": "x"})
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertIn("j1", ctx.exception.message)
        reply = self.run_op("git.commit", {"paths": ["a.txt"], "message": "x", "job": "j1"})
        self.assertTrue(reply["ok"])

    def test_undo_of_a_commit_is_a_soft_reset_that_keeps_the_files_staged(self):
        before = self.git("rev-parse", "HEAD")
        self.write("a.txt", "a\n")
        done = self.run_op("git.commit", {"paths": ["a.txt"], "message": "Add a"})
        self.assertTrue(done["undo"])
        self.run_op("undo", {"activity": done["activity"]})
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "a.txt")

    def test_detached_head_refuses_commit(self):
        self.git("checkout", "-q", "--detach")
        self.write("a.txt", "a\n")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.commit", {"paths": ["a.txt"], "message": "x"})
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertIn("detached", ctx.exception.message)

    def test_busy_index_lock_refuses_and_is_not_deleted(self):
        self.write("a.txt", "a\n")
        lock_path = os.path.join(self.folder, ".git", "index.lock")
        with open(lock_path, "w", encoding="utf-8") as fh:
            fh.write("")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.commit", {"paths": ["a.txt"], "message": "x"})
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertIn("busy", ctx.exception.message)
        self.assertTrue(os.path.exists(lock_path))
        os.remove(lock_path)


class PushTests(GitOpsCase):
    def setUp(self):
        super().setUp()
        self.remote = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        self.git("remote", "add", "origin", self.remote)
        self.git("push", "-q", "-u", "origin", "main")

    def remote_head(self, branch):
        done = subprocess.run(["git", "--git-dir", self.remote, "rev-parse", "--verify", "-q", branch],
                              capture_output=True, text=True)
        return done.stdout.strip() if done.returncode == 0 else None

    def test_agent_push_is_off_by_default(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.push", {}, source="agent")
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_person_push_reaches_the_remote(self):
        self.write("a.txt", "a\n")
        self.run_op("git.commit", {"paths": ["a.txt"], "message": "Add a"})
        reply = self.run_op("git.push", {})
        self.assertTrue(reply["ok"])
        self.assertEqual(self.remote_head("refs/heads/main"), self.git("rev-parse", "HEAD"))
        self.assertFalse(reply["undo"])

    def test_agent_push_refuses_a_protected_branch_and_allows_a_feature_branch(self):
        self.write_policy(push="task-done", protected=["main", "release/*"])
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.push", {}, source="agent")
        self.assertEqual(ctx.exception.code, "forbidden")
        self.assertIn("protected", ctx.exception.message)
        self.git("checkout", "-q", "-b", "agent/R7.12")
        reply = self.run_op("git.push", {}, source="agent")
        self.assertTrue(reply["ok"])
        self.assertIsNotNone(self.remote_head("refs/heads/agent/R7.12"))

    def test_after_check_push_needs_checked_true(self):
        self.write_policy(push="after-check", protected=["main"])
        self.git("checkout", "-q", "-b", "agent/R7.12")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.push", {}, source="agent")
        self.assertIn("green make check", ctx.exception.message)
        self.assertTrue(self.run_op("git.push", {"checked": True}, source="agent")["ok"])

    def test_push_refuses_a_detached_head(self):
        self.git("checkout", "-q", "--detach")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.push", {})
        self.assertEqual(ctx.exception.code, "conflict")

    def test_a_bad_policy_file_is_refused(self):
        self.write_policy(push="always", protected=["main"])
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.push", {}, source="agent")
        self.assertEqual(ctx.exception.code, "invalid_data")


class BranchTests(GitOpsCase):
    def test_agents_create_only_agent_prefixed_branches(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.branch", {"name": "feat/x"}, source="agent")
        self.assertEqual(ctx.exception.code, "forbidden")
        self.run_op("git.branch", {"name": "agent/R7.12"}, source="agent")
        self.assertIn("agent/R7.12", self.git("branch", "--format=%(refname:short)"))

    def test_a_bad_branch_name_is_refused(self):
        for bad in ["-x", "a..b", "a.lock", "feat/.hidden"]:
            with self.assertRaises(RoadmapError) as ctx:
                self.run_op("git.branch", {"name": bad})
            self.assertEqual(ctx.exception.exit, EXIT_USAGE)

    def test_undo_drops_a_branch_with_no_new_commits(self):
        created = self.run_op("git.branch", {"name": "feat/x"})
        self.run_op("undo", {"activity": created["activity"]})
        self.assertNotIn("feat/x", self.git("branch", "--format=%(refname:short)"))

    def test_undo_refuses_when_the_branch_has_new_commits(self):
        created = self.run_op("git.branch", {"name": "feat/y"})
        self.git("checkout", "-q", "feat/y")
        self.write("a.txt", "a\n")
        self.git("add", "a.txt")
        self.git("commit", "-q", "-m", "more")
        self.git("checkout", "-q", "main")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("undo", {"activity": created["activity"]})
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertIn("feat/y", self.git("branch", "--format=%(refname:short)"))


class SwitchTests(GitOpsCase):
    def setUp(self):
        super().setUp()
        self.git("branch", "feat/x")

    def test_switch_on_a_clean_tree_and_undo_switches_back(self):
        done = self.run_op("git.switch", {"name": "feat/x"})
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "feat/x")
        self.run_op("undo", {"activity": done["activity"]})
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_switch_refuses_an_untracked_file_in_the_project(self):
        self.write("loose.txt", "x\n")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.switch", {"name": "feat/x"})
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_roadmap_data_writes_do_not_block_a_switch(self):
        with open(os.path.join(self.data, "activity.jsonl"), "a", encoding="utf-8") as fh:
            fh.write("{}\n")
        done = self.run_op("git.switch", {"name": "feat/x"})
        self.assertTrue(done["ok"])

    def test_switch_to_a_missing_branch_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.switch", {"name": "nope"})
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)


class RevertTests(GitOpsCase):
    def test_agents_cannot_revert(self):
        self.write("a.txt", "a\n")
        self.run_op("git.commit", {"paths": ["a.txt"], "message": "Add a"})
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("git.revert", {"sha": self.git("rev-parse", "HEAD")}, source="agent")
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "2")

    def test_person_revert_adds_a_commit_and_undo_removes_it(self):
        self.write("a.txt", "a\n")
        self.run_op("git.commit", {"paths": ["a.txt"], "message": "Add a"})
        added = self.git("rev-parse", "HEAD")
        reply = self.run_op("git.revert", {"sha": added})
        self.assertFalse(os.path.exists(os.path.join(self.folder, "a.txt")))
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "3")
        self.run_op("undo", {"activity": reply["activity"]})
        self.assertEqual(self.git("rev-parse", "HEAD"), added)


class RegistryTests(GitOpsCase):
    def test_undo_inverses_are_not_callable_directly(self):
        for name in ("git.uncommit", "git.branch.drop"):
            with self.assertRaises(RoadmapError) as ctx:
                self.run_op(name, {"sha": "abc1234", "name": "x"})
            self.assertEqual(ctx.exception.code, "usage")
