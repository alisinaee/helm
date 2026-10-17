"""R7.63: the top bar, the Tokens usage band and the weekly limit row tell the same truth. A stale reading shows
"Week unknown" with its age and an Enter usage action, the stop value (85%) still shows, and no old percent (weekly or
5-hour) is printed as current. Node renders the fixture tests/web/render_tokens_simple.mjs (truth cases); the checks
are skipped when node is not installed.
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
RENDER = os.path.join(TESTS, "web", "render_tokens_simple.mjs")
VIEWS = os.path.join(WEB, "js", "views")


class TokensTruthRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node is not installed; the truth render check is skipped")
        proc = subprocess.run([node, "--experimental-default-type=module", RENDER, WEB],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_stale_top_bar_says_unknown_with_age_and_the_stop(self):
        # R11.129: the age is written out beside the bars (not only in a title), in warning colour.
        self.assertIn('title="Week unknown, stop at 85%; updated stale 31h"', self.out["staleTop"])
        self.assertIn('<span class="top-age chip-warning">stale 31h</span>', self.out["staleTop"])

    def test_stale_top_bar_offers_enter_usage_on_the_tokens_screen(self):
        self.assertIn('<a class="btn top-enter" href="#/p/splitnet/tokens"', self.out["staleTop"])
        self.assertIn(">Enter usage</a>", self.out["staleTop"])

    def test_fresh_top_bar_shows_the_share_and_no_action(self):
        self.assertIn('title="Week 63%, stop at 85%; updated 1m ago"', self.out["freshTop"])
        self.assertIn('<span class="mini-tick" data-pct="85">', self.out["freshTop"])
        self.assertNotIn("top-enter", self.out["freshTop"])
        self.assertNotIn("stale", self.out["freshTop"])

    def test_a_half_hour_old_reading_is_still_fresh_under_ninety_minutes(self):
        self.assertIn('title="Week 63%, stop at 85%; updated 30m ago"', self.out["midTop"])
        self.assertNotIn("is-stale", self.out["midTop"])
        self.assertNotIn("top-enter", self.out["midTop"])

    def test_stale_tokens_limit_row_is_unknown_like_the_top_bar(self):
        html = self.out["staleTokens"]
        self.assertIn('aria-label="Usage stops"', html)  # R11.126: the stop cards load their own data
        self.assertNotIn("Stopped", html)

    def test_stale_tokens_band_has_no_old_percent_and_says_its_age(self):
        html = self.out["staleTokens"]
        self.assertNotIn("82%", html)
        self.assertNotIn("34%", html)
        self.assertIn("Usage is 31 h old, so the weekly share is unknown. Enter usage below.", html)

    def test_fresh_tokens_shows_the_share_the_stop_and_no_note(self):
        html = self.out["freshTokens"]
        self.assertIn("63%", html)
        self.assertIn('aria-label="Usage stops"', html)
        self.assertNotIn("so the weekly share is unknown", html)

    def test_no_inline_markup_and_no_undefined(self):
        for name in ("staleTop", "staleTokens", "freshTop", "freshTokens"):
            html = self.out[name]
            self.assertIsNone(re.search(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', html, re.IGNORECASE), name)
            self.assertNotIn("undefined", html, name)
            self.assertNotIn("NaN", html, name)


class TruthSource(unittest.TestCase):

    def test_new_lines_are_short_and_no_innerhtml(self):
        for name in ("topbar.js", "tokens.js", "limits.js"):
            with open(os.path.join(VIEWS, name), encoding="utf-8") as fh:
                src = fh.read()
            self.assertTrue(all(len(line) <= 120 for line in src.split("\n")), name)
            self.assertNotIn("innerHTML", src, name)

    def test_top_bar_reads_only_the_usage_and_the_meter_rows(self):
        with open(os.path.join(VIEWS, "topbar.js"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("roadmap-board/", src)
        self.assertNotIn("fetch(", src)
        self.assertNotIn("usage.json", src)


if __name__ == "__main__":
    unittest.main()
