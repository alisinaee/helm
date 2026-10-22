"""Checks for the R7.43 head layout (review p6-gui): the card meta uses fixed grid tracks so the age and added numbers
line up, and below 480px the list table drops its wide columns and sticky offsets so it never scrolls sideways.

Static checks only: they read web/css/head.css and web/js/views/head.js. No inline style attribute, and the whole
web/css folder stays under the 72 KB cap.
"""

import os
import re
import unittest
from tests.web.test_shell import CSS_TOTAL_MAX

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
CSS_DIR = os.path.join(REPO, "web", "css")
HEAD_CSS = os.path.join(CSS_DIR, "head.css")
HEAD_JS = os.path.join(REPO, "web", "js", "views", "head.js")
INLINE = re.compile(r"""\sstyle\s*=""", re.IGNORECASE)
CAP = CSS_TOTAL_MAX


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def phone_block(css):
    """The body of the max-width:479px block (the 480px table rules)."""
    start = css.index("@media (max-width:479px)")
    return css[start:]


class CardMetaGridTests(unittest.TestCase):

    def setUp(self):
        self.css = read(HEAD_CSS)
        self.js = read(HEAD_JS)

    def test_meta_is_a_grid_with_fixed_age_and_added_tracks(self):
        self.assertRegex(self.css,
                         r"\.hd-meta\{grid-column:2 / -1;display:grid;grid-template-columns:auto minmax\(0,1fr\) 56px 112px;")
        self.assertNotRegex(self.css, r"\.hd-meta\{[^}]*display:flex")

    def test_numbers_are_right_aligned_and_tabular(self):
        self.assertRegex(self.css, r"\.hd-age,\.hd-when\{text-align:right;font-variant-numeric:tabular-nums\}")

    def test_age_and_when_are_the_last_two_meta_cells_in_order(self):
        meta = self.js.index('<span class="hd-meta">')
        status = self.js.index('hd-c hd-status', meta)
        bound = self.js.index('hd-c hd-bound', meta)
        age = self.js.index('hd-c hd-age rg-num', meta)
        when = self.js.index('hd-c hd-when rg-num', meta)
        self.assertLess(status, bound)
        self.assertLess(bound, age)
        self.assertLess(age, when)

    def test_phone_keeps_meta_full_width_grid(self):
        self.assertIn("grid-column:auto;flex:1 1 100%", self.css)


class PhoneTableTests(unittest.TestCase):

    def setUp(self):
        self.css = read(HEAD_CSS)
        self.block = phone_block(self.css)

    def test_below_480px_the_table_drops_the_wide_columns(self):
        self.assertIn(".hd-tbl .hd-bnd,.hd-tbl .hd-acc,.hd-tbl .hd-when{display:none}", self.block)

    def test_below_480px_no_column_is_sticky_or_offset(self):
        self.assertIn(".hd-n,.hd-sumc,.hd-stc{position:static}", self.block)
        self.assertNotIn("position:sticky", self.block)
        # The 599px block offsets the sticky columns with left:Npx; below 480px every cell resets to left:auto.
        self.assertIn("left:auto", self.block)
        self.assertIsNone(re.search(r"left:\d", self.block))

    def test_below_480px_columns_shrink_to_fit_the_phone_width(self):
        self.assertIn(".hd-n,.hd-sumc{width:auto;min-width:0}", self.block)
        self.assertIn(".hd-age{width:48px;min-width:48px}", self.block)
        self.assertIn(".hd-tbl .hd-panel{position:static;width:auto}", self.block)
        self.assertNotIn("calc(100vw", self.block)

    def test_the_480px_block_comes_after_the_599px_block(self):
        self.assertLess(self.css.index("@media (max-width:599px)"), self.css.index("@media (max-width:479px)"))


class HeadStyleRulesTests(unittest.TestCase):

    def test_no_inline_style_in_head_css_or_js(self):
        self.assertIsNone(INLINE.search(read(HEAD_JS)))
        self.assertNotIn("style=", read(HEAD_CSS))

    def test_css_folder_stays_under_the_cap(self):
        total = sum(os.path.getsize(os.path.join(CSS_DIR, name)) for name in os.listdir(CSS_DIR)
                    if name.endswith(".css"))
        self.assertLessEqual(total, CAP, "web/css totals %d bytes" % total)


if __name__ == "__main__":
    unittest.main()
