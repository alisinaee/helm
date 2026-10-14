"""Tests for the packaged skill templates: size limit, frontmatter, budget lines, and every roadmap command they name.

A command counts when it sits in a fenced block (a line starting with "roadmap ") or in backticks in prose. Each one
must parse with roadmap.cli.build_parser(), so a skill never names a command that does not exist.
"""

import os
import re
import shlex
import unittest

from roadmap.cli import build_parser
from roadmap.commands import skills
from roadmap.errors import RoadmapError

MAX_BYTES = 3200
FENCE = re.compile(r"^```")
INLINE = re.compile(r"`(roadmap [^`]+)`")


def _read(folder):
    with open(os.path.join(folder, "SKILL.md"), "r", encoding="utf-8") as fh:
        return fh.read()


def _commands(text):
    """Every roadmap command in a template: fenced lines and inline code spans, in order."""
    found = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence and line.startswith("roadmap "):
            found.append(line.strip())
    found.extend(INLINE.findall(text))
    return found


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.templates = dict(skills.templates())

    def test_both_skills_are_packaged(self):
        self.assertEqual(sorted(self.templates), ["roadmap-lead", "roadmap-worker"])

    def test_every_skill_is_at_most_3200_bytes(self):
        for name, folder in self.templates.items():
            size = len(_read(folder).encode("utf-8"))
            self.assertLessEqual(size, MAX_BYTES, name)

    def test_frontmatter_names_the_folder_and_gives_a_trigger(self):
        for name, folder in self.templates.items():
            text = _read(folder)
            self.assertTrue(text.startswith("---\nname: " + name + "\ndescription: Use when "), name)
            self.assertIn("\n---\n", text[4:], name)

    def test_every_workflow_section_states_a_token_budget(self):
        for name, folder in self.templates.items():
            sections = re.split(r"^## ", _read(folder), flags=re.M)[1:]
            with_commands = [s for s in sections if "```" in s]
            self.assertTrue(with_commands, name)
            for section in with_commands:
                self.assertIn("budget", section.splitlines()[0], name)

    def test_every_roadmap_command_in_the_templates_parses(self):
        parser = build_parser()
        checked = 0
        for name, folder in self.templates.items():
            for line in _commands(_read(folder)):
                argv = [token if not re.match(r"^<.*>$", token) else "x" for token in shlex.split(line)]
                try:
                    parser.parse_args(argv[1:])
                except (RoadmapError, SystemExit) as exc:
                    self.fail("%s: %r does not parse (%s)" % (name, line, exc))
                checked += 1
        self.assertGreaterEqual(checked, 30)

    def test_worker_names_the_ten_core_commands(self):
        text = _read(self.templates["roadmap-worker"])
        for needle in ("roadmap status", "roadmap inbox", "roadmap task list --status todo --limit 10",
                       "roadmap task start", "roadmap task done", "roadmap ask ", "roadmap ask get",
                       "roadmap issue new", "roadmap comment", "roadmap subtask done",
                       "roadmap rules show --for"):
            self.assertIn(needle, text)

    def test_lead_keeps_phase_approval_and_limits_for_the_person(self):
        text = _read(self.templates["roadmap-lead"])
        self.assertIn("Phase approval is the person's job", text)
        self.assertIn("limit set", text)
        self.assertIn("roadmap budget show", text)
        self.assertIn("roadmap rules show --for P1.2 --role worker", text)
        self.assertIn("paste", text)

    def test_neither_skill_tells_the_agent_to_edit_data_files(self):
        for name, folder in self.templates.items():
            self.assertIn("Never open or edit `docs/tasks.json`", _read(folder), name)
