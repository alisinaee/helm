"""Tests for project init, add, list, show, remove, check and migrate, through the CLI."""

import json
import os

from roadmap.store import config, paths
from tests.unit.test_project_support import ProjectCase, read_text, run_cli, write_json


class InitTests(ProjectCase):
    def test_init_writes_all_templates_with_schema_versions(self):
        code, out, _ = run_cli(["project", "init", self.folder, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(json.loads(out)["data"]["created"]),
                         ["autonomy.json", "jobs.json", "roadmap.config.json", "tasks.json"])
        for name, version in (("tasks.json", 1), ("jobs.json", 1), ("autonomy.json", 2),
                              ("roadmap.config.json", 1)):
            with self.subTest(name=name):
                self.assertEqual(json.loads(read_text(os.path.join(self.data, name)))["schemaVersion"], version)
        title = json.loads(read_text(os.path.join(self.data, "roadmap.config.json")))["title"]
        self.assertEqual(title, "demo")

    def test_init_never_overwrites_existing_files(self):
        write_json(os.path.join(self.data, "tasks.json"), {"tasks": [], "phases": [], "mine": True})
        before = read_text(os.path.join(self.data, "tasks.json"))
        code, out, _ = run_cli(["project", "init", self.folder, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)["data"]
        self.assertIn("tasks.json", data["kept"])
        self.assertNotIn("tasks.json", data["created"])
        self.assertEqual(read_text(os.path.join(self.data, "tasks.json")), before)

    def test_init_missing_folder_is_not_found(self):
        code, body = self.envelope(["project", "init", os.path.join(self.tmp, "nope")])
        self.assertEqual(code, 3)
        self.assertEqual(body["error"]["code"], "not_found")


class AddListShowRemoveTests(ProjectCase):
    def test_add_after_init_registers_with_folder_name(self):
        code, body = self.envelope(["project", "init", self.folder])
        self.assertEqual(code, 0)
        code, body = self.envelope(["project", "add", self.folder])
        self.assertEqual(code, 0)
        self.assertIs(body["ok"], True)
        project = body["data"]["project"]
        self.assertEqual((project["id"], project["name"], project["dataDir"]), ("demo", "demo", "docs"))
        self.assertEqual(project["path"], os.path.abspath(self.folder))

    def test_add_without_data_folder_asks_for_init(self):
        code, body = self.envelope(["project", "add", self.folder])
        self.assertEqual(code, 3)
        self.assertIn("project init", body["error"]["message"])
        self.assertEqual(config.list_projects(), [])

    def test_add_missing_path_is_not_found(self):
        code, body = self.envelope(["project", "add", os.path.join(self.tmp, "ghost")])
        self.assertEqual(code, 3)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_duplicate_name_and_id_conflict(self):
        self.init_and_add()
        other = self.make_project("other")
        run_cli(["project", "init", other])
        code, body = self.envelope(["project", "add", other, "--name", "DEMO"])
        self.assertEqual(code, 4)
        self.assertEqual(body["error"]["code"], "conflict")

    def test_same_folder_twice_conflicts(self):
        self.init_and_add()
        code, body = self.envelope(["project", "add", self.folder, "--name", "again"])
        self.assertEqual(code, 4)
        self.assertIn("already registered", body["error"]["message"])

    def test_list_and_show(self):
        self.init_and_add()
        code, body = self.envelope(["project", "list"])
        self.assertEqual([p["id"] for p in body["data"]["projects"]], ["demo"])
        code, body = self.envelope(["project", "show", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["project"]["files"]["tasks.json"], True)
        code, body = self.envelope(["project", "show", "nobody"])
        self.assertEqual(code, 3)

    def test_remove_unregisters_and_keeps_files(self):
        self.init_and_add()
        code, body = self.envelope(["project", "remove", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual(config.list_projects(), [])
        self.assertTrue(os.path.isfile(os.path.join(self.data, "tasks.json")))
        code, _ = self.envelope(["project", "remove", "demo"])
        self.assertEqual(code, 3)


class CheckTests(ProjectCase):
    def test_healthy_project_reports_ok_with_versions(self):
        self.init_and_add()
        code, body = self.envelope(["project", "check", "demo"])
        self.assertEqual(code, 0)
        rows = {r["file"]: r for r in body["data"]["projects"][0]["files"]}
        self.assertEqual(rows["autonomy.json"]["schemaVersion"], 2)
        self.assertTrue(all(r["status"] == "ok" for r in rows.values()))

    def test_corrupt_file_is_reported_with_exit_5(self):
        self.init_and_add()
        with open(os.path.join(self.data, "tasks.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        code, body = self.envelope(["project", "check"])
        self.assertEqual(code, 5)
        self.assertEqual(body["error"]["code"], "invalid_data")
        self.assertIn("tasks.json", body["error"]["message"])
        self.assertEqual(read_text(os.path.join(self.data, "tasks.json")), "{not json")

    def test_plain_check_prints_per_file_rows(self):
        self.init_and_add()
        code, out, _ = run_cli(["project", "check", "demo"])
        self.assertEqual(code, 0)
        self.assertIn("tasks.json", out)
        self.assertIn("ok", out)

    def test_newer_file_is_reported_as_error(self):
        self.init_and_add()
        write_json(os.path.join(self.data, "jobs.json"), {"schemaVersion": 99, "jobs": []})
        code, body = self.envelope(["project", "check", "demo"])
        self.assertEqual(code, 5)
        self.assertIn("newer", body["error"]["message"])


class MigrateTests(ProjectCase):
    def legacy_autonomy(self):
        """A v1 autonomy file: no schemaVersion, the limit and a usage block."""
        write_json(os.path.join(self.data, "autonomy.json"), {
            "limit": {"kind": "weekly", "stopAtPercent": 72},
            "usage": {"weeklyPercent": 63, "updated": "2026-10-13T17:30:03+0330"},
        })

    def test_migrate_backs_up_then_upgrades_autonomy(self):
        self.init_and_add()
        self.legacy_autonomy()
        code, body = self.envelope(["project", "migrate", "demo"])
        self.assertEqual(code, 0)
        result = body["data"]
        self.assertEqual(result["migrated"], [{"file": "autonomy.json", "from": 1, "to": 2}])
        self.assertTrue(os.path.isdir(result["backup"]))
        backed_up = json.loads(read_text(os.path.join(result["backup"], "autonomy.json")))
        self.assertIn("usage", backed_up)
        self.assertNotIn("schemaVersion", backed_up)
        now = json.loads(read_text(os.path.join(self.data, "autonomy.json")))
        self.assertEqual(now["schemaVersion"], 2)
        self.assertEqual(now["limit"]["stopAtPercent"], 72)
        self.assertNotIn("usage", now)

    def test_migrate_when_current_changes_nothing_and_makes_no_backup(self):
        self.init_and_add()
        code, body = self.envelope(["project", "migrate", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["migrated"], [])
        self.assertIsNone(body["data"]["backup"])
        self.assertFalse(os.path.isdir(paths.backups_dir("demo")))

    def test_migrate_refuses_newer_schema_and_writes_nothing(self):
        self.init_and_add()
        self.legacy_autonomy()
        write_json(os.path.join(self.data, "jobs.json"), {"schemaVersion": 7, "jobs": []})
        before = read_text(os.path.join(self.data, "autonomy.json"))
        code, body = self.envelope(["project", "migrate", "demo"])
        self.assertEqual(code, 5)
        self.assertEqual(body["error"]["code"], "newer_schema")
        self.assertEqual(read_text(os.path.join(self.data, "autonomy.json")), before)
        self.assertFalse(os.path.isdir(paths.backups_dir("demo")))

    def test_migrate_unknown_project_is_not_found(self):
        code, _ = self.envelope(["project", "migrate", "missing"])
        self.assertEqual(code, 3)

