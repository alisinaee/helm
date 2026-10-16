"""R10.10 C2: loader reads docs/work.json into the snapshot ("work" key) and its revision moves when work.json changes.

Checks: the snapshot of a project with work.json has a "work" key with the item; editing work.json changes the
revision and the next snapshot shows the new status; a project without work.json has no "work" key. Runs in a temp
ROADMAP_HOME (ControlCase) with the registered project demo.
"""

import json
import os
import unittest

from roadmap.services import loader
from tests.unit.test_control_support import ControlCase


def _work(title):
    return {"schemaVersion": 1, "items": [{"id": "W1", "title": title, "kind": "feature", "status": "Todo"}],
            "links": {}, "events": []}


class LoaderWorkTests(ControlCase):
    def setUp(self):
        super().setUp()
        loader._CACHE.clear()
        self.path = os.path.join(self.docs, "work.json")

    def _write_work(self, title):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(_work(title), fh)

    def test_snapshot_has_work_key(self):
        self._write_work("Alpha")
        snap = loader.load_snapshot("demo")
        self.assertIn("work", snap)
        self.assertEqual([row["id"] for row in snap["work"]], ["W1"])
        self.assertEqual(snap["work"][0]["title"], "Alpha")

    def test_snapshot_without_work_file_has_no_work_key(self):
        self.assertNotIn("work", loader.load_snapshot("demo"))

    def test_revision_changes_after_work_edit(self):
        self._write_work("Alpha")
        before = loader.project_revision("demo")
        self.assertEqual(before, loader.project_revision("demo"))
        self._write_work("Beta")
        after = loader.project_revision("demo")
        self.assertNotEqual(before, after)
        snap = loader.load_snapshot("demo")
        self.assertEqual(snap["rev"], after)
        self.assertEqual(snap["work"][0]["title"], "Beta")


if __name__ == "__main__":
    unittest.main()
