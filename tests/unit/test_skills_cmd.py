"""Tests for `roadmap skills list` and `roadmap skills install`: fresh install, conflicts, backups, dry-run, targets.

Everything runs in temp folders under a temp ROADMAP_HOME. The real home, ~/.claude and the real projects are not used.
"""

import glob
import json
import os

from roadmap.commands import skills
from tests.unit.test_project_support import ProjectCase, run_cli
from tests.unit.test_store_support import HomeCase


def _json(argv):
    code, out, err = run_cli(argv + ["--json"])
    return code, json.loads(out) if out.strip() else None, err


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class SkillsListTests(HomeCase):
    def test_list_names_both_templates_with_sizes(self):
        code, body, _ = _json(["skills", "list"])
        self.assertEqual(code, 0)
        names = [row["name"] for row in body["data"]["skills"]]
        self.assertEqual(names, ["roadmap-lead", "roadmap-worker"])
        for row in body["data"]["skills"]:
            self.assertGreater(row["bytes"], 0)
            self.assertLessEqual(row["bytes"], 3200)
            self.assertEqual(row["max_bytes"], 3200)

    def test_list_without_a_registered_project_says_no_project(self):
        code, body, _ = _json(["skills", "list"])
        self.assertEqual(code, 0)
        self.assertIsNone(body["data"]["project"])
        self.assertTrue(all(row["installed"] is None for row in body["data"]["skills"]))

    def test_list_plain_mode_prints_one_line_per_template(self):
        code, out, _ = run_cli(["skills", "list"])
        self.assertEqual(code, 0)
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("roadmap-worker", lines[1])
        self.assertIn("bytes", lines[1])


class SkillsInstallTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.target = os.path.join(self.tmp, "proj")
        os.makedirs(self.target)
        self.dest = os.path.join(self.target, ".claude", "skills")

    def test_fresh_install_into_target_copies_both_skills(self):
        code, body, err = _json(["skills", "install", "--target", self.target])
        self.assertEqual(code, 0, err)
        self.assertFalse(body["data"]["dry_run"])
        self.assertEqual([row["action"] for row in body["data"]["skills"]], ["create", "create"])
        for name, folder in skills.templates():
            copied = _read(os.path.join(self.dest, name, "SKILL.md"))
            self.assertEqual(copied, _read(os.path.join(folder, "SKILL.md")))

    def test_existing_skill_without_yes_is_a_conflict_and_writes_nothing(self):
        os.makedirs(os.path.join(self.dest, "roadmap-worker"))
        marker = os.path.join(self.dest, "roadmap-worker", "mine.md")
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("my own notes")
        code, body, _ = _json(["skills", "install", "--target", self.target])
        self.assertEqual(code, 4)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "conflict")
        self.assertIn("--yes", body["error"]["next"])
        self.assertEqual(_read(marker), "my own notes")
        self.assertFalse(os.path.exists(os.path.join(self.dest, "roadmap-lead")))
        self.assertEqual(glob.glob(os.path.join(self.dest, "*.bak-*")), [])

    def test_yes_backs_up_the_existing_folder_then_installs(self):
        os.makedirs(os.path.join(self.dest, "roadmap-worker"))
        with open(os.path.join(self.dest, "roadmap-worker", "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("old text")
        code, body, err = _json(["skills", "install", "--target", self.target, "--yes"])
        self.assertEqual(code, 0, err)
        rows = {row["name"]: row for row in body["data"]["skills"]}
        self.assertEqual(rows["roadmap-worker"]["action"], "replace")
        backup = rows["roadmap-worker"]["backup"]
        self.assertRegex(os.path.basename(backup), r"^roadmap-worker\.bak-\d{8}-\d{6}$")
        self.assertEqual(_read(os.path.join(backup, "SKILL.md")), "old text")
        self.assertEqual(rows["roadmap-lead"]["action"], "create")
        self.assertIn("name: roadmap-worker", _read(os.path.join(self.dest, "roadmap-worker", "SKILL.md")))

    def test_dry_run_writes_nothing_for_a_fresh_target(self):
        code, body, _ = _json(["skills", "install", "--target", self.target, "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue(body["data"]["dry_run"])
        self.assertEqual([row["action"] for row in body["data"]["skills"]], ["create", "create"])
        self.assertFalse(os.path.exists(os.path.join(self.target, ".claude")))

    def test_dry_run_reports_a_conflict_but_exits_zero_and_writes_nothing(self):
        os.makedirs(os.path.join(self.dest, "roadmap-lead"))
        code, body, _ = _json(["skills", "install", "--target", self.target, "--dry-run"])
        self.assertEqual(code, 0)
        actions = {row["name"]: row["action"] for row in body["data"]["skills"]}
        self.assertEqual(actions["roadmap-lead"], "conflict")
        self.assertEqual(glob.glob(os.path.join(self.dest, "roadmap-worker")), [])

    def test_missing_target_folder_is_not_found(self):
        code, body, _ = _json(["skills", "install", "--target", os.path.join(self.tmp, "nope")])
        self.assertEqual(code, 3)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_target_and_project_together_is_a_usage_error(self):
        code, body, _ = _json(["skills", "install", "--target", self.target, "--project", "demo"])
        self.assertEqual(code, 2)
        self.assertEqual(body["error"]["code"], "usage")

    def test_install_without_a_project_or_target_is_not_found(self):
        code, body, _ = _json(["skills", "install"])
        self.assertEqual(code, 3)

    def test_plain_mode_prints_what_it_did(self):
        code, out, _ = run_cli(["skills", "install", "--target", self.target, "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("would create", out)
        self.assertIn("dry run: nothing written", out)

    def test_backup_names_do_not_collide_within_one_second(self):
        dest = os.path.join(self.dest, "roadmap-worker")
        os.makedirs(dest)
        first = skills._backup_name(dest, "20260101-000000", set())
        second = skills._backup_name(dest, "20260101-000000", {first})
        self.assertNotEqual(first, second)
        self.assertTrue(second.endswith("-2"))


class SkillsProjectTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()

    def test_project_flag_installs_into_the_registered_folder(self):
        code, body, err = _json(["skills", "install", "--project", "demo"])
        self.assertEqual(code, 0, err)
        self.assertEqual(body["data"]["project"], "demo")
        self.assertEqual(os.path.realpath(body["data"]["root"]), os.path.realpath(self.folder))
        self.assertTrue(os.path.isfile(os.path.join(self.folder, ".claude", "skills", "roadmap-lead", "SKILL.md")))

    def test_list_with_project_reports_install_state(self):
        _json(["skills", "install", "--project", "demo"])
        code, body, _ = _json(["skills", "list", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual([row["installed"] for row in body["data"]["skills"]], [True, True])

    def test_unknown_project_is_not_found(self):
        code, body, _ = _json(["skills", "install", "--project", "nobody"])
        self.assertEqual(code, 3)
        self.assertEqual(body["error"]["code"], "not_found")
