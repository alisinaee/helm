"""R7.85 (H3): loader.revision covers the head files, so a Head reply or gate change moves the revision.

Checks: creating or editing each head file (head-text.jsonl, head-spool.jsonl, head-gate.json, head-pause, undo.jsonl,
head.jsonl) changes the revision; a missing file stamps as None and its creation changes the revision; a stable
project keeps one revision. Runs in a temp ROADMAP_HOME (ControlCase) with the registered project demo.
"""

import os
import unittest

from roadmap.services import head as head_store, loader
from tests.unit.test_control_support import ControlCase


class RevisionFilesTests(ControlCase):
    def setUp(self):
        super().setUp()
        loader._CACHE.clear()

    def _write(self, name, text):
        with open(os.path.join(self.docs, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_revision_is_stable_with_no_head_files(self):
        first = loader.project_revision("demo")
        self.assertEqual(first, loader.project_revision("demo"))

    def test_creating_each_head_file_changes_the_revision(self):
        for name in (head_store.FILE, head_store.TEXT_FILE, head_store.SPOOL_FILE, head_store.GATE_STAMP_FILE,
                     head_store.GATE_PAUSE_FILE, loader.UNDO_FILE):
            with self.subTest(name=name):
                before = loader.project_revision("demo")
                self._write(name, "{}\n")
                self.assertNotEqual(before, loader.project_revision("demo"))

    def test_editing_each_head_file_changes_the_revision(self):
        for name in (head_store.FILE, head_store.TEXT_FILE, head_store.SPOOL_FILE, head_store.GATE_STAMP_FILE,
                     loader.UNDO_FILE):
            with self.subTest(name=name):
                self._write(name, "{}\n")
                before = loader.project_revision("demo")
                self._write(name, '{"reply":"new text"}\n')
                self.assertNotEqual(before, loader.project_revision("demo"))

    def test_deleting_a_head_file_changes_the_revision(self):
        self._write(head_store.TEXT_FILE, '{"id":"H1"}\n')
        before = loader.project_revision("demo")
        os.remove(os.path.join(self.docs, head_store.TEXT_FILE))
        self.assertNotEqual(before, loader.project_revision("demo"))


if __name__ == "__main__":
    unittest.main()
