"""Inline title edit for task rows (R7.3b). The checks read the source and, when node is installed, call the
client-side title check in node: it must trim, reject empty and over-long titles and control characters, and
keep TITLE_MAX equal to the server's parsers.TITLE_MAX. Writes go through cmd.js run() (task.rename, with Undo)."""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
VIEWS = os.path.join(REPO, "web", "js", "views")
TASKS = os.path.join(VIEWS, "tasks.js")
API = os.path.join(REPO, "web", "js", "api.js")
PLAN_CSS = os.path.join(REPO, "web", "css", "plan.css")
PARSERS = os.path.join(REPO, "roadmap", "core", "parsers.py")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TitleEditSourceTest(unittest.TestCase):
    def test_writes_go_through_the_shared_command_path(self):
        src = read(TASKS)
        self.assertIn('import { run } from "../cmd.js";', src)
        self.assertRegex(src, r'run\("task\.rename",\s*\{\s*id:\s*id,\s*title:\s*title\s*\}')
        self.assertIn('label: id + " renamed"', src)

    def test_title_cap_matches_the_server(self):
        src = read(TASKS)
        self.assertIn("export const TITLE_MAX = 120;", src)
        self.assertRegex(read(PARSERS), r"(?m)^TITLE_MAX = 120$")

    def test_keys_and_double_click_are_wired(self):
        src = read(TASKS)
        self.assertIn('"dblclick"', src)
        self.assertIn('event.key === "Enter"', src)
        self.assertIn('event.key === "Escape"', src)
        self.assertIn('event.key !== "F2"', src)

    def test_no_inline_style_or_handler_attributes_or_innerhtml(self):
        for path in (TASKS, API):
            src = read(path)
            self.assertNotRegex(src, r"\sstyle\s*=", path)
            self.assertNotIn("innerHTML", src, path)
            self.assertNotRegex(src, r"\son[a-z]{3,}\s*=", path)

    def test_editor_reuses_an_existing_input_class(self):
        self.assertIn('input.className = "iss-input";', read(TASKS))
        self.assertRegex(read(PLAN_CSS), r"\.iss-input\s*\{[^}]*width:\s*100%")

    def test_title_span_is_focusable_and_addressable(self):
        src = read(TASKS)
        self.assertIn('tabindex="0" role="button" ', src)
        self.assertIn('aria-label="Edit title for ', src)
        self.assertIn('data-tt-id="', src)


class TitleCheckTest(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        if not self.node:
            self.skipTest("node is not installed")

    def check(self, value):
        script = (
            "import { checkTitle, TITLE_MAX } from " + json.dumps(TASKS) + ";"
            "const v = JSON.parse(process.argv[1]);"
            "process.stdout.write(JSON.stringify({ r: checkTitle(v), max: TITLE_MAX }));"
        )
        proc = subprocess.run([self.node, "--input-type=module", "-e", script, json.dumps(value)],
                              capture_output=True, text=True, check=False, cwd=REPO)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_trims_and_accepts_a_normal_title(self):
        out = self.check("  Plan the release  ")
        self.assertEqual(out["r"], {"title": "Plan the release"})
        self.assertEqual(out["max"], 120)

    def test_rejects_empty_and_blank(self):
        self.assertIn("empty", self.check("")["r"]["error"])
        self.assertIn("empty", self.check("   ")["r"]["error"])

    def test_limit_is_120_characters_counted_as_code_points(self):
        self.assertEqual(self.check("a" * 120)["r"], {"title": "a" * 120})
        self.assertIn("121", self.check("a" * 121)["r"]["error"])
        self.assertEqual(self.check("\U0001F600" * 120)["r"], {"title": "\U0001F600" * 120})

    def test_rejects_control_characters(self):
        self.assertIn("not allowed", self.check("a\tb")["r"]["error"])
        self.assertIn("not allowed", self.check("a\nb")["r"]["error"])


if __name__ == "__main__":
    unittest.main()
