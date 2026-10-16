"""UX group C checks (R8.13, R8.14, R8.16, R8.17): the Rules add form shows the budget field only for a budget rule,
its checks are inline next to the field, an empty group offers an action, Sync reports its counts in a toast; the
The Rules render runs in node (skipped when node is not installed), the rest reads the sources.
"""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
VIEWS = os.path.join(WEB, "js", "views")
RENDER = os.path.join(TESTS, "web", "render_ux_rules.mjs")


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class RulesSource(unittest.TestCase):
    def setUp(self):
        self.src = read(os.path.join(VIEWS, "rules.js"))

    def test_empty_group_offers_an_action(self):
        self.assertIn("function emptyGroupHtml(activeTab)", self.src)
        self.assertIn("Show all rules", self.src)
        self.assertIn("Add the first one in the form below.", self.src)
        self.assertNotIn('emptyHtml("No rules in this group.", "")', self.src)

    def test_budget_field_shows_for_a_budget_rule_only(self):
        self.assertIn("data-rule-budget hidden", self.src)
        self.assertIn('budget.hidden = t.value !== "budget"', self.src)
        self.assertIn('kind === "budget" && raw !== ""', self.src)

    def test_checks_are_inline_not_only_a_toast(self):
        self.assertIn('data-err-for="text"', self.src)
        self.assertIn('data-err-for="value"', self.src)
        self.assertIn('aria-describedby="rule-text-err rule-count"', self.src)
        self.assertIn('aria-describedby="rule-value-err"', self.src)
        self.assertNotIn("Enter the rule text first.", self.src)
        self.assertIn("aria-invalid", self.src)

    def test_jargon_label_is_plain(self):
        self.assertNotIn("Or phase:ID or task:ID", self.src)
        self.assertIn("Or one task or phase (e.g. task:R8.13)", self.src)

    def test_sync_reports_the_counts(self):
        self.assertIn('postJson("/api/v1/cmd"', self.src)
        self.assertIn("Nothing changed.", self.src)
        self.assertIn("added, ", self.src)
        self.assertIn('"Sync to CLAUDE.md failed: "', self.src)

    def test_copy_buttons_are_kept(self):
        self.assertIn("copyButton(\"rule\"", self.src)
        self.assertIn("copyButton(\"section\", \"rules.list\"", self.src)


class AdminCssRule(unittest.TestCase):
    def test_error_line_uses_tokens(self):
        css = read(os.path.join(WEB, "css", "admin.css"))
        self.assertIn(".rule-err {", css)
        self.assertIn("color: var(--danger)", css)

    def test_rule_rows_keep_the_phone_collapse_from_row_grid(self):
        css = read(os.path.join(WEB, "css", "admin.css"))
        self.assertNotIn(".lim-row, .rule-row { display: grid", css)
        self.assertIn(".rule-text { white-space: normal; }", css)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RulesRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run(
            [shutil.which("node"), "--experimental-default-type=module", RENDER, WEB],
            capture_output=True, text=True, check=False, timeout=60,
        )
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)
        cls.html = cls.out["all"]

    def test_budget_field_is_hidden_until_kind_is_budget(self):
        self.assertIn('<label class="lim-field" data-rule-budget hidden>', self.html)
        self.assertNotIn("Budget in thousands", self.html)

    def test_error_slots_exist_and_are_empty(self):
        self.assertIn('<p class="rule-err" id="rule-text-err" data-err-for="text"></p>', self.html)
        self.assertIn('<p class="rule-err" id="rule-value-err" data-err-for="value"></p>', self.html)

    def test_copy_buttons_stay_on_each_rule_row(self):
        self.assertIn("copy-ref", self.html)

    def test_an_empty_group_offers_a_way_out(self):
        empty = self.out["phase"]
        self.assertIn("No rules in this group.", empty)
        self.assertIn('data-action="rule-tab" data-tab="all"', empty)
        self.assertIn("Show all rules", empty)


if __name__ == "__main__":
    unittest.main()
