"""R7.72 (HEAD-AGENT-V2 A6): head, job, task and git print at most 15 lines by default; --full lifts the cap. The test
walks those commands through cli.main on a temp copy of the fixture project that holds many tasks, head entries, jobs
and commits, and counts the printed lines (stdout and stderr together)."""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from roadmap.cli import main
from roadmap.services import tasks
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID

MAX_LINES = 15
MANY = 40
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com")


def _run(argv, stdin=""):
    """Run the CLI in-process as a non-TTY shell: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = main(argv + ["--project", PROJECT_ID])
    return code, out.getvalue(), err.getvalue()


def _count(out, err):
    return len(out.splitlines()) + len(err.splitlines())


class CompactCase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="rb-compact-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        self.root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(self.root, "docs"))
        config_store.add_project("split-net", self.root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]
        self._seed_git()
        self._seed_records()

    def _git(self, *args):
        return subprocess.run(["git", "-c", "commit.gpgsign=false"] + list(args), cwd=self.root, check=True,
                              capture_output=True, text=True, env=GIT_ENV).stdout

    def _seed_git(self):
        self._git("init", "-q")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")
        for i in range(MANY):
            self._git("commit", "-q", "--allow-empty", "-m", "commit %d" % i)
        for i in range(30):
            with open(os.path.join(self.root, "bulk%02d.txt" % i), "w", encoding="utf-8") as fh:
                fh.write("x\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "bulk")

    def _seed_records(self):
        for i in range(MANY):
            code, _, err = _run(["head", "log", "ask number %d" % i, "--kind", "ask"])
            self.assertEqual(code, 0, err)
        for i in range(MANY):
            code, _, err = _run(["job", "start", "job %d" % i, "opus"])
            self.assertEqual(code, 0, err)
        self.task_ids = []
        for i in range(MANY):
            code, out, err = _run(["task", "add", "compact item %d" % i])
            self.assertEqual(code, 0, err)
            self.task_ids.append(re.match(r"^ok (\S+) ", out).group(1))

    def test_every_walked_command_stays_within_fifteen_lines(self):
        ids = self.task_ids
        walk = [
            ["head", "list"], ["head", "list", "--all"], ["head", "list", "--n", "50"], ["head", "show", "H1"],
            ["head", "brief"], ["head", "brief", "--md"], ["head", "brief", "--done"], ["head", "triage"],
            ["head", "review"], ["head", "claim", "--model", "Opus 5.5"],
            ["job", "list"], ["job", "prune"],
            ["task", "list"], ["task", "list", "--limit", "50"], ["task", "show", ids[0]],
            ["task", "hold"] + ids, ["task", "set", "-", "--dry-run"],
            ["git", "log"], ["git", "log", "-n", "40"], ["git", "status"], ["git", "branches"],
            ["git", "show", self._git("rev-parse", "HEAD").strip()],
        ]
        stdin = "\n".join("%s status=todo" % tid for tid in ids) + "\n"
        for argv in walk:
            with self.subTest(argv=" ".join(argv[:3])):
                code, out, err = _run(argv, stdin=stdin)
                self.assertEqual(code, 0, err)
                self.assertLessEqual(_count(out, err), MAX_LINES)

    def test_full_lifts_the_cap(self):
        _, out, _ = _run(["head", "list", "--full"])
        self.assertGreater(len(out.splitlines()), MAX_LINES)
        _, out, _ = _run(["git", "log", "-n", "40", "--full"])
        self.assertEqual(len(out.splitlines()), 40)
        _, out, _ = _run(["task", "list", "--limit", "50", "--full"])
        self.assertGreater(len(out.splitlines()), MAX_LINES)

    def test_capped_output_says_how_to_see_more(self):
        _, out, _ = _run(["git", "log", "-n", "40"])
        self.assertIn("+26 more (--full)", out.splitlines()[-1])

    def test_invalid_plan_is_one_line_then_next(self):
        bad = "\n".join("NOPE%d status=bogus" % i for i in range(8)) + "\n"
        code, out, err = _run(["task", "set", "-", "--dry-run"], stdin=bad)
        self.assertEqual(code, 5)
        lines = err.splitlines()
        self.assertEqual(len(lines), 2, err)
        self.assertTrue(lines[-1].startswith("next: "))

    def test_json_envelope_is_not_capped(self):
        code, out, _ = _run(["head", "list", "--json", "--n", "30"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["data"]["entries"]), 30)


if __name__ == "__main__":
    unittest.main()
