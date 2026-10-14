"""Tests for the global config: defaults, add and remove, id and name uniqueness, path checks, file modes."""

import json
import os
import unittest

from roadmap.errors import RoadmapError
from roadmap.store import config, paths
from tests.unit.test_store_support import HomeCase, mode_of


class ConfigTests(HomeCase):
    def test_missing_config_gives_defaults_and_writes_nothing(self):
        cfg = config.load()
        self.assertEqual(cfg["port"], 8780)
        self.assertEqual(cfg["phonePort"], 8766)
        self.assertEqual(cfg["usage"], {"intervalS": 120, "mirrorToProjects": True})
        self.assertEqual(cfg["projects"], [])
        self.assertFalse(os.path.exists(paths.config_file()))

    def test_add_list_get_and_remove(self):
        folder = self.make_project("alpha")
        entry = config.add_project("Alpha Project", folder)
        self.assertEqual(entry["id"], "alpha-project")
        self.assertEqual(entry["path"], folder)
        self.assertEqual(entry["dataDir"], "docs")
        self.assertTrue(entry["addedAt"].endswith("Z"))
        self.assertEqual([p["id"] for p in config.list_projects()], ["alpha-project"])
        self.assertEqual(config.get_project("alpha-project")["name"], "Alpha Project")
        removed = config.remove_project("alpha-project")
        self.assertEqual(removed["id"], "alpha-project")
        self.assertEqual(config.list_projects(), [])
        self.assertTrue(os.path.isdir(folder))  # the project files are never touched

    def test_saved_config_has_schema_version_and_secure_modes(self):
        config.add_project("one", self.make_project("one"))
        with open(paths.config_file(), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["schemaVersion"], 1)
        self.assertEqual(mode_of(paths.config_file()), 0o600)
        self.assertEqual(mode_of(paths.config_dir()), 0o700)

    def test_duplicate_id_is_refused(self):
        config.add_project("First", self.make_project("first"), project_id="shared")
        with self.assertRaises(RoadmapError) as cm:
            config.add_project("Second", self.make_project("second"), project_id="shared")
        self.assertEqual(cm.exception.code, "conflict")
        self.assertEqual(cm.exception.exit, 4)
        self.assertEqual(len(config.list_projects()), 1)

    def test_derived_id_collision_is_refused(self):
        config.add_project("Split Net", self.make_project("a"))
        with self.assertRaises(RoadmapError) as cm:
            config.add_project("split-net", self.make_project("b"))
        self.assertEqual(cm.exception.code, "conflict")

    def test_duplicate_name_ignores_case(self):
        config.add_project("Roadmap", self.make_project("a"))
        with self.assertRaises(RoadmapError) as cm:
            config.add_project("ROADMAP", self.make_project("b"), project_id="other")
        self.assertEqual(cm.exception.code, "conflict")

    def test_path_must_exist(self):
        with self.assertRaises(RoadmapError) as cm:
            config.add_project("ghost", os.path.join(self.tmp, "nope"))
        self.assertEqual(cm.exception.code, "not_found")
        self.assertEqual(cm.exception.exit, 3)

    def test_bad_id_name_and_data_dir_are_refused(self):
        folder = self.make_project("ok")
        cases = [
            dict(name="x", path=folder, project_id="Bad Id"),
            dict(name="   ", path=folder),
            dict(name="x", path=folder, data_dir="../outside"),
            dict(name="x", path=folder, data_dir="/abs/docs"),
        ]
        for kwargs in cases:
            with self.assertRaises(RoadmapError) as cm:
                config.add_project(**kwargs)
            self.assertEqual(cm.exception.code, "invalid_input", kwargs)
        self.assertEqual(config.list_projects(), [])

    def test_get_and_remove_unknown_project_is_not_found(self):
        with self.assertRaises(RoadmapError) as cm:
            config.get_project("missing")
        self.assertEqual(cm.exception.exit, 3)
        with self.assertRaises(RoadmapError):
            config.remove_project("missing")
        self.assertFalse(os.path.exists(paths.config_file()))


if __name__ == "__main__":
    unittest.main()
