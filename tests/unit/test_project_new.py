"""Tests for project new (WP62): init, register, plan template with phase P1 not approved, and research note 01.

Everything runs in a temp ROADMAP_HOME and a temp project folder, through the CLI."""

import json
import os

from roadmap.core import parsers
from roadmap.store import config
from tests.unit.test_project_support import ProjectCase, read_text, run_cli


class ProjectNewCase(ProjectCase):
    def new(self, extra=(), folder=None):
        return self.envelope(["project", "new", folder or self.folder] + list(extra))

    def tasks(self):
        with open(os.path.join(self.data, "tasks.json"), encoding="utf-8") as fh:
            return json.load(fh)


class ProjectNewTests(ProjectNewCase):
    def test_research_flag_creates_note_01_plan_and_registration(self):
        code, body = self.new(["--research", "--name", "Demo App"])
        self.assertEqual(code, 0, body)
        data = body["data"]
        self.assertEqual(data["project"]["name"], "Demo App")
        self.assertEqual(data["plan"], {"phase": "P1", "approved": False, "written": True})
        self.assertEqual(data["research"]["number"], 1)
        note = os.path.join(self.data, "research", "01-scope.md")
        self.assertTrue(os.path.isfile(note))
        self.assertIn("# Research 01: Project scope and first questions", read_text(note))
        index = read_text(os.path.join(self.data, "research", "INDEX.md"))
        self.assertIn("- 01 scope — Project scope and first questions — (no finding yet)", index.splitlines())
        self.assertEqual([p["id"] for p in config.list_projects()], ["demo-app"])

    def test_plan_has_phase_p1_not_approved_and_parses_as_such(self):
        self.new()
        stored = self.tasks()
        self.assertEqual(stored["schemaVersion"], 1)
        self.assertEqual(stored["phases"], [{"id": "P1", "name": "Phase 1", "status": "todo", "approved": False}])
        self.assertEqual(stored["tasks"], [])
        phases, errors = parsers.parse_tasks(read_text(os.path.join(self.data, "tasks.json")))
        self.assertEqual(errors, [])
        self.assertIs(phases["phases"][0]["approved"], False)

    def test_without_research_flag_no_note_is_made(self):
        code, body = self.new()
        self.assertEqual(code, 0, body)
        self.assertIsNone(body["data"]["research"])
        self.assertFalse(os.path.exists(os.path.join(self.data, "research")))

    def test_second_run_is_idempotent(self):
        self.new(["--research"])
        before = read_text(os.path.join(self.data, "tasks.json"))
        code, body = self.new(["--research"])
        self.assertEqual(code, 0, body)
        self.assertFalse(body["data"]["plan"]["written"])
        self.assertIsNone(body["data"]["research"])
        self.assertEqual(read_text(os.path.join(self.data, "tasks.json")), before)
        self.assertFalse(os.path.exists(os.path.join(self.data, "research", "02-scope.md")))
        self.assertEqual(len(config.list_projects()), 1)

    def test_existing_tasks_are_kept_and_no_phase_is_added(self):
        self.init_and_add()
        with open(os.path.join(self.data, "tasks.json"), "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 1, "updated": "", "phases": [{"id": "WP1", "name": "Old"}],
                       "tasks": []}, fh)
        code, body = self.new()
        self.assertEqual(code, 0, body)
        self.assertFalse(body["data"]["plan"]["written"])
        self.assertEqual(self.tasks()["phases"], [{"id": "WP1", "name": "Old"}])

    def test_existing_registration_is_reused(self):
        self.init_and_add(name="Keep")
        code, body = self.new()
        self.assertEqual(code, 0, body)
        self.assertEqual(body["data"]["project"]["name"], "Keep")
        self.assertEqual(len(config.list_projects()), 1)

    def test_existing_note_is_not_replaced(self):
        self.new(["--research"])
        code, body = self.new(["--research"])
        self.assertEqual(code, 0, body)
        self.assertFalse(os.path.exists(os.path.join(self.data, "research", "02-scope.md")))

    def test_missing_folder_is_not_found_and_nothing_is_written(self):
        code, body = self.new(folder=os.path.join(self.tmp, "nope"))
        self.assertEqual(code, 3)
        self.assertEqual(body["error"]["code"], "not_found")
        self.assertEqual(config.list_projects(), [])

    def test_plain_output_names_the_approval_step(self):
        code, out, err = run_cli(["project", "new", self.folder, "--research"])
        self.assertEqual(code, 0, err)
        self.assertIn("plan: phase P1 written, not approved", out)
        self.assertIn("research: ", out)
        self.assertIn("roadmap phase approve P1", out)

    def test_newer_tasks_file_is_refused_and_left_alone(self):
        self.init_and_add()
        path = os.path.join(self.data, "tasks.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 99, "phases": [], "tasks": []}, fh)
        before = read_text(path)
        code, body = self.new()
        self.assertEqual(code, 5)
        self.assertEqual(body["error"]["code"], "newer_schema")
        self.assertEqual(read_text(path), before)
