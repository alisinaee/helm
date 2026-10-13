"""Rules: the line format, the caps, show filtering, add and rm, check, and sync into CLAUDE.md (idempotent, backup
first, refuses broken markers)."""

import os
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import rules
from roadmap.store import config
from tests.unit.test_control_support import ControlCase

AGENT = {"CLAUDECODE": "1"}


class RulesCase(ControlCase):
    def rules_path(self):
        return os.path.join(self.docs, "rules.txt")

    def write_rules(self, text):
        with open(self.rules_path(), "w", encoding="utf-8") as fh:
            fh.write(text)

    def claude_path(self):
        return os.path.join(self.project, "CLAUDE.md")

    def read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def project_record(self):
        return config.get_project("demo")


class FormatTests(RulesCase):
    def test_parse_reads_budget_and_plain_rules(self):
        rows, problems = rules.parse("# header\nR3 haiku budget 60 | Stop at 60k on one task\nR1 all do | Test first\n")
        self.assertEqual(problems, [])
        self.assertEqual([r["id"] for r in rows], ["R3", "R1"])
        self.assertEqual(rows[0]["value"], 60)
        self.assertEqual(rules.format_rule(rows[0]), "R3 haiku budget 60 | Stop at 60k on one task")
        self.assertEqual(rules.format_rule(rows[1]), "R1 all do | Test first")

    def test_bad_lines_are_reported_with_their_number(self):
        _, problems = rules.parse("R1 nowhere do | x\nR2 all budget | no number\nR3 all do 5 | number on do\n"
                                  "junk\nR4 all do | " + "x" * 161 + "\n")
        self.assertEqual(len(problems), 5)
        self.assertTrue(problems[0].startswith("line 1:"))
        self.assertTrue(problems[3].startswith("line 4"))

    def test_duplicate_ids_and_too_many_rules_are_problems(self):
        _, problems = rules.parse("R1 all do | a\nR1 all do | b\n")
        self.assertIn("R1 is listed more than once", problems)
        many = "".join("R%d all do | r\n" % i for i in range(1, 62))
        _, problems = rules.parse(many)
        self.assertTrue(any("61 rules" in p for p in problems))

    def test_file_over_8_kb_is_a_problem(self):
        big = "".join("R%d all do | %s\n" % (i, "y" * 150) for i in range(1, 55))
        _, problems = rules.parse(big)
        self.assertTrue(any("8192" in p for p in problems))


class AddRemoveTests(RulesCase):
    def test_add_numbers_rules_and_keeps_the_header(self):
        rules.add(self.docs, "all", "do", "Run the tests", source="cli")
        rules.add(self.docs, "haiku", "budget", "Stop at 60k", value=60, source="cli")
        rules.add(self.docs, "lead", "dont", "Edit the plan by hand", source="cli")
        text = self.read(self.rules_path())
        self.assertTrue(text.startswith("# Project rules."))
        self.assertIn("R2 haiku budget 60 | Stop at 60k", text)
        rules.remove(self.docs, "R2", source="cli")
        self.assertEqual(rules.add(self.docs, "all", "done", "Works on the Mac", source="cli")["id"], "R4")

    def test_add_rejects_bad_fields_and_long_text(self):
        for args in (("nowhere", "do", "x"), ("all", "maybe", "x"), ("all", "budget", "x"),
                     ("all", "do", "x" * 161), ("all", "do", "")):
            with self.assertRaises(RoadmapError) as ctx:
                rules.add(self.docs, *args, source="cli")
            self.assertEqual(ctx.exception.exit, 2)
        self.assertFalse(os.path.exists(self.rules_path()))

    def test_add_stops_at_60_rules(self):
        self.write_rules("".join("R%d all do | r\n" % i for i in range(1, 61)))
        with self.assertRaises(RoadmapError) as ctx:
            rules.add(self.docs, "all", "do", "one more", source="cli")
        self.assertEqual(ctx.exception.code, "conflict")

    def test_rm_unknown_id_is_not_found(self):
        self.write_rules("R1 all do | a\n")
        with self.assertRaises(RoadmapError) as ctx:
            rules.remove(self.docs, "R9", source="cli")
        self.assertEqual(ctx.exception.exit, 3)

    def test_add_rm_and_sync_are_refused_from_an_agent(self):
        with mock.patch.dict(os.environ, AGENT):
            with self.assertRaises(RoadmapError) as ctx:
                rules.add(self.docs, "all", "do", "x")
            self.assertEqual(ctx.exception.code, "agent_refused")
            with self.assertRaises(RoadmapError):
                rules.remove(self.docs, "R1")
            with self.assertRaises(RoadmapError):
                rules.sync(self.project_record(), self.docs)


class ShowTests(RulesCase):
    def setUp(self):
        super().setUp()
        self.write_rules("\n".join([
            "R1 all do | Run the tests before a commit",
            "R2 haiku budget 60 | Stop at 60k on one task",
            "R3 sonnet dont | Do not touch the plan",
            "R4 worker do | Report in ten lines",
            "R5 lead do | Check the diff yourself",
            "R6 phase:P0 do | Keep the parser pure",
            "R7 task:P0.2 dont | Do not change the writer API",
            "R8 claude do | Mention the rules file",
            "",
        ]))

    def ids(self, lines):
        return [line.split(" ")[0] for line in lines]

    def test_worker_on_haiku_for_a_phase_task_sees_its_rules(self):
        self.assertEqual(self.ids(rules.show(self.docs, task_id="P0.1", model="haiku", role="worker")),
                         ["R1", "R2", "R4", "R6"])

    def test_task_scope_and_lead_role(self):
        self.assertEqual(self.ids(rules.show(self.docs, task_id="P0.2", model="sonnet", role="lead")),
                         ["R1", "R3", "R5", "R6", "R7"])

    def test_claude_rules_are_never_shown(self):
        self.assertNotIn("R8", self.ids(rules.show(self.docs)))

    def test_show_caps_at_twelve_lines(self):
        extra = "".join("R%d all do | r\n" % i for i in range(9, 22))
        self.write_rules(self.read(self.rules_path()) + extra)
        lines = rules.show(self.docs)
        self.assertEqual(len(lines), 12)
        self.assertTrue(lines[-1].startswith("+"))

    def test_bad_role_is_a_usage_error(self):
        with self.assertRaises(RoadmapError):
            rules.show(self.docs, role="boss")


class CheckTests(RulesCase):
    def test_check_counts_good_rules_and_lists_problems(self):
        self.write_rules("R1 all do | ok\n")
        self.assertEqual(rules.check(self.docs), 1)
        self.write_rules("R1 all do | ok\nnot a rule\n")
        with self.assertRaises(RoadmapError) as ctx:
            rules.check(self.docs)
        self.assertEqual(ctx.exception.code, "invalid_data")
        self.assertIn("line 2", ctx.exception.message)


class SyncTests(RulesCase):
    def setUp(self):
        super().setUp()
        self.write_rules("R1 all do | Run the tests\nR2 haiku budget 60 | Stop at 60k\nR3 lead dont | Edit the plan\n"
                         "R4 claude do | Mention the file\nR5 worker do | Worker only\n")
        with open(self.claude_path(), "w", encoding="utf-8") as fh:
            fh.write("# Project\n\nKeep this text.\n")

    def test_first_sync_adds_the_block_with_backup_and_then_nothing_changes(self):
        project = self.project_record()
        first = rules.sync(project, self.docs)
        self.assertEqual((first["added"], first["changed"], first["removed"]), (3, 0, 0))
        self.assertTrue(first["written"])
        self.assertIsNotNone(first["backup"])
        text = self.read(self.claude_path())
        self.assertIn("Keep this text.", text)
        self.assertIn("<!-- roadmap:rules -->", text)
        self.assertIn("<!-- /roadmap:rules -->", text)
        self.assertNotIn("Worker only", text)
        self.assertIn("- R4 claude do | Mention the file", text)
        second = rules.sync(project, self.docs)
        self.assertEqual((second["added"], second["changed"], second["removed"]), (0, 0, 0))
        self.assertFalse(second["written"])
        self.assertEqual(self.read(self.claude_path()), text)

    def test_a_changed_rule_is_counted_as_changed(self):
        project = self.project_record()
        rules.sync(project, self.docs)
        self.write_rules(self.read(self.rules_path()).replace("Run the tests", "Run all the tests"))
        result = rules.sync(project, self.docs)
        self.assertEqual((result["added"], result["changed"], result["removed"]), (0, 1, 0))

    def test_dry_run_writes_nothing(self):
        project = self.project_record()
        before = self.read(self.claude_path())
        result = rules.sync(project, self.docs, dry_run=True)
        self.assertEqual(result["added"], 3)
        self.assertEqual(self.read(self.claude_path()), before)
        self.assertFalse(os.path.exists(os.path.join(self.state_dir, "backups")))

    def test_broken_markers_are_refused_and_the_file_is_left_alone(self):
        broken = "a\n<!-- roadmap:rules -->\nb\n<!-- roadmap:rules -->\n"
        with open(self.claude_path(), "w", encoding="utf-8") as fh:
            fh.write(broken)
        with self.assertRaises(RoadmapError) as ctx:
            rules.sync(self.project_record(), self.docs)
        self.assertEqual(ctx.exception.code, "invalid_data")
        self.assertEqual(self.read(self.claude_path()), broken)

    def test_end_marker_before_start_is_refused(self):
        with open(self.claude_path(), "w", encoding="utf-8") as fh:
            fh.write("<!-- /roadmap:rules -->\n<!-- roadmap:rules -->\n")
        with self.assertRaises(RoadmapError):
            rules.sync(self.project_record(), self.docs)

    def test_sync_refuses_a_rules_file_with_problems(self):
        self.write_rules("R1 all do | ok\ngarbage\n")
        with self.assertRaises(RoadmapError):
            rules.sync(self.project_record(), self.docs)
