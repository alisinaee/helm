"""Tests for the opt-in launcher (R7.1 T4). A fake runner stands in for osascript; nothing is ever launched."""

import os
import shutil
import shlex
import tempfile
import unittest
from unittest import mock

from roadmap.services import launcher, presence
from roadmap.store import paths


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="launcher-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = os.path.join(self.tmp, 'my "app" dir')
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

    def test_off_by_default(self):
        del self.config["projects"][0]["launchOnStart"]
        self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.config["projects"][0]["launchOnStart"] = False
        self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_launches_with_quoted_path_as_argv(self):
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertEqual(len(self.calls), 1)
        argv = self.calls[0]
        self.assertIsInstance(argv, list)
        self.assertEqual(argv[:2], ["osascript", "-e"])
        script = argv[2]
        self.assertTrue(script.startswith('tell application "Terminal" to do script "'))
        # the shell-quoted path, with its double quotes escaped for AppleScript
        self.assertIn(shlex.quote(self.project).replace('"', '\\"'), script)
        self.assertIn('\\"app\\"', script)

    def test_second_call_within_ten_minutes_does_nothing(self):
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000 + 599))
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000 + 601))
        self.assertEqual(len(self.calls), 2)

    def test_presence_open_means_no_launch(self):
        with mock.patch.object(presence, "state", return_value=presence.OPEN):
            self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        with mock.patch.object(presence, "state", return_value=presence.WATCHING):
            self.assertFalse(launcher.maybe_launch(self.data_dir, runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_missing_folder_is_refused(self):
        self.config["projects"][0]["path"] = os.path.join(self.tmp, "gone")
        self.assertFalse(launcher.maybe_launch(os.path.join(self.tmp, "gone", "docs"), runner=self.runner, now=1000))
        self.config["projects"][0]["path"] = "relative/path"
        self.assertFalse(launcher.maybe_launch("relative/path/docs", runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_unknown_data_dir_is_refused(self):
        self.assertFalse(launcher.maybe_launch(os.path.join(self.tmp, "other"), runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_runner_failure_is_swallowed(self):
        def broken(argv):
            raise OSError("no osascript")
        self.assertFalse(launcher.maybe_launch(self.data_dir, runner=broken, now=1000))

    def test_no_runner_under_unittest_never_runs_anything(self):
        with mock.patch.object(launcher.subprocess, "run") as run:
            self.assertFalse(launcher.maybe_launch(self.data_dir, now=1000))
        run.assert_not_called()

    def test_shell_metacharacters_stay_inert(self):
        hostile = os.path.join(self.tmp, "a;rm -rf x $(touch y) `id`")
        os.makedirs(hostile)
        self.config["projects"][0]["path"] = hostile
        self.assertTrue(launcher.maybe_launch(os.path.join(hostile, "docs"), runner=self.runner, now=1000))
        self.assertEqual(self.calls[0][:2], ["osascript", "-e"])
        self.assertEqual(len(self.calls[0]), 3)


if __name__ == "__main__":
    unittest.main()
