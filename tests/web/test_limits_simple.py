"""The simple limits module (R7.28 A, docs/LIMITS-SIMPLE-SPEC.md): one weekly stop and one share per project.

The module is rendered in node (render_limits_simple.mjs) from synthetic view models; the source is checked for the
rules that apply to every view: no inline markup, no innerHTML, no cap editors left, and only limit.set and limit.rm.
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
SOURCE = os.path.join(WEB, "js", "views", "limits.js")
RENDER = os.path.join(TESTS, "web", "render_limits_simple.mjs")
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)
OPS = re.compile(r'run\(\s*"([a-z.]+)"')
OLD_CONTROLS = ("lim-add", "lim-preset", "lim-step", "lim-sheet", "lim-del", "lim-override", "spend-cap",
                "task.cap", "budget.set", "PRESETS", "limitsHtml", "setLimitContext", "rowsForScope", "editable",
                "previewText", "limitRowHtml", "lim-range", "lim-num", "lim-stepper")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class LimitsSimpleSource(unittest.TestCase):
    def setUp(self):
        self.src = read(SOURCE)

    def test_exports_the_names_the_other_views_import(self):
        for name in ("weeklyStopHtml", "shareRowsHtml", "limitAction", "attachLimitListeners"):
            self.assertRegex(self.src, r"export function " + name + r"\(", name)

    def test_no_cap_editor_or_old_control_is_left(self):
        for name in OLD_CONTROLS:
            self.assertNotIn(name, self.src, name)

    def test_only_limit_set_and_limit_rm_are_sent(self):
        self.assertEqual(sorted(set(OPS.findall(self.src))), ["limit.rm", "limit.set"])

    def test_no_long_lines(self):
        self.assertTrue(all(len(line) <= 120 for line in self.src.split("\n")))

    def test_no_inline_markup_and_no_innerhtml(self):
        self.assertIsNone(INLINE.search(self.src))
        self.assertNotIn("innerHTML", self.src)

    def test_handlers_are_wired_to_submit_and_enter(self):
        self.assertIn('addEventListener("submit"', self.src)
        self.assertIn("event.preventDefault()", self.src)
        self.assertIn('data-form="weekly"', self.src)
        self.assertIn('data-form="share"', self.src)


class LimitsSimpleRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run(
            [shutil.which("node"), "--experimental-default-type=module", RENDER, WEB],
            capture_output=True, text=True, check=False, timeout=60,
        )
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_weekly_stop_is_one_switch_and_one_percent(self):
        html = self.out["weekly"]
        self.assertIn('role="switch" aria-checked="true"', html)
        self.assertIn('aria-label="Weekly stop, on"', html)
        self.assertIn('data-action="lim-weekly" data-row="L4"', html)
        self.assertIn('value="95"', html)
        self.assertIn("Stop agents at", html)
        self.assertIn("of my weekly usage", html)
        self.assertIn('maxlength="3"', html)
        self.assertNotIn("rule-input", html)

    def test_weekly_stop_off_shows_the_default_and_no_remove_id(self):
        html = self.out["weeklyOff"]
        self.assertIn('aria-checked="false"', html)
        self.assertIn('value="95"', html)
        self.assertIn('data-row=""', html)

    def test_weekly_stop_does_not_repeat_the_limit_sentence(self):
        # The one sentence about the limit and the override is printed once, by tokens.js.
        self.assertNotIn("override for 1 hour", self.out["weekly"])
        self.assertNotIn("agents stop starting", self.out["weekly"])
        self.assertNotIn("stop starting", self.out["weekly"])

    def test_all_view_names_no_project_in_copy_refs(self):
        # The All view (no project route) must not carry the first project's slug into its refs or forms.
        self.assertNotIn('data-project="alpha"', self.out["weekly"])
        self.assertNotIn('data-project="alpha"', self.out["weeklyOff"])

    def test_project_stop_note_names_the_lower_own_stop(self):
        self.assertIn("alpha stops at 80% on its own.", self.out["weekly"])
        self.assertNotIn("beta stops", self.out["weekly"])

    def test_share_has_one_row_per_project_with_a_number_and_a_choice(self):
        html = self.out["share"]
        self.assertEqual(html.count('data-form="share"'), 2)
        self.assertIn('data-project="alpha"', html)
        self.assertIn('data-project="beta"', html)
        self.assertIn('value="30"', html)
        self.assertIn('data-window="day"', html)
        self.assertIn('<option value="day" selected>daily</option>', html)
        self.assertIn('<option value="week">weekly</option>', html)
        self.assertIn('placeholder="none"', html)
        self.assertNotIn("rule-input", html)
        self.assertNotIn("rg-head", html)

    def test_share_row_names_its_inputs_and_shows_state_in_words(self):
        html = self.out["share"]
        self.assertIn('id="lim-share-alpha"', html)
        self.assertIn("Limit for alpha, percent; empty for no limit", html)
        self.assertIn("Warning at 80%", html)
        self.assertIn("+ 1 CLI rules", html)
        self.assertIn("≈ 4%", html)

    def test_share_without_a_row_says_no_limit_and_is_collapsed(self):
        self.assertNotIn(" open>", self.out["shareOff"])
        self.assertIn("No limit", self.out["shareOff"])
        self.assertIn('value=""', self.out["shareOff"])

    def test_share_block_is_open_when_a_project_has_a_limit(self):
        self.assertIn('<details class="lim-block lim-share-block" open>', self.out["share"])

    def test_render_has_no_inline_markup(self):
        for key, html in self.out.items():
            self.assertIsNone(INLINE.search(html), key)


if __name__ == "__main__":
    unittest.main()
