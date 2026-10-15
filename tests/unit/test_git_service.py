"""Git core (GIT-SPEC step 1): validation, runner guards, parsers, redaction and caps. Repos are real temp repos."""

import io
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, EXIT_EXTERNAL, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import git

IDENT = {"GIT_AUTHOR_NAME": "Tester", "GIT_AUTHOR_EMAIL": "t@example.com",
         "GIT_COMMITTER_NAME": "Tester", "GIT_COMMITTER_EMAIL": "t@example.com"}


def _sh(cwd, *args):
    env = dict(os.environ, **IDENT)
    subprocess.run(["git"] + list(args), cwd=cwd, env=env, check=True, capture_output=True)


def _fake_git(test, body):
    """Point the runner at a shell script that runs body instead of git. Returns the patch to use in a with."""
    folder = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, folder, True)
    path = os.path.join(folder, "git")
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, 0o755)
    return mock.patch.object(git, "_GIT", path)


class _Pipe(io.BytesIO):
    """A BytesIO that stays open after the runner closes it, so the test can read how far it was consumed."""

    def close(self):
        pass


class ValidationTests(unittest.TestCase):
    def test_valid_refs(self):
        self.assertEqual(git.valid_ref("agent/R7.12"), "agent/R7.12")
        self.assertEqual(git.valid_ref("main"), "main")

    def test_invalid_refs_are_usage_errors(self):
        for bad in ["", "-x", "--force", "a..b", "a//b", "/a", "a/", ".hidden", "a/.b", "x.lock", "a b", "a@{1}",
                    "a" * 101, None, "main\n"]:
            with self.assertRaises(RoadmapError, msg=repr(bad)) as ctx:
                git.valid_ref(bad)
            self.assertEqual(ctx.exception.exit, EXIT_USAGE)

    def test_sha_is_7_to_40_hex(self):
        self.assertEqual(git.valid_sha("1a2b3c4"), "1a2b3c4")
        self.assertEqual(git.valid_sha("A" * 40), "A" * 40)
        for bad in ["1a2b3c", "1a2b3c4d" * 6, "xyz1234", "--stat", "", "1a2b3c4\n"]:
            with self.assertRaises(RoadmapError):
                git.valid_sha(bad)

    def test_rel_path_rules(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(git.valid_rel_path(root, "a/b.txt"), os.path.join("a", "b.txt"))
        for bad in ["", "/etc/passwd", "../x", "a/../../x", ".", "a\0b", "-rf", "--config=x", "a\nb", "a\rb"]:
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

    def test_any_scheme_and_case_is_hidden(self):
        self.assertEqual(git.redact("ssh://git:tok@host/a"), "ssh://***@host/a")
        self.assertEqual(git.redact("HTTPS://user:tok@host/a"), "HTTPS://***@host/a")
        self.assertEqual(git.redact("https://user@name:secret@host/a"), "https://***@host/a")

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

    def test_short_porcelain_records_are_skipped_not_crashed(self):
        st = git.parse_status("# branch.head main\0# branch.ab +1\0# branch.ab x y\0"
                              "1 M.\0u UU\0? notes.txt\0" "2 R.\0")
        self.assertEqual(st["branch"], "main")
        self.assertEqual((st["ahead"], st["behind"]), (0, 0))
        self.assertEqual((st["staged"], st["changed"], st["conflicts"]), ([], [], []))
        self.assertEqual(st["untracked"], ["notes.txt"])

    def test_parse_log_task_and_job_trailers(self):
        text = ("aaa111\x00Ali\x001700000000\x00First\0First\n\nTask: R7.12\nJob: j12\0\n"
                "bbb222\x00Ali\x00text\0Plain\0Plain\0\n")
        rows = git.parse_log(text)
        self.assertEqual(rows[0], {"sha": "aaa111", "author": "Ali", "time": 1700000000, "subject": "First",
                                   "task": "R7.12", "job": "j12"})
        self.assertEqual((rows[1]["time"], rows[1]["task"], rows[1]["job"]), (None, None, None))

    def test_parse_log_redacts_author_and_subject(self):
        rows = git.parse_log("aaa111\x00Ali\x001\x00see https://u:tok@host/a\0body\0\n")
        self.assertEqual(rows[0]["subject"], "see https://***@host/a")

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

    def test_env_drops_every_git_variable_and_sets_fixed_ones(self):
        leaked = {"GIT_DIR": "/nowhere", "GIT_CONFIG_GLOBAL": "/nowhere", "GIT_SSH_COMMAND": "evil",
                  "GIT_SSH": "evil", "GIT_EXTERNAL_DIFF": "evil", "GIT_EXEC_PATH": "/x", "GIT_PROXY_COMMAND": "evil",
                  "GIT_ASKPASS": "evil", "SSH_ASKPASS": "evil", "GIT_TRACE": "/x", "GIT_TRACE_PACKET": "/x",
                  "GIT_CURL_VERBOSE": "1", "GIT_TRACE2_EVENT": "/x"}
        with mock.patch.dict(os.environ, leaked):
            env = git._env(optional_locks=True)
        for name in leaked:
            self.assertNotIn(name, env)
        self.assertEqual(env["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GIT_PAGER"], "cat")
        self.assertEqual(env["LC_ALL"], "C")
        self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(git._env(optional_locks=False)["GIT_OPTIONAL_LOCKS"], "1")

    def test_reads_pass_fsmonitor_and_credential_flags_first(self):
        seen = os.path.join(self.home, "argv.txt")
        with _fake_git(self, "printf '%s\\n' \"$@\" > '" + seen + "'"):
            git.run(self.root, ["status"])
        with open(seen) as fh:
            argv = fh.read().splitlines()
        self.assertEqual(argv, ["-c", "core.fsmonitor=false", "-c", "credential.helper=", "status"])

    def test_status_never_runs_a_configured_fsmonitor_hook(self):
        self._repo()
        marker = os.path.join(self.home, "marker")
        hook = os.path.join(self.home, "hook.sh")
        with open(hook, "w") as fh:
            fh.write("#!/bin/sh\ntouch '%s'\n" % marker)
        os.chmod(hook, 0o755)
        _sh(self.root, "config", "core.fsmonitor", hook)
        git.read_status(self.root)
        self.assertFalse(os.path.exists(marker))

    def test_a_commit_message_cannot_forge_a_log_row(self):
        self._repo()
        _sh(self.root, "commit", "-q", "--allow-empty", "-m",
            "Subject\n\nBody\x1e1111111\x1fEvil\x1fEvil\x1fEvil\nTask: R9.99\n")
        log = git.read_log(self.root, limit=5)
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["subject"], "Subject")
        self.assertEqual(log[0]["task"], "R9.99")
        self.assertNotIn("1111111", [row["sha"] for row in log])

    def test_commit_subject_secret_is_redacted(self):
        self._repo()
        _sh(self.root, "commit", "-q", "--allow-empty", "-m", "push https://user:tok@host/a")
        log = git.read_log(self.root, limit=1)
        self.assertEqual(log[0]["subject"], "push https://***@host/a")
        self.assertNotIn("tok", log[0]["subject"])

    def test_read_log_limit_must_be_a_number(self):
        self._repo()
        with self.assertRaises(RoadmapError) as ctx:
            git.read_log(self.root, limit="x")
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("usage", EXIT_USAGE))

    def test_missing_git_is_external_error(self):
        with mock.patch.object(git, "_GIT", None), mock.patch.object(git.shutil, "which", return_value=None):
            with self.assertRaises(RoadmapError) as ctx:
                git.git_path()
        self.assertEqual(ctx.exception.exit, EXIT_EXTERNAL)


class CappedRunnerTests(unittest.TestCase):
    """The runner against real pipes: a fake git script for timeouts and output caps, a real repo for read_log."""

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_timeout_kills_git_and_is_an_error(self):
        with _fake_git(self, "sleep 30"):
            started = time.monotonic()
            with self.assertRaises(RoadmapError) as ctx:
                git.run(self.root, ["status"], timeout=1)
        self.assertEqual(ctx.exception.code, "git_timeout")
        self.assertLess(time.monotonic() - started, 10)

    def test_stdout_past_the_cap_is_an_error_and_the_child_stops(self):
        with _fake_git(self, "head -c %d /dev/zero" % (git.STDOUT_CAP * 3)):
            started = time.monotonic()
            with self.assertRaises(RoadmapError) as ctx:
                git.run(self.root, ["status"])
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("git_too_big", EXIT_EXTERNAL))
        self.assertLess(time.monotonic() - started, 10)

    def test_pump_stops_reading_at_the_cap(self):
        stream = _Pipe(b"x" * (10 * 1024 * 1024))
        calls = []
        kept, over = git._pump(stream, 10, on_over=lambda: calls.append(1))
        self.assertEqual((kept, over, calls), (b"x" * 10, True, [1]))
        self.assertLess(stream.tell(), 10 * 1024 * 1024)

    def test_pump_without_a_cap_callback_drains_the_rest(self):
        stream = _Pipe(b"y" * 300000)
        kept, over = git._pump(stream, 10)
        self.assertEqual((kept, over), (b"y" * 10, True))
        self.assertEqual(stream.tell(), 300000)

    def test_read_log_refuses_output_over_the_cap(self):
        _sh(self.root, "init", "-q", "-b", "main")
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        message = os.path.join(folder, "msg.txt")
        with open(message, "w") as fh:
            fh.write("x" * (git.STDOUT_CAP + 1000) + "\n")
        with open(os.path.join(self.root, "a.txt"), "w") as fh:
            fh.write("one\n")
        _sh(self.root, "add", "a.txt")
        _sh(self.root, "commit", "-q", "-F", message)
        with self.assertRaises(RoadmapError) as ctx:
            git.read_log(self.root)
        self.assertEqual(ctx.exception.code, "git_too_big")

    def test_stderr_is_cut_and_redacted(self):
        secret = "https://user:tok@host/x " + "e" * 600
        with _fake_git(self, "printf '%s' '" + secret + "' >&2; exit 1"):
            with self.assertRaises(RoadmapError) as ctx:
                git.run(self.root, ["fetch"])
        self.assertNotIn("tok", ctx.exception.message)
        self.assertIn("https://***@host/x", ctx.exception.message)
        self.assertLessEqual(len(ctx.exception.message), git.STDERR_CUT)

    def test_stderr_secret_past_the_cut_is_gone(self):
        secret = "e" * 500 + " https://user:tok@host/x"
        with _fake_git(self, "printf '%s' '" + secret + "' >&2; exit 1"):
            with self.assertRaises(RoadmapError) as ctx:
                git.run(self.root, ["fetch"])
        self.assertNotIn("tok", ctx.exception.message)
        self.assertLessEqual(len(ctx.exception.message), git.STDERR_CUT)

    def test_run_failure_with_empty_stderr_has_fallback_message(self):
        with _fake_git(self, "exit 1"):
            with self.assertRaises(RoadmapError) as ctx:
                git.run(self.root, ["status"])
        self.assertEqual((ctx.exception.code, ctx.exception.message, ctx.exception.exit),
                         ("git_failed", "git failed", EXIT_EXTERNAL))


class GapTests(unittest.TestCase):
    """Verified gaps from docs/reviews/agy-git-testgaps.md (23 cases)."""

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = mock.patch.dict(os.environ, {"ROADMAP_HOME": self.home})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _commits(self, count):
        _sh(self.root, "init", "-q", "-b", "main")
        for i in range(count):
            with open(os.path.join(self.root, "a.txt"), "w") as fh:
                fh.write("%d\n" % i)
            _sh(self.root, "add", "a.txt")
            _sh(self.root, "commit", "-q", "-m", "C%d" % i)

    def test_git_path_returns_cached_binary_without_which(self):
        with mock.patch.object(git, "_GIT", "/cached/git"), mock.patch.object(git.shutil, "which") as which:
            self.assertEqual(git.git_path(), "/cached/git")
        which.assert_not_called()

    def test_redact_none_is_empty(self):
        self.assertEqual(git.redact(None), "")

    def test_redact_http_credentials(self):
        self.assertEqual(git.redact("http://user:pass@host/repo"), "http://***@host/repo")

    def test_valid_ref_rejects_trailing_period(self):
        with self.assertRaises(RoadmapError) as ctx:
            git.valid_ref("feat.")
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)

    def test_valid_sha_none_is_usage_error(self):
        with self.assertRaises(RoadmapError) as ctx:
            git.valid_sha(None)
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)

    def test_valid_sha_accepts_mixed_case(self):
        self.assertEqual(git.valid_sha("1a2B3c4D"), "1a2B3c4D")

    def test_valid_rel_path_none_is_usage_error(self):
        with self.assertRaises(RoadmapError) as ctx:
            git.valid_rel_path(self.root, None)
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)

    def test_env_drops_work_tree_and_index_file(self):
        with mock.patch.dict(os.environ, {"GIT_WORK_TREE": "/x", "GIT_INDEX_FILE": "/y"}):
            env = git._env(optional_locks=True)
        self.assertNotIn("GIT_WORK_TREE", env)
        self.assertNotIn("GIT_INDEX_FILE", env)

    def test_repo_root_refuses_empty_or_none_path(self):
        for bad in ["", None]:
            with self.assertRaises(RoadmapError, msg=repr(bad)) as ctx:
                git.repo_root(bad)
            self.assertEqual((ctx.exception.code, ctx.exception.message), ("usage", "project path must be absolute"))

    def test_repo_root_refuses_symlinked_project_path(self):
        parent = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, parent, True)
        link = os.path.join(parent, "link")
        os.symlink(self.root, link)
        with self.assertRaises(RoadmapError) as ctx:
            git.repo_root(link)
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("git_path", EXIT_USAGE))

    def test_in_progress_reports_rebase_directories(self):
        self._commits(1)
        for name in ("rebase-merge", "rebase-apply"):
            path = os.path.join(self.root, ".git", name)
            os.mkdir(path)
            self.assertEqual(git.in_progress(self.root), "rebase", name)
            os.rmdir(path)
        self.assertIsNone(git.in_progress(self.root))

    def test_check_index_free_returns_none_without_lock(self):
        self._commits(1)
        self.assertIsNone(git.check_index_free(self.root))

    def _log_count_arg(self, limit):
        original = git._git
        with mock.patch.object(git, "_git", side_effect=original) as spy:
            rows = git.read_log(self.root, limit=limit)
        argv = [c.args[1] for c in spy.call_args_list if c.args[1][0] == "log"][0]
        return len(rows), argv[argv.index("-n") + 1]

    def test_read_log_clamps_low_limit_to_one(self):
        self._commits(3)
        self.assertEqual(self._log_count_arg(0), (1, "1"))
        self.assertEqual(self._log_count_arg(-5), (1, "1"))

    def test_read_log_clamps_high_limit_to_log_max(self):
        self._commits(3)
        rows, count = self._log_count_arg(500)
        self.assertEqual((rows, count), (3, str(git.LOG_MAX)))

    def test_parse_branches_non_numeric_time_is_none(self):
        rows = git.parse_branches("feat\x1f\x1f\x1f\x1fnot-a-date\n")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["time"])

    def test_parse_status_duplicate_conflict_listed_once(self):
        line = "u UU N... 100644 100644 100644 100644 h1 h2 h3 clash.py\0"
        st = git.parse_status(line + line)
        self.assertEqual(st["conflicts"], ["clash.py"])

    def test_parse_log_skips_short_records(self):
        text = "aaa111\x00Ali\x001700000000\x00Ok\0Ok\0\nbad\0only\0"
        rows = git.parse_log(text)
        self.assertEqual([r["sha"] for r in rows], ["aaa111"])

    def test_secret_name_in_subdirectory_is_secret(self):
        self.assertTrue(git.is_secret_path("sub/dir/.env"))

    def test_nul_after_first_8000_bytes_is_not_binary(self):
        data = b"a" * 8000 + b"\0"
        self.assertFalse(git.is_binary(data))
        self.assertIsNone(git.diff_skip_reason("notes.txt", len(data), data))

    def test_secret_name_takes_precedence_over_size(self):
        self.assertEqual(git.diff_skip_reason(".env", 2 * 1024 * 1024), "hidden (secret pattern)")

    def test_cap_text_drops_split_multibyte_character(self):
        # "é" is two bytes (c3 a9); a 2-byte cut leaves a broken sequence that must be dropped.
        self.assertEqual(git.cap_text("aé", max_bytes=2, max_lines=10), ("a", True))


if __name__ == "__main__":
    unittest.main()
