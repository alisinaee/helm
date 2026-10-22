"""Tests for store paths: ROADMAP_HOME redirects every location, defaults match the spec, dirs are created 0700."""

import os
from unittest import mock
import sys
import unittest

from roadmap.errors import RoadmapError
from roadmap.store import paths
from tests.unit.test_store_support import HomeCase, mode_of


class PathRedirectTests(HomeCase):
    def test_roadmap_home_redirects_config_state_and_logs(self):
        root = os.environ["ROADMAP_HOME"]
        self.assertTrue(paths.config_dir().startswith(self.tmp))
        self.assertEqual(paths.config_dir(), os.path.join(root, "config"))
        self.assertEqual(paths.state_dir(), os.path.join(root, "state"))
        self.assertEqual(paths.logs_dir(), os.path.join(root, "logs"))
        self.assertEqual(paths.config_file(), os.path.join(root, "config", "config.json"))
        self.assertEqual(paths.phone_token_file(), os.path.join(root, "config", "phone.token"))
        self.assertEqual(paths.usage_file(), os.path.join(root, "state", "usage.json"))
        self.assertEqual(paths.hooks_file("demo"), os.path.join(root, "state", "hooks-demo.json"))
        self.assertEqual(paths.backups_dir("demo"), os.path.join(root, "state", "backups", "demo"))

    def test_defaults_without_roadmap_home_use_home_directory(self):
        del os.environ["ROADMAP_HOME"]
        home = os.environ["HOME"]
        self.assertEqual(paths.config_dir(), os.path.join(home, ".config", "roadmap-board"))
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(paths.state_dir(), os.path.join(home, "Library", "Application Support", "roadmap-board"))
            self.assertEqual(paths.logs_dir(), os.path.join(home, "Library", "Logs", "roadmap-board"))
        with mock.patch.object(sys, "platform", "linux"), mock.patch.dict(os.environ, {"XDG_STATE_HOME": ""}):
            self.assertEqual(paths.state_dir(), os.path.join(home, ".local", "state", "roadmap-board"))
            self.assertEqual(paths.logs_dir(), os.path.join(home, ".local", "state", "roadmap-board", "logs"))

    def test_blank_roadmap_home_counts_as_unset(self):
        os.environ["ROADMAP_HOME"] = "   "
        self.assertEqual(paths.config_dir(), os.path.join(os.environ["HOME"], ".config", "roadmap-board"))

    def test_ensure_dir_creates_missing_chain_with_mode_0700(self):
        target = os.path.join(self.tmp, "home", "config")
        paths.ensure_dir(target)
        for directory in (os.path.join(self.tmp, "home"), target):
            self.assertTrue(os.path.isdir(directory))
            self.assertEqual(mode_of(directory), 0o700)

    def test_ensure_dir_does_not_change_existing_directory(self):
        existing = os.path.join(self.tmp, "existing")
        os.mkdir(existing)
        os.chmod(existing, 0o755)
        paths.ensure_dir(existing)
        self.assertEqual(mode_of(existing), 0o755)

    def test_project_id_is_checked_before_building_paths(self):
        for bad in ("../x", "Demo", "", "a/b", "-lead"):
            with self.assertRaises(RoadmapError) as cm:
                paths.backups_dir(bad)
            self.assertEqual(cm.exception.code, "invalid_input")
        self.assertTrue(paths.valid_id("split-net-2"))


if __name__ == "__main__":
    unittest.main()
