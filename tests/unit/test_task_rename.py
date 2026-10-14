"""The task.rename registry op (roadmap/services/commands.py): retitles one task and undo restores the old title.
The title rules (non-empty, at most 120 characters, no control characters) and the usual not_found error for an
unknown id are checked too."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import commands, tasks
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID


class RenameCase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-rename-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def run_op(self, op, args, source="gui"):
        with commands.context(source, PROJECT_ID):
            return commands.run(op, args, source, self.data_dir)

    def title_of(self, task_id):
        return tasks.get(self.data_dir, task_id)["title"]

    def activity(self):
        return commands.activity.recent(self.data_dir, 100)


class Rename(RenameCase):
    def test_renames_the_task_and_logs_one_line(self):
        before = len(self.activity())
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "  New title  "})
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["data"]["title"], "New title")
        self.assertTrue(reply["data"]["changed"])
        self.assertEqual(self.title_of("P1.1"), "New title")
        self.assertEqual(len(self.activity()), before + 1)
        self.assertTrue(reply["undo"])

    def test_status_and_other_fields_are_kept(self):
        before = tasks.get(self.data_dir, "P1.1")
        self.run_op("task.rename", {"id": "P1.1", "title": "Renamed"})
        after = tasks.get(self.data_dir, "P1.1")
        for key in ("status", "tokensK", "phase", "model"):
            self.assertEqual(after.get(key), before.get(key))

    def test_same_title_changes_nothing(self):
        current = self.title_of("P1.1")
        reply = self.run_op("task.rename", {"id": "P1.1", "title": current})
        self.assertFalse(reply["data"]["changed"])
        self.assertFalse(reply["undo"])

    def test_undo_restores_the_old_title(self):
        old = self.title_of("P1.1")
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "Temporary"})
        self.run_op("undo", {"activity": reply["activity"]})
        self.assertEqual(self.title_of("P1.1"), old)


class Validation(RenameCase):
    def assertRefused(self, args, code="usage"):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("task.rename", args)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def test_empty_or_blank_title_is_refused(self):
        self.assertRefused({"id": "P1.1", "title": ""})
        self.assertRefused({"id": "P1.1", "title": "   "})
        self.assertRefused({"id": "P1.1"})

    def test_title_of_120_characters_is_allowed_and_121_is_refused(self):
        self.run_op("task.rename", {"id": "P1.1", "title": "x" * 120})
        self.assertEqual(len(self.title_of("P1.1")), 120)
        exc = self.assertRefused({"id": "P1.1", "title": "x" * 121})
        self.assertIn("121", str(exc))

    def test_control_characters_are_refused(self):
        for bad in ("two\nlines", "tab\there", "bell\x07", "del\x7f"):
            self.assertRefused({"id": "P1.1", "title": bad})

    def test_bad_task_id_is_refused(self):
        self.assertRefused({"id": "not an id!", "title": "Fine"})

    def test_unknown_task_gives_not_found_with_next(self):
        exc = self.assertRefused({"id": "P99.99", "title": "Fine"}, code="not_found")
        self.assertTrue(exc.next)
        self.assertIn("roadmap task list", exc.next)


if __name__ == "__main__":
    unittest.main()
