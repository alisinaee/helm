"""R11.6: Tokens Overview and History tabs (inline SVG charts, remaining estimate, accessibility, no inline markup)."""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_tokens_charts.mjs")
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TokensChartsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run(["node", "--experimental-default-type=module", RENDER, WEB], capture_output=True,
                              text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_loading_before_the_data_arrives(self):
        self.assertIn("Loading history", self.out["before"])
        self.assertIn('data-tk="chip"', self.out["before"])

    def test_overview_totals_and_remaining_estimate(self):
        html = self.out["overview"]
        self.assertIn("Remaining work ≈ estimate", html)
        self.assertIn("≈ 90.0k", html)
        self.assertIn("R1 · One (Alpha)", html)
        self.assertIn('<li class="row-grid tk-tot">', html)
        self.assertIn("Tokens used per project", html)

    def test_history_has_every_chart_with_a_name_and_a_table(self):
        html = self.out["history"]
        for name in ("Per day by model", "Cumulative", "Model share", "Jobs per day", "Top phases and tasks",
                     "Weekly limit used"):
            self.assertIn(name, html)
        self.assertGreaterEqual(html.count('role="img"'), 8)
        self.assertGreaterEqual(html.count("<details"), 5)
        self.assertIn("data-tip=", html)
        self.assertIn('stroke-dasharray=', html)

    def test_controls(self):
        html = self.out["history"]
        for value in ("7", "30", "all"):
            self.assertIn('data-tk="range" data-value="%s"' % value, html)
        for model in ("haiku", "sonnet", "opus", "other"):
            self.assertIn('data-model="%s" aria-pressed="true"' % model, html)

    def test_markup_is_clean(self):
        for name, html in self.out.items():
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("undefined", html, name)
            self.assertNotIn("NaN", html, name)


class TokensChartsSource(unittest.TestCase):
    def test_no_innerhtml_no_raw_hex(self):
        for name in ("tokens_charts.js", "tokens_history.js"):
            with open(os.path.join(WEB, "js", "views", name), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotIn("innerHTML", src)
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", src), name)


if __name__ == "__main__":
    unittest.main()
