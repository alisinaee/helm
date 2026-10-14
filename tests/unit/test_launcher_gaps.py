"""Gap tests for the opt-in launcher (R7.1 T4): config edge cases, folder and control-character checks, AppleScript
escaping, a damaged or future rate-limit stamp, the real runner's argv and timeout (subprocess.run is mocked, so
nothing ever launches), platform gating and fail-open paths. A fake clock is passed as now."""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

from roadmap.services import launcher, presence
from roadmap.store import paths


class LauncherGapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="launcher-gap-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = os.path.join(self.tmp, "app")
        os.makedirs(self.project)
        self.data_dir = os.path.join(self.project, "docs")
        self.state = os.path.join(self.tmp, "state")
        self.calls = []
        self.config = {"projects": [{"id": "app", "name": "app", "path": self.project, "dataDir": "docs",
                                     "launchOnStart": True}]}
        for patcher in (mock.patch.object(paths, "state_dir", return_value=self.state),
                        mock.patch.object(launcher.config, "load", side_effect=lambda: self.config)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def runner(self, argv):
        self.calls.append(argv)
        return True

    def stamp_path(self):
        return os.path.join(self.state, launcher.FILE)

    def write_stamp(self, text):
        os.makedirs(self.state, exist_ok=True)
        with open(self.stamp_path(), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_moment_without_now_reads_the_wall_clock(self):
        with mock.patch.object(launcher.time, "time", return_value=1234.5):
            self.assertEqual(launcher._moment(None), 1234.5)

    def test_moment_converts_a_numeric_string_and_an_int(self):
        self.assertEqual(launcher._moment("1000"), 1000.0)
        self.assertIsInstance(launcher._moment(1000), float)

    def test_project_for_accepts_a_path_object(self):
        project = self.config["projects"][0]
        self.assertIs(launcher._project_for(pathlib.Path(self.data_dir)), project)

    def test_project_for_skips_non_dict_entries(self):
        valid = self.config["projects"][0]
        self.config["projects"] = ["junk", None, 7, valid]
        self.assertIs(launcher._project_for(self.data_dir), valid)

    def test_project_for_skips_entries_with_a_missing_or_non_string_path(self):
        self.config["projects"] = [{"id": "a", "dataDir": "docs"}, {"id": "b", "path": 123, "dataDir": "docs"}]
        self.assertIsNone(launcher._project_for(self.data_dir))

    def test_project_for_skips_an_empty_path_even_when_it_would_resolve(self):
        self.config["projects"] = [{"id": "a", "path": "", "dataDir": "docs"}]
        self.assertIsNone(launcher._project_for(os.path.abspath("docs")))

    def test_project_for_defaults_data_dir_to_docs(self):
        project = {"id": "app", "path": self.project}
        self.config["projects"] = [project]
        self.assertIs(launcher._project_for(self.data_dir), project)

    def test_project_for_matches_a_custom_data_dir_only(self):
        project = {"id": "app", "path": self.project, "dataDir": "roadmap-data"}
        self.config["projects"] = [project]
        self.assertIs(launcher._project_for(os.path.join(self.project, "roadmap-data")), project)
        self.assertIsNone(launcher._project_for(self.data_dir))

    def test_valid_dir_refuses_non_string_paths(self):
        self.assertFalse(launcher._valid_dir(None))
        self.assertFalse(launcher._valid_dir(123))

    def test_valid_dir_refuses_a_regular_file(self):
        path = os.path.join(self.tmp, "notes.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x")
        self.assertFalse(launcher._valid_dir(path))
        self.assertTrue(launcher._valid_dir(self.project))

    def test_valid_dir_refuses_control_characters(self):
        with mock.patch.object(launcher.os.path, "isdir", return_value=True):
            for bad in ("/x/a\nb", "/x/a\tb", "/x/a\x7fb"):
                with self.subTest(path=bad):
                    self.assertFalse(launcher._valid_dir(bad))
            self.assertTrue(launcher._valid_dir("/x/ab"))

    def test_script_doubles_backslashes_for_applescript(self):
        script = launcher._script("/x/a\\b")
        self.assertIn("'/x/a\\\\b'", script)

    def test_script_has_the_exact_terminal_command(self):
        self.assertEqual(launcher._script("/opt/app"),
                         'tell application "Terminal" to do script "cd /opt/app && claude"')

    def test_a_non_dict_stamp_is_not_recent(self):
        self.write_stamp("[1000]")
        self.assertFalse(launcher._recent(1000))
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))

    def test_a_boolean_stamp_is_not_recent(self):
        self.write_stamp('{"at": true}')
        # read as 1.0 the stamp would be recent at 101; a boolean must not count
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=101))
        self.assertEqual(len(self.calls), 1)

    def test_a_non_numeric_stamp_is_not_recent(self):
        for text in ('{"at": "invalid"}', '{"at": null}'):
            with self.subTest(text=text):
                self.write_stamp(text)
                self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))

    def test_a_future_stamp_is_not_recent(self):
        self.write_stamp('{"at": 2000}')
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))

    def test_a_stamp_exactly_rate_s_old_is_not_recent(self):
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000 + launcher.RATE_S))
        self.assertEqual(len(self.calls), 2)

    def test_a_stamp_at_zero_age_is_recent(self):
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertEqual(len(self.calls), 1)

    def test_an_unreadable_stamp_is_not_recent(self):
        self.write_stamp('{"at": 1000}')
        with mock.patch.object(launcher.atomic, "read_json", side_effect=OSError("io")):
            self.assertFalse(launcher._recent(1001))

    def test_stamp_writes_the_launch_time(self):
        launcher._stamp(1234.0)
        with open(self.stamp_path(), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"at": 1234.0})

    def test_stamp_failure_does_not_raise(self):
        with mock.patch.object(launcher.atomic, "write_json", side_effect=PermissionError("denied")):
            self.assertIsNone(launcher._stamp(1.0))

    def test_run_passes_argv_with_a_bounded_timeout(self):
        argv = ["osascript", "-e", "x"]
        with mock.patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess(argv, 0)) as run:
            self.assertTrue(launcher._run(argv))
        run.assert_called_once_with(argv, check=False, timeout=launcher.TIMEOUT_S, capture_output=True)

    def test_run_reports_a_non_zero_exit_as_false(self):
        argv = ["osascript", "-e", "x"]
        with mock.patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess(argv, 1)):
            self.assertFalse(launcher._run(argv))

    def test_a_timed_out_runner_fails_open_through_maybe_launch(self):
        timeout = subprocess.TimeoutExpired(cmd="osascript", timeout=launcher.TIMEOUT_S)
        with mock.patch.object(launcher.subprocess, "run", side_effect=timeout) as run:
            self.assertFalse(launcher.maybe_launch(self.data_dir, runner=launcher._run, now=1000))
        self.assertEqual(run.call_args.kwargs["timeout"], launcher.TIMEOUT_S)

    def test_no_runner_off_macos_never_runs_anything(self):
        fake_sys = types.SimpleNamespace(platform="linux", modules={})
        with mock.patch.object(launcher, "sys", fake_sys), mock.patch.object(launcher.subprocess, "run") as run:
            self.assertFalse(launcher.maybe_launch(self.data_dir, now=1000))
        run.assert_not_called()

    def test_no_runner_on_macos_outside_tests_uses_the_real_runner(self):
        fake_sys = types.SimpleNamespace(platform="darwin", modules={})
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(launcher, "sys", fake_sys), \
                mock.patch.object(launcher.subprocess, "run", return_value=completed) as run:
            self.assertTrue(launcher.maybe_launch(self.data_dir, now=1000))
        self.assertEqual(run.call_args.args[0][:2], ["osascript", "-e"])

    def test_a_truthy_non_boolean_launch_flag_is_off(self):
        for flag in ("true", 1):
            with self.subTest(flag=flag):
                self.config["projects"][0]["launchOnStart"] = flag
                self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_a_path_with_control_characters_is_refused(self):
        bad = self.project + "\n"
        self.config["projects"][0]["path"] = bad
        with mock.patch.object(launcher.os.path, "isdir", return_value=True):
            self.assertFalse(launcher.maybe_launch(os.path.join(bad, "docs"), runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_maybe_launch_without_now_reads_the_wall_clock(self):
        with mock.patch.object(launcher.time, "time", return_value=1000.0):
            self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner))
        with open(self.stamp_path(), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"at": 1000.0})

    def test_a_runner_returning_false_still_counts_as_requested(self):
        calls = []

        def failing(argv):
            calls.append(argv)
            return False

        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=failing, now=1000))
        self.assertEqual(len(calls), 1)

    def test_a_presence_failure_fails_open(self):
        with mock.patch.object(presence, "state", side_effect=RuntimeError("boom")):
            self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_a_config_failure_fails_open(self):
        with mock.patch.object(launcher.config, "load", side_effect=OSError("unreadable")):
            self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
