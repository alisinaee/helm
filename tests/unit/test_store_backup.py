"""Tests for backups: copies land in a timestamped folder, the newest 14 are kept, modes are 0600 and 0700."""

import datetime
import os
import unittest

from roadmap.store import backup, paths
from tests.unit.test_store_support import HomeCase, mode_of


class BackupTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.docs = os.path.join(self.tmp, "docs")
        os.makedirs(self.docs)
        self.files = []
        for name in ("tasks.json", "jobs.json", "autonomy.json"):
            path = os.path.join(self.docs, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"schemaVersion": 1}')
            self.files.append(path)
        self.start = datetime.datetime(2026, 10, 1, 8, 0, 0, tzinfo=datetime.timezone.utc)

    def test_copies_files_with_secure_modes(self):
        dest = backup.backup_files("demo", self.files + [os.path.join(self.docs, "missing.json")], now=self.start)
        self.assertEqual(sorted(os.listdir(dest)), ["autonomy.json", "jobs.json", "tasks.json"])
        self.assertEqual(mode_of(dest), 0o700)
        self.assertEqual(mode_of(os.path.join(dest, "tasks.json")), 0o600)
        self.assertTrue(dest.startswith(paths.backups_dir("demo")))

    def test_same_instant_gets_a_distinct_folder(self):
        first = backup.backup_files("demo", self.files, now=self.start)
        second = backup.backup_files("demo", self.files, now=self.start)
        self.assertNotEqual(first, second)

    def test_keeps_newest_14_and_prunes_the_rest(self):
        created = []
        for i in range(16):
            created.append(backup.backup_files("demo", self.files,
                                               now=self.start + datetime.timedelta(minutes=i)))
        kept = sorted(os.listdir(paths.backups_dir("demo")))
        self.assertEqual(len(kept), 14)
        self.assertEqual(kept, sorted(os.path.basename(p) for p in created[-14:]))
        self.assertFalse(os.path.exists(created[0]))
        self.assertTrue(os.path.exists(created[-1]))

    def test_prune_ignores_stray_files_and_other_projects(self):
        backup.backup_files("other", self.files, now=self.start)
        root = paths.backups_dir("demo")
        os.makedirs(root)
        with open(os.path.join(root, "note.txt"), "w", encoding="utf-8") as fh:
            fh.write("keep me")
        for i in range(3):
            backup.backup_files("demo", self.files, now=self.start + datetime.timedelta(hours=i))
        deleted = backup.prune("demo", keep=1)
        self.assertEqual(len(deleted), 2)
        self.assertEqual(len([n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))]), 1)
        self.assertTrue(os.path.exists(os.path.join(root, "note.txt")))
        self.assertEqual(len(os.listdir(paths.backups_dir("other"))), 1)


if __name__ == "__main__":
    unittest.main()
