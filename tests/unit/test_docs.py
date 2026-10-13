"""The documented commands run: tools/check_docs.py passes on the shipped docs, and its parser and judge are right."""

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(REPO, "tools", "check_docs.py")


def _load_tool():
    spec = importlib.util.spec_from_file_location("check_docs", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocumentedCommands(unittest.TestCase):
    def test_every_documented_command_runs(self):
        proc = subprocess.run([sys.executable, TOOL], cwd=REPO, capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("checked", proc.stdout)
        self.assertIn(": 0 failed", proc.stdout)


class Extraction(unittest.TestCase):
    def setUp(self):
        self.tool = _load_tool()
        self.tmp = tempfile.TemporaryDirectory(prefix="docs-test-")
        self.addCleanup(self.tmp.cleanup)

    def _doc(self, text):
        path = os.path.join(self.tmp.name, "doc.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_only_roadmap_lines_in_shell_fences_are_taken(self):
        path = self._doc(
            "intro roadmap is not a command here\n"
            "```bash\n"
            "roadmap job list --json\n"
            "  roadmap version   # print the version\n"
            "echo roadmap is not run\n"
            "```\n"
            "```text\n"
            "roadmap project add nope\n"
            "```\n"
            "```sh\n"
            "roadmap doctor\n"
            "```\n"
        )
        found = self.tool.extract(path, "doc.md")
        self.assertEqual([c.argv for c in found], [["job", "list", "--json"], ["version"], ["doctor"]])
        self.assertEqual([c.line for c in found], [3, 4, 11])

    def test_help_only_commands_are_recognised_after_flags(self):
        self.assertTrue(self.tool.is_help_only(["service", "install"]))
        self.assertTrue(self.tool.is_help_only(["--json", "hooks", "install", "my-app"]))
        self.assertTrue(self.tool.is_help_only(["usage", "sync"]))
        self.assertFalse(self.tool.is_help_only(["usage", "show"]))
        self.assertFalse(self.tool.is_help_only(["job", "start", "x", "haiku"]))

    def test_unknown_command_fails_the_check(self):
        path = self._doc("```bash\nroadmap nosuchcommand\n```\n")
        results = self.tool.check(files=[path], root_dir="/")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].exit, 2)
        self.assertIsNotNone(results[0].problem)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.tool.report(results), 1)

    def test_stub_commands_are_only_checked_with_help(self):
        path = self._doc("```bash\nroadmap phone status\n```\n")
        results = self.tool.check(files=[path], root_dir="/")
        self.assertEqual(results[0].mode, "help")
        self.assertIsNone(results[0].problem)  # help-only commands are never run for real

        path = self._doc("```bash\nroadmap open --json\n```\n")
        results = self.tool.check(files=[path], root_dir="/")
        self.assertEqual(results[0].mode, "help")  # open is listed as help-only until it is built

    def test_a_working_command_passes(self):
        path = self._doc("```bash\nroadmap version\n```\n")
        results = self.tool.check(files=[path], root_dir="/")
        self.assertIsNone(results[0].problem)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.tool.report(results), 0)


if __name__ == "__main__":
    unittest.main()
