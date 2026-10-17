"""Checks for the simple Tokens screen (R7.28 B): the section order, the usage band with the manual form and the
no-token message, the weekly stop and share rows (from limits.js), the one-sentence limit note with the 1-hour override
only when a limit is reached, the read-only spend grid, and what was removed (meters with pace, spend caps, the override
panel, the accuracy explainer). Node renders web/js/views/tokens.js with synthetic snapshots. When limits.js does not
yet export weeklyStopHtml and shareRowsHtml, a stub is put in a temporary copy of web/ so the test still runs. The node
checks are skipped when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
VIEWS = os.path.join(WEB, "js", "views")
RENDER = os.path.join(TESTS, "web", "render_tokens_simple.mjs")

INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)
STUB = """export function weeklyStopHtml(vm) { return '<p class="stop-mark">STOP-MARK</p>'; }
export function shareRowsHtml(vm) { return '<p class="share-mark">SHARE-MARK</p>'; }
"""
GONE = ["mtick", "paceAt", "At this pace", "Save cap", "Token limit", "Top 5 tasks", "lim-override",
        "Accuracy", "How these limits", "Read only", "lim-preset", "Stay under 10%", "data-state=\"none\""]


def real_limits_exports():
    with open(os.path.join(VIEWS, "limits.js"), encoding="utf-8") as fh:
        src = fh.read()
    return "export function weeklyStopHtml" in src and "export function shareRowsHtml" in src


def render_web_dir():
    """The web directory to render from: the repo itself, or a temporary copy with a stub limits.js."""
    if real_limits_exports():
        return WEB, None
    tmp = tempfile.mkdtemp(prefix="tokens-simple-")
    target = os.path.join(tmp, "web")
    shutil.copytree(WEB, target)
    with open(os.path.join(target, "js", "views", "limits.js"), "w", encoding="utf-8") as fh:
        fh.write(STUB)
    return target, tmp


class TokensSimpleRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node is not installed; the Tokens render check is skipped")
        web_dir, cls.tmp = render_web_dir()
        proc = subprocess.run([node, "--experimental-default-type=module", RENDER, web_dir],
                              capture_output=True, text=True, check=False, timeout=60)
        if cls.tmp:
            shutil.rmtree(cls.tmp, ignore_errors=True)
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_section_order_is_the_spec_order(self):
        html = self.out["project"]
        order = ['aria-label="Usage now"', 'aria-label="Usage stops"', "Share per project", 'aria-label="At the limit"',
                 "Spend"]
        positions = [html.index(name) for name in order]
        self.assertEqual(positions, sorted(positions))

    def test_usage_band_has_the_manual_form(self):
        html = self.out["project"]
        self.assertIn("Enter usage", html)
        self.assertIn("data-usage-entry", html)
        self.assertIn('data-focus="usage-save"', html)

    def test_no_token_case_says_so_in_plain_words(self):
        html = self.out["noToken"]
        self.assertNotIn("/login", html)
        self.assertIn('>Sync now<', html)

    def test_weekly_stop_and_share_come_from_limits(self):
        if not real_limits_exports():
            self.assertIn("STOP-MARK", self.out["project"])
        self.assertIn('aria-label="Usage stops"', self.out["project"])  # R11.126: limits_v2.js
        self.assertIn("Share per project", self.out["project"])

    def test_one_sentence_about_the_limit(self):
        self.assertIn("At the limit, agents stop starting new jobs. Override for 1 hour lets them run again.",
                      self.out["project"])

    def test_override_button_only_when_a_limit_is_reached(self):
        self.assertIn('data-action="override" data-project="alpha"', self.out["blocked"])
        self.assertIn('aria-label="Override for 1 hour, alpha"', self.out["blocked"])
        self.assertNotIn('data-action="override"', self.out["project"])
        self.assertIn('data-action="override" data-project="alpha"', self.out["global"])

    def test_spend_is_a_read_only_right_aligned_grid(self):
        html = self.out["global"]
        for head in ("Project", "Tokens used", "Share of weekly", "Resets"):
            self.assertIn('<span class="rg-' + ("t" if head == "Project" else "num") + '">' + head + "</span>", html)
        self.assertIn('<li class="row-grid tk-spend">', html)
        self.assertIn('<span class="rg-num num">', html)
        self.assertIn("≈ ", html)
        self.assertNotIn("<input", html[html.index("Spend"):])

    def test_spend_copy_reference_kept_for_one_project(self):
        self.assertIn('data-ref="rb:splitnet/section/tokens.spend"', self.out["project"])
        self.assertNotIn("/section/tokens.spend", self.out["global"])

    def test_removed_parts_are_gone(self):
        for name, html in self.out.items():
            for word in GONE:
                self.assertNotIn(word, html, "%s: %s" % (name, word))

    def test_only_the_accuracy_line_remains(self):
        self.assertIn("Percentages are estimates; token counts are exact.", self.out["project"])

    def test_no_inline_markup_and_no_undefined(self):
        for name, html in self.out.items():
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("undefined", html, name)
            self.assertNotIn("NaN", html, name)

    def test_empty_state_says_so_in_plain_words(self):
        self.assertIn("No projects yet.", self.out["empty"])

    def test_every_button_has_a_name(self):
        for name, html in self.out.items():
            for m in re.finditer(r"<button\b[^>]*>(.*?)</button>", html):
                opening = m.group(0)
                self.assertTrue("aria-label=" in opening or m.group(1).strip(), name)

    def test_limit_sentence_is_printed_once(self):
        html = self.out["blocked"]
        self.assertEqual(html.count("agents stop starting new jobs"), 1)
        self.assertEqual(self.out["project"].count("agents stop starting"), 1)

    def test_all_view_names_no_project_in_the_weekly_stop(self):
        # The All view has no project route: its weekly stop form and its top bar carry no slug.
        self.assertIn('aria-label="Usage stops"', self.out["global"])  # R11.126: account-wide cards carry no slug
        self.assertNotIn('data-form="weekly"', self.out["global"])
        self.assertNotIn('data-project="splitnet"', self.out["topbarAll"])
        self.assertNotIn('data-project="alpha"', self.out["topbarAll"])

    def test_top_bar_shows_5h_and_week_mini_bars_with_the_stop_tick(self):
        # R11.129: the weekly text line became two mini bars; the stop is the tick on each bar and the title.
        top = self.out["topbar"]
        self.assertIn('data-win="5h"', top)
        self.assertIn('<span class="mini" data-win="w" title="Week 63%, stop at 95%', top)
        self.assertIn('<span class="mini-tick" data-pct="95">', top)
        self.assertIn('title="Week 63%, stop at 95%', self.out["topbarAll"])

    def test_top_bar_says_off_and_unknown_in_words(self):
        # With no stop the title says "no stop" in words; an unknown week says "unknown" in the bar.
        self.assertIn('title="Week 12%, no stop', self.out["topbarOff"])
        self.assertNotIn("mini-tick", self.out["topbarOff"])
        self.assertIn('<span class="mini is-unknown" data-win="w"', self.out["topbarUnknown"])
        self.assertIn('<span class="mini-v">unknown</span>', self.out["topbarUnknown"])


class TokensSimpleSource(unittest.TestCase):

    def setUp(self):
        with open(os.path.join(VIEWS, "tokens.js"), encoding="utf-8") as fh:
            self.src = fh.read()

    def test_no_innerhtml_and_no_long_lines(self):
        self.assertNotIn("innerHTML", self.src)
        self.assertTrue(all(len(line) <= 120 for line in self.src.split("\n")))

    def test_top_bar_source_is_short_lined_and_draws_mini_bars_without_innerhtml(self):
        with open(os.path.join(VIEWS, "topbar.js"), encoding="utf-8") as fh:
            top = fh.read()
        self.assertTrue(all(len(line) <= 120 for line in top.split("\n")))
        self.assertNotIn("innerHTML", top)
        self.assertIn("function miniHtml(", top)  # R11.129: the 5h and W bars are drawn by one helper

    def test_keeps_the_route_export(self):
        self.assertIn("export function sectionView(vm)", self.src)

    def test_no_caps_or_override_handlers_left(self):
        for word in ("spend-cap", "task.cap", "budget.set", "lim-override", "control.override", "accountHtml"):
            self.assertNotIn(word, self.src)


if __name__ == "__main__":
    unittest.main()
