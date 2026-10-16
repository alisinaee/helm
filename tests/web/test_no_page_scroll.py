"""Static checks for R10.5: no page-level scrollbars on desktop widths.

The app is exactly the viewport tall (100dvh) and clips its own overflow. html and body do not scroll at 641px and up
(the full-screen Map keeps its page scroll because #app is hidden there). A closed right panel is display:none, so it
takes no layout width. Each section scrolls inside its own column (.main or a section scroller such as .hd-list).
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
CSS = os.path.join(REPO, "web", "css")


def read(*parts):
    with open(os.path.join(CSS, *parts), encoding="utf-8") as fh:
        return fh.read()


def rule(css, selector):
    match = re.search(re.escape(selector) + r"\{([^}]*)\}", css)
    return match.group(1) if match else None


class NoPageScrollTests(unittest.TestCase):
    def setUp(self):
        self.shell = read("shell.css")

    def test_app_is_viewport_tall_and_clips(self):
        app = rule(self.shell, ".app")
        self.assertIsNotNone(app)
        self.assertIn("height:100vh;height:100dvh", app)
        self.assertIn("overflow:hidden", app)
        self.assertNotIn("overflow-x:clip", app)

    def test_html_and_body_do_not_scroll_at_desktop_widths(self):
        self.assertIn("@media (min-width:641px){:is(html,body):has(#app:not([hidden])){height:100%;overflow:hidden}}",
                      self.shell)

    def test_full_map_keeps_page_scroll(self):
        # The full-screen Map hides #app, so the :has() rule above does not apply to it.
        self.assertNotIn("html{overflow", self.shell)
        self.assertNotIn("body{overflow", self.shell)

    def test_closed_panel_takes_no_layout_width(self):
        closed = rule(self.shell, '.app[data-panel="closed"] .side')
        self.assertEqual(closed, "display:none")

    def test_main_column_is_a_min_height_zero_grid_child(self):
        main = rule(self.shell, ".main")
        self.assertIn("min-height:0", main)
        self.assertIn("overflow:hidden auto", main)
        self.assertIn("minmax(0,1fr)", rule(self.shell, ".app"))

    def test_side_column_clips_its_own_content(self):
        side = rule(self.shell, ".side")
        self.assertIn("overflow:hidden", side)

    def test_head_list_is_the_only_head_scroller(self):
        head = read("head.css")
        self.assertIn(".hd-list{flex:1 1 auto;min-height:0;min-width:0;overflow:auto}", head)

    def test_shell_css_stays_under_cap(self):
        self.assertLessEqual(len(self.shell.encode("utf-8")), 8 * 1024)


if __name__ == "__main__":
    unittest.main()
