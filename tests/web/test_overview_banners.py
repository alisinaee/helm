"""Checks for the Overview banner stack (R11.147).

Every Overview banner (the limit banner and the Running or Stopped banner) is rendered inside one .ov-banners stack
above the .ov grid, so the stacked rows share one left edge, one padding and one grid. Static checks only: they read
web/js/views/overview.js and web/css/flow.css.
"""

import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OVERVIEW_JS = os.path.join(REPO, "web", "js", "views", "overview.js")
FLOW_CSS = os.path.join(REPO, "web", "css", "flow.css")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class OverviewBannerStackTests(unittest.TestCase):

    def setUp(self):
        self.js = read(OVERVIEW_JS)
        self.css = read(FLOW_CSS)

    def test_one_stack_helper_wraps_the_banners(self):
        self.assertIn("function bannerStack(parts)", self.js)
        self.assertIn("'<div class=\"ov-banners\">' + items.join(\"\") + \"</div>\"", self.js)

    def test_project_and_all_views_both_use_the_stack(self):
        self.assertIn("bannerStack([limitBanner(worstLimit(scopes), true), controlBanner(vm)])", self.js)
        self.assertIn("bannerStack([limitBanner(worstLimit(scopes), false)])", self.js)

    def test_control_banner_is_no_longer_inside_the_main_column(self):
        main = re.search(r"const main = (.*?);", self.js, re.S).group(1)
        self.assertNotIn("controlBanner", main)
        self.assertNotIn("limitBanner(", self.js.split("function projectOverview")[1].split("return bannerStack")[0])

    def test_stack_rows_share_one_padding_and_margin_reset(self):
        self.assertIn(".ov-banners > .banner, .ov-banners > .banner + .banner { margin: 0;", self.css)
        self.assertIn("padding: var(--sp-3) var(--sp-4) }", self.css)
        self.assertIn(".ov-banners .banner > p { margin: 0 }", self.css)
        self.assertIn(".ov-banners .banner .ov-actions { margin: var(--sp-2) 0 0 }", self.css)

    def test_old_banner_sibling_offset_is_gone(self):
        self.assertNotIn(".banner + .ov", self.css)


if __name__ == "__main__":
    unittest.main()
