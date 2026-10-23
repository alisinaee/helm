"""Checks for web/css/motion.css (docs/MOTION-PLAN.md, CSS worker): it is linked last in index.html, it defines the
three
durations and two easings, it draws the loading state from aria-busy, it has a reduced-motion block, and it stays small
with no raw colours. Stdlib only; the files are read as text.
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
MOTION = os.path.join(WEB, "css", "motion.css")
INDEX = os.path.join(WEB, "index.html")
MAX_BYTES = 6 * 1024
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
STYLESHEET = re.compile(r'<link\s+rel="stylesheet"\s+href="/css/([^"]+)"')


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class MotionStylesheetTests(unittest.TestCase):

    def setUp(self):
        self.text = read(MOTION)

    def test_motion_is_the_last_stylesheet_linked(self):
        linked = STYLESHEET.findall(read(INDEX))
        self.assertTrue(linked, "index.html links no stylesheets")
        self.assertEqual(linked[-1], "motion.css")

    def test_motion_is_listed_once_in_index(self):
        self.assertEqual(read(INDEX).count('href="/css/motion.css"'), 1)

    def test_defines_the_three_durations(self):
        for name, value in (("t-quick", "140ms"), ("t-med", "260ms"), ("t-slow", "380ms")):
            self.assertRegex(self.text, r"--%s:\s*%s\s*;" % (name, re.escape(value)), name)

    def test_defines_the_two_easings(self):
        self.assertRegex(self.text, r"--ease-out:\s*cubic-bezier\(\s*\.22\s*,\s*1\s*,\s*\.36\s*,\s*1\s*\)")
        self.assertRegex(self.text, r"--ease-in-out:\s*cubic-bezier\(\s*\.65\s*,\s*0\s*,\s*\.35\s*,\s*1\s*\)")

    def test_loading_state_is_drawn_from_aria_busy(self):
        self.assertIn('[aria-busy="true"]', self.text)
        self.assertIn('.btn[aria-busy="true"]', self.text)
        self.assertIn("animation: motion-spin", self.text)

    def test_reduced_motion_block_exists_and_keeps_a_static_loading_mark(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.text)
        self.assertIn("transition-duration: .01ms", self.text)
        self.assertIn('"\\2026"', self.text)

    def test_side_panel_closed_state_is_not_focusable(self):
        self.assertRegex(self.text, r'\.app\[data-panel="closed"\] \.side\s*\{[^}]*visibility:\s*hidden')

    def test_small_and_colourless(self):
        self.assertLessEqual(len(self.text.encode("utf-8")), MAX_BYTES)
        self.assertEqual(HEX.findall(self.text), [])


if __name__ == "__main__":
    unittest.main()
