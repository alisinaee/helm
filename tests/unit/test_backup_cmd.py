"""Tests for the backup command: copies of the data files, the newest 14 kept, and unknown projects."""

import os

from roadmap.services import projects
from roadmap.store import config, paths
from tests.unit.test_project_support import ProjectCase, read_text, run_cli


class BackupCommandTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()

    def test_backup_copies_the_data_files(self):
        code, body = self.envelope(["backup", "--project", "demo"])
        self.assertEqual(code, 0)
        row = body["data"]["backups"][0]
        self.assertEqual(row["status"], "ok")
        self.assertEqual(sorted(row["files"]), ["autonomy.json", "jobs.json", "roadmap.config.json", "tasks.json"])
        self.assertEqual(read_text(os.path.join(row["folder"], "tasks.json")),
                         read_text(os.path.join(self.data, "tasks.json")))

    def test_backup_without_project_covers_all_registered(self):
        other = self.make_project("other")
        run_cli(["project", "init", other])
        run_cli(["project", "add", other, "--json"])
        code, body = self.envelope(["backup"])
        self.assertEqual(sorted(r["project"] for r in body["data"]["backups"]), ["demo", "other"])

    def test_backup_skips_a_project_whose_data_folder_vanished(self):
        os.rename(self.data, self.data + ".moved")
        code, body = self.envelope(["backup"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["backups"][0]["status"], "skipped")

    def test_backup_unknown_project_is_not_found(self):
        code, _ = self.envelope(["backup", "--project", "nobody"])
        self.assertEqual(code, 3)

    def test_backup_with_no_projects_is_empty(self):
        config.remove_project("demo")
        code, out, _ = run_cli(["backup"])
        self.assertEqual(code, 0)
        self.assertIn("no projects", out)

    def test_backups_are_pruned_to_the_newest_14(self):
        for _ in range(16):
            projects.backup_projects("demo")
        names = os.listdir(paths.backups_dir("demo"))
        self.assertEqual(len(names), 14)
