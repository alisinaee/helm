"""Git core (GIT-SPEC step 1): validation, runner guards, parsers, redaction and caps. Repos are real temp repos."""

import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, EXIT_EXTERNAL, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import git

IDENT = {"GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "t@example.com",
         "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "t@example.com"}


def _sh(cwd, *args):
    env = dict(os.environ, **IDENT)
    subprocess.run(["git"] + list(args), cwd=cwd, env=env, check=True, capture_output=True)


class ValidationTests(unittest.TestCase):
    def test_valid_refs(self):
        self.assertEqual(git.valid_ref("agent/R7.12"), "agent/R7.12")
        self.assertEqual(git.valid_ref("main"), "main")

    def test_invalid_refs_are_usage_errors(self):
        for bad in ["", "-x", "--force", "a..b", "a//b", "/a", "a/", ".hidden", "a/.b", "x.lock", "a b", "a@{1}",
                    "a" * 101, None]:
            with self.assertRaises(RoadmapError, msg=repr(bad)) as ctx:
                git.valid_ref(bad)
            self.assertEqual(ctx.exception.exit, EXIT_USAGE)

    def test_sha_is_7_to_40_hex(self):
        self.assertEqual(git.valid_sha("1a2b3c4"), "1a2b3c4")
        self.assertEqual(git.valid_sha("A" * 40), "A" * 40)
        for bad in ["1a2b3c", "1a2b3c4d" * 6, "xyz1234", "--stat", ""]:
            with self.assertRaises(RoadmapError):
                git.valid_sha(bad)

    def test_rel_path_rules(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(git.valid_rel_path(root, "a/b.txt"), os.path.join("a", "b.txt"))
        for bad in ["", "/etc/passwd", "../x", "a/../../x", ".", "a\0b"]:
            with self.assertRaises(RoadmapError, msg=repr(bad)):
                git.valid_rel_path(root, bad)

    def test_symlink_inside_project_cannot_point_out(self):
        root = os.path.realpath(tempfile.mkdtemp())
        outside = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        self.addCleanup(shutil.rmtree, outside, True)
        os.symlink(outside, os.path.join(root, "link"))
        with self.assertRaises(RoadmapError) as ctx:
            git.valid_rel_path(root, "link/secret.txt")
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)


class RedactAndCapTests(unittest.TestCase):
    def test_url_credentials_are_hidden(self):
        self.assertEqual(git.redact("https://user:tok123@github.com/a/b.git"), "https://***@github.com/a/b.git")
        self.assertEqual(git.redact("push to https://tok@host/x failed"), "push to https://***@host/x failed")
        self.assertEqual(git.redact("git@github.com:a/b.git"), "git@github.com:a/b.git")

    def test_secret_names(self):
        for name in [".env", ".env.local", "server.pem", "my_key.txt", "id_ed25519", "keyboard.js"]:
            self.assertTrue(git.is_secret_path(name), name)
        self.assertFalse(git.is_secret_path("src/app.py"))

    def test_diff_skip_reasons(self):
        self.assertEqual(git.diff_skip_reason(".env", 10), "hidden (secret pattern)")
        self.assertEqual(git.diff_skip_reason("big.bin", 3 * 1024 * 1024), "binary, 3 MB")
        self.assertEqual(git.diff_skip_reason("img.png", 10, b"\x89PNG\0\0"), "binary, 1 MB")
        self.assertIsNone(git.diff_skip_reason("a.py", 10, b"print(1)\n"))

    def test_cap_text_by_lines_and_bytes(self):
        text, cut = git.cap_text("a\nb\nc", max_bytes=100, max_lines=2)
        self.assertEqual((text, cut), ("a\nb", True))
        text, cut = git.cap_text("x" * 50, max_bytes=10, max_lines=10)
        self.assertEqual((text, cut), ("x" * 10, True))
        self.assertEqual(git.cap_text("ok"), ("ok", False))


class ParserTests(unittest.TestCase):
    def test_parse_status_headers_and_entries(self):
        text = ("# branch.oid abc\0# branch.head main\0# branch.upstream origin/main\0# branch.ab +3 -1\0"
                "1 M. N... 100644 100644 100644 h1 h2 staged.py\0"
                "1 .M N... 100644 100644 100644 h1 h2 changed file.py\0"
                "2 R. N... 100644 100644 100644 h1 h2 R100 new.py\0old.py\0"
                "u UU N... 100644 100644 100644 100644 h1 h2 h3 clash.py\0"
                "? notes.txt\0")
        st = git.parse_status(text)
        self.assertEqual((st["branch"], st["upstream"], st["ahead"], st["behind"]), ("main", "origin/main", 3, 1))
        self.assertFalse(st["detached"])
        self.assertEqual(st["staged"], [{"path": "staged.py", "code": "M."},
                                        {"path": "new.py", "code": "R.", "from": "old.py"}])
        self.assertEqual(st["changed"], [{"path": "changed file.py", "code": ".M"}])
        self.assertEqual(st["conflicts"], ["clash.py"])
        self.assertEqual(st["untracked"], ["notes.txt"])

    def test_parse_status_detached_and_no_upstream(self):
        st = git.parse_status("# branch.oid (initial)\0# branch.head (detached)\0")
        self.assertTrue(st["detached"])
        self.assertIsNone(st["branch"])
        self.assertIsNone(st["upstream"])
        self.assertEqual((st["ahead"], st["behind"]), (0, 0))

    def test_parse_log_task_and_job_trailers(self):
        text = ("\x1eaaa111\x1fAli\x1f1700000000\x1fFirst\x1fFirst\n\nTask: R7.12\nJob: j12\n"
                "\x1ebbb222\x1fAli\x1ftext\x1fPlain\x1fPlain\n")
        rows = git.parse_log(text)
        self.assertEqual(rows[0], {"sha": "aaa111", "author": "Ali", "time": 1700000000, "subject": "First",
                                   "task": "R7.12", "job": "j12"})
        self.assertEqual((rows[1]["time"], rows[1]["task"], rows[1]["job"]), (None, None, None))

    def test_parse_branches(self):
        text = ("main\x1f*\x1forigin/main\x1fahead 2, behind 1\x1f1700000001\n"
                "old\x1f\x1forigin/old\x1fgone\x1f1700000002\n"
                "feat\x1f\x1f\x1f\x1f1700000003\n")
        rows = git.parse_branches(text)
        self.assertEqual((rows[0]["name"], rows[0]["current"], rows[0]["ahead"], rows[0]["behind"]),
                         ("main", True, 2, 1))
        self.assertTrue(rows[1]["gone"])
        self.assertIsNone(rows[2]["upstream"])


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = mock.patch.dict(os.environ, {"ROADMAP_HOME": self.home})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _repo(self):
        _sh(self.root, "init", "-q", "-b", "main")
        with open(os.path.join(self.root, "a.txt"), "w") as fh:
            fh.write("one\n")
        _sh(self.root, "add", "a.txt")
        _sh(self.root, "commit", "-q", "-m", "Init\n\nTask: R7.1\nJob: j3")

    def test_not_a_repo_message_and_hint(self):
        with self.assertRaises(RoadmapError) as ctx:
            git.read_status(self.root)
        self.assertEqual(ctx.exception.message, "Not a git repo")
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertEqual(ctx.exception.next, "git init")

    def test_relative_or_missing_project_is_refused(self):
        with self.assertRaises(RoadmapError):
            git.repo_root("relative/path")
        with self.assertRaises(RoadmapError) as ctx:
            git.repo_root(os.path.join(self.root, "missing"))
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)

    def test_subdirectory_of_a_repo_is_not_the_project(self):
        self._repo()
        sub = os.path.join(self.root, "sub")
        os.mkdir(sub)
        with self.assertRaises(RoadmapError):
            git.repo_root(sub)

    def test_status_log_and_branches_on_real_repo(self):
        self._repo()
        with open(os.path.join(self.root, "b.txt"), "w") as fh:
            fh.write("new\n")
        status = git.read_status(self.root)
        self.assertEqual(status["branch"], "main")
        self.assertIsNone(status["upstream"])
        self.assertIsNone(status["in_progress"])
        self.assertEqual(status["untracked"], ["b.txt"])
        log = git.read_log(self.root, limit=5)
        self.assertEqual(len(log), 1)
        self.assertEqual((log[0]["subject"], log[0]["task"], log[0]["job"]), ("Init", "R7.1", "j3"))
        branches = git.read_branches(self.root)
        self.assertEqual([(b["name"], b["current"]) for b in branches], [("main", True)])

    def test_empty_repo_has_no_log(self):
        _sh(self.root, "init", "-q", "-b", "main")
        self.assertEqual(git.read_log(self.root), [])

    def test_merge_in_progress_is_reported(self):
        self._repo()
        open(os.path.join(self.root, ".git", "MERGE_HEAD"), "w").close()
        self.assertEqual(git.read_status(self.root)["in_progress"], "merge")

    def test_index_lock_answers_busy_and_is_not_deleted(self):
        self._repo()
        lock = os.path.join(self.root, ".git", "index.lock")
        open(lock, "w").close()
        with self.assertRaises(RoadmapError) as ctx:
            git.check_index_free(self.root)
        self.assertEqual((ctx.exception.message, ctx.exception.exit), ("busy, retry", EXIT_CONFLICT))
        self.assertTrue(os.path.exists(lock))

    def test_env_drops_caller_git_variables_and_sets_fixed_ones(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "/nowhere", "GIT_CONFIG_GLOBAL": "/nowhere"}):
            env = git._env(optional_locks=True)
        self.assertNotIn("GIT_DIR", env)
        self.assertNotIn("GIT_CONFIG_GLOBAL", env)
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GIT_PAGER"], "cat")
        self.assertEqual(env["LC_ALL"], "C")
        self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(git._env(optional_locks=False)["GIT_OPTIONAL_LOCKS"], "1")

    def test_timeout_and_big_output_are_errors(self):
        self._repo()
        with mock.patch.object(git.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 5)):
            with self.assertRaises(RoadmapError) as ctx:
                git.run(self.root, ["status"])
        self.assertEqual(ctx.exception.code, "git_timeout")
        fake = subprocess.CompletedProcess(["git"], 0, b"x" * (git.STDOUT_CAP + 1), b"")
        with mock.patch.object(git.subprocess, "run", return_value=fake):
            with self.assertRaises(RoadmapError) as ctx:
                git.run(self.root, ["status"])
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("git_too_big", EXIT_EXTERNAL))

    def test_stderr_is_cut_and_redacted(self):
        secret = "https://user:tok@host/x " + "e" * 600
        fake = subprocess.CompletedProcess(["git"], 1, b"", secret.encode())
        with mock.patch.object(git.subprocess, "run", return_value=fake):
            with self.assertRaises(RoadmapError) as ctx:
                git.run(self.root, ["fetch"])
        self.assertNotIn("tok", ctx.exception.message)
        self.assertIn("https://***@host/x", ctx.exception.message)
        self.assertLessEqual(len(ctx.exception.message), git.STDERR_CUT)

    def test_missing_git_is_external_error(self):
        with mock.patch.object(git, "_GIT", None), mock.patch.object(git.shutil, "which", return_value=None):
            with self.assertRaises(RoadmapError) as ctx:
                git.git_path()
        self.assertEqual(ctx.exception.exit, EXIT_EXTERNAL)


if __name__ == "__main__":
    unittest.main()
