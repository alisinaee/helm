"""Cursor review fixes 6, 12 and 13 (web views).

6: the task title is a button: Enter, Space and F2 start the edit; leaving the field saves or restores the title
   without moving focus back onto the title when focus goes to another control.
12: the renamed-title cache is keyed by project and task id, and entries end on expiry or when the snapshot agrees.
13: the Run panel shows the launch path with the home folder as ~; the real command is only kept for the copy button.
"""

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
DETAILS = os.path.join(VIEWS, "details.js")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TitleButtonTest(unittest.TestCase):
    def test_enter_space_and_f2_start_the_edit_from_the_title(self):
        src = read(TASKS)
        self.assertRegex(src, r'event\.key !== "F2" && event\.key !== "Enter" && event\.key !== " "')
        self.assertIn("const span = titleSpanOf(event.target);", src)

    def test_blur_does_not_refocus_the_title(self):
        src = read(TASKS)
        self.assertIn("if (refocus) ed.span.focus({ preventScroll: true });", src)
        self.assertIn('input.addEventListener("blur", function () {\n    if (editing && editing.input === input) '
                      "commitEdit(false);", src)
        self.assertIn("endEdit(ed.prior, false);", src)

    def test_enter_and_escape_keep_focus_on_the_title(self):
        src = read(TASKS)
        self.assertIn("commitEdit(true);", src)
        self.assertIn("endEdit(editing.prior, true);", src)


class RenameCacheTest(unittest.TestCase):
    def test_key_includes_the_project(self):
        src = read(TASKS)
        self.assertIn("function renameKey(project, id)", src)
        self.assertIn('return project + "\\n" + id;', src)
        self.assertIn("setShown(project, id, title);", src)

    def test_entries_end_on_expiry_or_when_the_snapshot_matches(self):
        src = read(TASKS)
        self.assertIn("function sweepRenamed(now)", src)
        self.assertIn("entry.title === task.title", src)
        self.assertIn("renamed.delete(key);", src)


class RunPathTest(unittest.TestCase):
    def test_the_real_command_never_reaches_the_markup(self):
        src = read(DETAILS)
        self.assertNotIn('data-cmd="', src)
        self.assertIn('data-project="', src)
        self.assertIn("launchByProject.get(el.getAttribute(\"data-project\"))", src)

    def test_no_inline_style_or_handler_attributes_or_innerhtml(self):
        for path in (TASKS, DETAILS):
            src = read(path)
            self.assertNotRegex(src, r"\sstyle\s*=", path)
            self.assertNotIn("innerHTML", src, path)
            self.assertNotRegex(src, r"\son[a-z]{3,}\s*=", path)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RedactPathTest(unittest.TestCase):
    def redact(self, path):
        script = (
            "import { redactPath } from " + json.dumps(DETAILS) + ";"
            "process.stdout.write(JSON.stringify(redactPath(JSON.parse(process.argv[1]))));"
        )
        proc = subprocess.run([shutil.which("node"), "--input-type=module", "-e", script, json.dumps(path)],
                              capture_output=True, text=True, check=False, cwd=REPO)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_home_folder_becomes_tilde(self):
        self.assertEqual(self.redact("/Users/ali/Works/roadmap-board"), "~/Works/roadmap-board")
        self.assertEqual(self.redact("/home/ali/code"), "~/code")
        self.assertEqual(self.redact("C:\\Users\\ali\\code"), "~\\code")

    def test_other_paths_are_unchanged(self):
        self.assertEqual(self.redact("/srv/projects/x"), "/srv/projects/x")


if __name__ == "__main__":
    unittest.main()
