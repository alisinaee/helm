"""Tests for the research command (WP17): new, list and check, through the CLI, in a temp ROADMAP_HOME and project."""

import os
import shutil

from roadmap.commands import research
from tests.unit.test_project_support import ProjectCase, read_text, run_cli


class ResearchCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()
        self.notes = os.path.join(self.data, "research")

    def new(self, slug, title="Similar products"):
        return self.envelope(["research", "new", slug, title, "--project", "demo"])

    def check(self):
        return self.envelope(["research", "check", "--project", "demo"])

    def write_note(self, name, text):
        os.makedirs(self.notes, exist_ok=True)
        with open(os.path.join(self.notes, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def good_note(self, title="Demo"):
        return ("# Research: %s\n\n## Question\n\nQ?\n\n## Findings\n\n- x\n\n## Decisions\n\n- y\n\n"
                "## Sources\n\n- https://example.com\n" % title)


class NewTests(ResearchCase):
    def test_new_writes_template_and_index_line(self):
        code, body = self.new("landscape")
        self.assertEqual(code, 0, body)
        path = os.path.join(self.notes, "01-landscape.md")
        self.assertEqual(body["data"]["number"], 1)
        text = read_text(path)
        self.assertIn("# Research 01: Similar products", text)
        for heading in research.REQUIRED_HEADINGS:
            self.assertIn(heading, text.splitlines())
        index = read_text(os.path.join(self.notes, "INDEX.md"))
        self.assertIn("- 01 landscape — Similar products — (no finding yet)", index.splitlines())

    def test_numbers_follow_each_other(self):
        self.new("landscape")
        code, body = self.new("risks", "Risks")
        self.assertEqual(code, 0, body)
        self.assertEqual(body["data"]["number"], 2)
        self.assertTrue(os.path.isfile(os.path.join(self.notes, "02-risks.md")))

    def test_duplicate_slug_is_a_conflict(self):
        self.new("landscape")
        code, body = self.new("landscape", "Again")
        self.assertEqual(code, 4)
        self.assertEqual(body["error"]["code"], "conflict")
        self.assertEqual(len(os.listdir(self.notes)), 2)  # note plus INDEX.md

    def test_seventh_note_is_refused_and_nothing_is_written(self):
        for i in range(research.MAX_NOTES):
            code, body = self.new("note-%d" % i, "Note %d" % i)
            self.assertEqual(code, 0, body)
        code, body = self.new("extra", "Too many")
        self.assertEqual(code, 4)
        self.assertEqual(body["error"]["code"], "research_limit")
        self.assertFalse(os.path.exists(os.path.join(self.notes, "07-extra.md")))
        self.assertNotIn("extra", read_text(os.path.join(self.notes, "INDEX.md")))

    def test_bad_slug_is_a_usage_error(self):
        code, body = self.new("Bad Slug")
        self.assertEqual(code, 2)
        self.assertEqual(body["error"]["code"], "invalid_input")

    def test_missing_data_folder_is_not_found(self):
        shutil.rmtree(self.data)
        code, body = self.envelope(["research", "new", "landscape", "x", "--project", "demo"])
        self.assertEqual(code, 3)
        self.assertEqual(body["error"]["code"], "not_found")


class ListTests(ResearchCase):
    def test_list_prints_the_index(self):
        self.new("landscape")
        code, out, _ = run_cli(["research", "list", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertIn("- 01 landscape", out)

    def test_list_empty_says_so(self):
        code, out, _ = run_cli(["research", "list", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "no research notes\n")

    def test_list_json_gives_the_lines(self):
        self.new("landscape")
        code, body = self.envelope(["research", "list", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual(len(body["data"]["notes"]), 1)


class CheckTests(ResearchCase):
    def test_fresh_notes_pass(self):
        self.new("landscape")
        self.new("risks", "Risks")
        code, body = self.check()
        self.assertEqual(code, 0, body)
        self.assertEqual(body["data"]["notes"], 2)

    def test_check_prints_ok_in_plain_text(self):
        self.new("landscape")
        code, out, _ = run_cli(["research", "check", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "ok: 1 notes\n")

    def test_more_than_120_lines_fails(self):
        self.new("landscape")
        path = os.path.join(self.notes, "01-landscape.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.good_note() + "\n".join("line %d" % i for i in range(130)) + "\n")
        code, body = self.check()
        self.assertEqual(code, 5)
        self.assertEqual(body["error"]["code"], "invalid_data")
        self.assertIn("120", body["error"]["message"])

    def test_120_lines_is_allowed(self):
        text = self.good_note()
        while len(text.splitlines()) < 120:
            text += "filler\n"
        self.write_note("01-demo.md", text)
        self.write_note("INDEX.md", "- 01 demo — Demo — (no finding yet)\n")
        self.assertEqual(len(text.splitlines()), 120)
        code, body = self.check()
        self.assertEqual(code, 0, body)

    def test_over_6_kb_fails(self):
        self.write_note("01-demo.md", self.good_note() + "x" * (6 * 1024) + "\n")
        self.write_note("INDEX.md", "- 01 demo — Demo — (no finding yet)\n")
        code, body = self.check()
        self.assertEqual(code, 5)
        self.assertIn("6 KB", body["error"]["message"])

    def test_missing_heading_fails(self):
        self.write_note("01-demo.md", self.good_note().replace("## Decisions", "## Choices"))
        self.write_note("INDEX.md", "- 01 demo — Demo — (no finding yet)\n")
        code, body = self.check()
        self.assertEqual(code, 5)
        self.assertIn("'## Decisions'", body["error"]["message"])

    def test_bad_plan_block_is_reported_with_its_line(self):
        text = self.good_note() + "\n```roadmap-plan\nP P1 todo | Ok\nT P1.1 nope 5 haiku/low | Bad status\n```\n"
        self.write_note("01-demo.md", text)
        self.write_note("INDEX.md", "- 01 demo — Demo — (no finding yet)\n")
        code, body = self.check()
        self.assertEqual(code, 5)
        self.assertIn("roadmap-plan line 2", body["error"]["message"])

    def test_valid_plan_block_passes(self):
        text = self.good_note() + "\n```roadmap-plan\nP P1 todo | Ok\nT P1.1 todo 5 haiku/low | Fine\n```\n"
        self.write_note("01-demo.md", text)
        self.write_note("INDEX.md", "- 01 demo — Demo — (no finding yet)\n")
        code, body = self.check()
        self.assertEqual(code, 0, body)

    def test_note_missing_from_index_fails(self):
        self.write_note("01-demo.md", self.good_note())
        code, body = self.check()
        self.assertEqual(code, 5)
        self.assertIn("no line in INDEX.md", body["error"]["message"])

    def test_more_than_six_notes_fails(self):
        for i in range(7):
            self.write_note("%02d-n%d.md" % (i + 1, i), self.good_note())
        self.write_note("INDEX.md", "".join("- %02d n%d — x — y\n" % (i + 1, i) for i in range(7)))
        code, body = self.check()
        self.assertEqual(code, 5)
        self.assertIn("cap is 6", body["error"]["message"])

    def test_note_problems_are_pure(self):
        problems = research.note_problems("n.md", ("# t\n" + "\n".join(
            ["## Question", "## Findings", "## Decisions", "## Sources"])).encode("utf-8"))
        self.assertEqual(problems, [])
        problems = research.note_problems("n.md", b"# nothing here\n")
        self.assertEqual(len(problems), 4)
