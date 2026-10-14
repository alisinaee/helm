"""tools/install-skills.py: fresh install, backup of an existing skill folder, dry run, and refusal of an invalid draft.

Every test uses a temporary target (and, for the invalid case, a temporary copy of the drafts), never ~/.claude.
"""

import contextlib
import datetime
import importlib.util
import io
import os
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(REPO, "tools", "install-skills.py")
NOW = datetime.datetime(2026, 10, 14, 8, 0, 0)


def _load_tool():
    spec = importlib.util.spec_from_file_location("install_skills", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOLS = _load_tool()
GOOD = (
    "---\nname: %s\ndescription: A test skill that runs a documented command.\n---\n\n"
    "```bash\nroadmap status --json\n```\n"
)


class InstallSkillsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="wp37-skills-")
        self.tmp = self._tmp.name
        self.target = os.path.join(self.tmp, "skills")

    def tearDown(self):
        self._tmp.cleanup()

    def run_tool(self, **kwargs):
        lines = []
        code = TOOLS.run(self.target, now=NOW, out=lines.append, **kwargs)
        return code, "\n".join(lines)

    def make_root(self, bodies):
        """A drafts tree with one SKILL.md per (name, rel path) in TOOLS.SKILLS, the body from bodies[name]."""
        root = os.path.join(self.tmp, "repo")
        for name, rel in TOOLS.SKILLS:
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(bodies.get(name, GOOD % name))
        return root

    def test_fresh_install_copies_all_three_skills(self):
        code, out = self.run_tool(dry_run=False, yes=False)
        self.assertEqual(code, TOOLS.EXIT_OK, out)
        for name, rel in TOOLS.SKILLS:
            installed = os.path.join(self.target, name, "SKILL.md")
            with open(installed, "rb") as fh, open(os.path.join(REPO, rel), "rb") as src:
                self.assertEqual(fh.read(), src.read(), name)
        self.assertIn("done: 3 skill(s) installed", out)
        self.assertEqual(sorted(os.listdir(self.target)), sorted(n for n, _ in TOOLS.SKILLS))

    def test_existing_folder_is_refused_without_yes_and_left_alone(self):
        existing = os.path.join(self.target, "roadmap-update")
        os.makedirs(existing)
        with open(os.path.join(existing, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("my own version\n")
        code, out = self.run_tool(dry_run=False, yes=False)
        self.assertEqual(code, TOOLS.EXIT_REFUSED, out)
        self.assertIn("--yes", out)
        with open(os.path.join(existing, "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "my own version\n")
        self.assertFalse(os.path.exists(os.path.join(self.target, "roadmap-dashboard")))

    def test_yes_backs_up_the_existing_folder_then_installs(self):
        existing = os.path.join(self.target, "roadmap-update")
        os.makedirs(existing)
        with open(os.path.join(existing, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("my own version\n")
        code, out = self.run_tool(dry_run=False, yes=True)
        self.assertEqual(code, TOOLS.EXIT_OK, out)
        backup = os.path.join(self.target, "roadmap-update.bak-20261014-080000")
        with open(os.path.join(backup, "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "my own version\n")
        with open(os.path.join(existing, "SKILL.md"), encoding="utf-8") as fh:
            self.assertIn("name: roadmap-update", fh.read())

    def test_dry_run_prints_the_plan_and_changes_nothing(self):
        code, out = self.run_tool(dry_run=True, yes=False)
        self.assertEqual(code, TOOLS.EXIT_OK, out)
        self.assertIn("would install roadmap-dashboard", out)
        self.assertIn("dry run: nothing changed", out)
        self.assertFalse(os.path.exists(self.target))

    def test_dry_run_with_an_existing_folder_names_the_backup(self):
        os.makedirs(os.path.join(self.target, "roadmap-dashboard"))
        code, out = self.run_tool(dry_run=True, yes=True)
        self.assertEqual(code, TOOLS.EXIT_OK, out)
        self.assertIn("would back up", out)
        self.assertTrue(os.path.isdir(os.path.join(self.target, "roadmap-dashboard")))
        self.assertFalse(os.path.exists(os.path.join(self.target, "roadmap-dashboard.bak-20261014-080000")))

    def test_invalid_draft_refuses_the_whole_install(self):
        bad = {"roadmap-update": "---\nname: roadmap-update\n---\n\n```bash\nroadmap nosuch-command\n```\n"}
        root = self.make_root(bad)
        code, out = self.run_tool(root=root, skills=TOOLS.SKILLS, dry_run=False, yes=False)
        self.assertEqual(code, TOOLS.EXIT_INVALID, out)
        self.assertIn("nothing installed", out)
        self.assertIn("description", out)
        self.assertFalse(os.path.exists(self.target))

    def test_unknown_roadmap_command_in_a_draft_is_reported(self):
        bad = {"roadmap-plan-new": "---\nname: roadmap-plan-new\ndescription: x\n---\n\n```sh\nroadmap nosuch\n```\n"}
        root = self.make_root(bad)
        problems = TOOLS.validate("roadmap-plan-new", os.path.join(root, TOOLS.SKILLS[2][1]))
        self.assertEqual(len(problems), 1)
        self.assertIn("line 7", problems[0])

    def test_name_must_match_the_folder(self):
        root = self.make_root({"roadmap-dashboard": GOOD % "some-other-name"})
        code, out = self.run_tool(root=root, skills=TOOLS.SKILLS, dry_run=True, yes=False)
        self.assertEqual(code, TOOLS.EXIT_INVALID, out)
        self.assertIn("is not 'roadmap-dashboard'", out)

    def test_roadmap_lines_outside_shell_fences_are_not_checked(self):
        text = (
            "---\nname: a\ndescription: b\n---\n\n"
            "roadmap nosuch is prose, not a command\n\n```text\nroadmap nosuch\n```\n"
        )
        self.assertEqual(TOOLS.roadmap_lines(text), [])

    def test_the_real_drafts_pass_validation(self):
        for name, rel in TOOLS.SKILLS:
            self.assertEqual(TOOLS.validate(name, os.path.join(REPO, rel)), [], name)

    def test_main_dry_run_against_a_temp_target_exits_zero(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = TOOLS.main(["--dry-run", "--target", self.target])
        self.assertEqual(code, 0, out.getvalue())
        self.assertFalse(os.path.exists(self.target))


if __name__ == "__main__":
    unittest.main()
