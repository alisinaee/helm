"""Checks for the copy-reference button in the Details drawer (R7.12, package P3).

The task header of the Details tab carries one copy button: a real button with data-action="copy-ref", a valid rb:
ref for the task, an aria-label, and no path in the ref or the summary. The render comes from tests/web/render_panel.mjs
(the same node run test_panel.py uses), so no new render script is needed. The node check is skipped when node is not
installed; the static check reads details.js and runs without node.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_panel.mjs")
SNAPSHOT = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
DETAILS_JS = os.path.join(WEB, "js", "views", "details.js")

REF_RE = re.compile(r"^rb:[a-z0-9-]+(/[a-z]+/[A-Za-z0-9._-]+)?$")
COPY = re.compile(r'<button type="button" class="ref-copy" data-action="copy-ref" data-ref="([^"]*)" '
                  r'data-sum="([^"]*)" aria-label="([^"]*)"')
BUTTON_OR_LINK = re.compile(r"<(button|a)\b[^>]*>(.*?)</\1>", re.DOTALL)
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)


def render():
    node = shutil.which("node")
    proc = subprocess.run(
        [node, "--experimental-default-type=module", RENDER, WEB, SNAPSHOT],
        capture_output=True, text=True, check=False, timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError("render failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def copy_buttons(html):
    return COPY.findall(html)


class DetailsRefStaticTests(unittest.TestCase):

    def test_details_imports_the_ref_helper_and_no_raw_markup(self):
        with open(DETAILS_JS, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('import { copyButton, refSummary } from "../ref.js";', src)
        self.assertNotIn("innerHTML", src)
        self.assertNotIn("execCommand", src)


@unittest.skipUnless(shutil.which("node"), "node is not installed; the Details ref render check is skipped")
class DetailsRefRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = render()

    def test_task_details_header_has_one_copy_button_with_a_valid_ref(self):
        html = self.out["detailsTask"]
        buttons = copy_buttons(html)
        self.assertEqual(len(buttons), 1)
        ref, summary, label = buttons[0]
        self.assertRegex(ref, REF_RE)
        self.assertEqual(ref.split("/")[-1], "P0.1")
        self.assertTrue(label.startswith("Copy reference to "), label)
        self.assertTrue(summary.startswith("task "), summary)

    def test_ref_and_summary_carry_no_absolute_path_or_home_marker(self):
        for name in ("detailsTask",):
            for ref, summary, _label in copy_buttons(self.out[name]):
                for text in (ref, summary):
                    self.assertNotIn("/Users/", text)
                    self.assertNotIn("~", text)

    def test_copy_button_is_not_nested_inside_another_button_or_link(self):
        html = self.out["detailsTask"]
        for outer in BUTTON_OR_LINK.finditer(html):
            self.assertNotIn('data-action="copy-ref"', outer.group(2), outer.group(0)[:80])

    def test_copy_button_is_present_in_the_task_header_only(self):
        html = self.out["detailsTask"]
        head = html.split('<h3 class="d-title">', 1)[0]
        self.assertEqual(len(copy_buttons(head)), 1)

    def test_no_inline_style_or_handlers_in_the_header(self):
        html = self.out["detailsTask"]
        head = html.split('<h3 class="d-title">', 1)[0]
        self.assertIsNone(INLINE.search(head))

    def test_issue_details_have_no_copy_button(self):
        self.assertEqual(copy_buttons(self.out["detailsIssue"]), [])


if __name__ == "__main__":
    unittest.main()
