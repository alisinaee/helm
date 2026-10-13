"""Tests for agent-guide (WP17): the output size, every roadmap command named in the guide and the two skill drafts
parses with roadmap.cli.build_parser(), and the skill files keep their line caps and frontmatter."""

import json
import os
import re
import shlex
import unittest

from roadmap.cli import build_parser
from roadmap.core import guide
from tests.unit.test_project_support import run_cli

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_DIR = os.path.join(REPO, "docs", "skill-draft")
UPDATE_SKILL = os.path.join(SKILL_DIR, "roadmap-update", "SKILL.md")
PLAN_SKILL = os.path.join(SKILL_DIR, "roadmap-plan-new", "SKILL.md")
NOT_BUILT = ("roadmap open", "roadmap phone")


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def commands_in(text):
    """Every command line in the text: lines that start with 'roadmap ' and backtick spans that do."""
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("roadmap "):
            found.append(stripped)
        for span in re.findall(r"`([^`]+)`", line):
            if span.startswith("roadmap "):
                found.append(span)
    return found


def as_argv(command):
    """Turn a documented command into argv for the parser: placeholders become X, optional brackets go."""
    text = re.sub(r"<[^>]*>", "X", command)
    text = text.replace("[", " ").replace("]", " ")
    words = shlex.split(text)
    assert words[0] == "roadmap", command
    return words[1:]


class GuideOutputTests(unittest.TestCase):
    def test_guide_is_at_most_40_lines(self):
        self.assertLessEqual(len(guide.lines()), guide.GUIDE_MAX_LINES)
        self.assertLessEqual(len(guide.lines()), 40)

    def test_command_prints_the_guide(self):
        code, out, _ = run_cli(["agent-guide"])
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out.splitlines()), 40)
        self.assertEqual(out.splitlines(), guide.lines())

    def test_command_json_gives_the_lines(self):
        code, out, _ = run_cli(["agent-guide", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["lines"], guide.lines())

    def test_guide_names_the_rules_and_research_layout(self):
        text = "\n".join(guide.lines())
        self.assertIn("docs/tasks.json", text)
        self.assertIn("next:", text)
        self.assertIn("--dry-run", text)
        self.assertIn("docs/research/NN-slug.md", text)
        self.assertIn("Token estimate", text)

    def test_guide_lists_eight_or_more_commands_and_three_plan_examples(self):
        commands = commands_in("\n".join(guide.lines()))
        self.assertGreaterEqual(len(commands), 8)
        examples = [line for line in guide.lines() if line.startswith("Example: ")]
        self.assertEqual(len(examples), 3)


class CommandsParseTests(unittest.TestCase):
    def check_parses(self, label, text):
        commands = commands_in(text)
        self.assertTrue(commands, label + " names no commands")
        for command in commands:
            with self.subTest(source=label, command=command):
                for banned in NOT_BUILT:
                    self.assertFalse(command.startswith(banned), command)
                build_parser().parse_args(as_argv(command))

    def test_every_command_in_the_guide_parses(self):
        self.check_parses("agent-guide", "\n".join(guide.lines()))

    def test_every_command_in_roadmap_update_parses(self):
        self.check_parses("roadmap-update", read(UPDATE_SKILL))

    def test_every_command_in_roadmap_plan_new_parses(self):
        self.check_parses("roadmap-plan-new", read(PLAN_SKILL))

    def test_guide_and_skills_do_not_name_unbuilt_commands(self):
        for label, text in (("guide", "\n".join(guide.lines())), ("update", read(UPDATE_SKILL)),
                            ("plan", read(PLAN_SKILL))):
            for banned in NOT_BUILT:
                self.assertNotIn(banned, text, label)


class SkillShapeTests(unittest.TestCase):
    def frontmatter(self, text):
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match, "no frontmatter")
        fields = {}
        for line in match.group(1).splitlines():
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        return fields

    def test_roadmap_update_is_at_most_60_lines_with_trigger(self):
        text = read(UPDATE_SKILL)
        self.assertLessEqual(len(text.splitlines()), 60)
        fields = self.frontmatter(text)
        self.assertEqual(fields["name"], "roadmap-update")
        self.assertIn("Never open docs/tasks.json", fields["description"])

    def test_roadmap_plan_new_is_at_most_90_lines_with_trigger(self):
        text = read(PLAN_SKILL)
        self.assertLessEqual(len(text.splitlines()), 90)
        fields = self.frontmatter(text)
        self.assertEqual(fields["name"], "roadmap-plan-new")
        self.assertIn("Research first", fields["description"])

    def test_skill_draft_section_4_points_to_the_skills_and_cli(self):
        text = read(os.path.join(SKILL_DIR, "SKILL.md"))
        start = text.index("## 4. ")
        end = text.index("## 5. ")
        section = text[start:end].strip().splitlines()
        self.assertLessEqual(len(section), 6)
        self.assertIn("roadmap-update", "\n".join(section))
        self.assertIn("roadmap task", "\n".join(section))


if __name__ == "__main__":
    unittest.main()
