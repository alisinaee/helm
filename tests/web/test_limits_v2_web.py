"""R11.126 Limits v2 cards: slider markup and aria, mode and switch controls, budget and cap labels, drag maths,
no inline markup. The page logic runs under node with a stubbed endpoint."""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_limits_v2.mjs")
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class LimitsV2Web(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run(["node", "--experimental-default-type=module", RENDER, WEB], capture_output=True,
                              text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_loading_note_before_the_data(self):
        self.assertIn("Loading stops.", self.out["before"])

    def test_two_cards_with_sliders(self):
        html = self.out["html"]
        self.assertEqual(html.count('class="lv-card'), 2)
        self.assertEqual(html.count('role="slider"'), 2)
        for attr in ("aria-valuemin=", "aria-valuemax=", "aria-valuenow=", "aria-valuetext=", 'tabindex="0"'):
            self.assertEqual(html.count(attr) >= 2, True, attr)
        self.assertIn('aria-valuetext="+20% of 5h, stop at 49%"', html)
        self.assertIn('aria-valuetext="stop at 35%"', html)
        self.assertIn('aria-valuemin="30"', html)  # a budget handle cannot go below base + 1

    def test_modes_switch_and_number(self):
        html = self.out["html"]
        self.assertEqual(html.count("Budget from now"), 2)
        self.assertEqual(html.count(">Cap at<"), 2)
        self.assertIn('aria-label="5 hours stop, on"', html)
        self.assertIn('aria-label="Week stop, off"', html)
        self.assertEqual(html.count('data-lv="num"'), 2)
        self.assertIn("% more", html)

    def test_labels_and_drag_maths(self):
        self.assertEqual(self.out["label"], "+20% of 5h")
        self.assertEqual(self.out["stop"], 49)
        self.assertEqual(self.out["budgetAfter"], {"value": 41, "base": 29})  # stop 70 = base 29 + N 41
        self.assertEqual(self.out["weekAfter"], {"value": 40, "on": True})
        self.assertEqual(self.out["clamped"], 1)

    def test_no_inline_markup_and_no_undefined(self):
        html = self.out["html"]
        self.assertIsNone(INLINE.search(html))
        self.assertNotIn("undefined", html)
        self.assertNotIn("NaN", html)

    def test_bar_widths_use_data_pct(self):
        self.assertIn('class="lv-fill" data-pct="29"', self.out["html"])


if __name__ == "__main__":
    unittest.main()
