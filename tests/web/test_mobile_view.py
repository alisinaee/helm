"""Tests for mobile responsiveness, safe area insets, touch targets, and sheet dismissal.

Verifies:
- viewport-fit=cover in web/index.html
- safe-area insets and touch target token (--h-touch: 44px) in web/css/tokens.css
- touch target sizing and 16px input font (iOS zoom prevention) in web/css/base.css
- overflow prevention, safe-area padding, and sheet scroll in web/css/shell.css
- flexible 4-item bnav-row and no text bleed in web/css/glass.css
- mobile table display: block conversion in web/css/work.css
- non-wrapping action bands and 2-row run item grid in web/css/components.css
- right-anchored mobile dropdown in web/css/system.css
- above-bottom-nav docking in web/css/toolbar.css
- closeMore export in web/js/views/nav.js and invocation in web/js/app.js
"""

import os
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")


def read_file(*parts):
    with open(os.path.join(WEB, *parts), encoding="utf-8") as fh:
        return fh.read()


class MobileViewportAndTokensTests(unittest.TestCase):
    def test_index_html_has_viewport_fit_cover(self):
        html = read_file("index.html")
        self.assertIn("viewport-fit=cover", html)

    def test_tokens_defines_touch_target_and_safe_areas(self):
        tokens = read_file("css", "tokens.css")
        self.assertIn("--h-touch: 44px;", tokens)
        self.assertIn("--sat: env(safe-area-inset-top, 0px);", tokens)
        self.assertIn("--sab: env(safe-area-inset-bottom, 0px);", tokens)
        self.assertIn("--sal: env(safe-area-inset-left, 0px);", tokens)
        self.assertIn("--sar: env(safe-area-inset-right, 0px);", tokens)

    def test_tokens_tabs_horizontal_touch_scroll(self):
        tokens = read_file("css", "tokens.css")
        self.assertIn("-webkit-overflow-scrolling: touch", tokens)
        self.assertIn(".band-actions .banner { flex: 1 1 100%; min-width: 0; max-width: 100%; }", tokens)


class MobileBaseCssTests(unittest.TestCase):
    def setUp(self):
        self.base = read_file("css", "base.css")

    def test_mobile_touch_target_min_height(self):
        self.assertIn("min-height: var(--h-touch, 44px)", self.base)

    def test_ios_input_zoom_prevention_16px(self):
        # Mobile inputs, selects, textareas must be at least 16px to prevent iOS auto-zoom
        self.assertIn("font-size: 16px", self.base)
        self.assertIn("input:not([type=\"checkbox\"]):not([type=\"radio\"])", self.base)


class MobileShellCssTests(unittest.TestCase):
    def setUp(self):
        self.shell = read_file("css", "shell.css")

    def test_app_clips_horizontal_overflow(self):
        self.assertIn("overflow-x:hidden", self.shell)

    def test_bnav_row_is_flex_and_fills(self):
        self.assertIn(".bnav-row{display:flex;height:100%}", self.shell)
        self.assertIn(".bnav-i{flex:1 1 0;min-width:0;", self.shell)

    def test_bnav_safe_area_padding(self):
        self.assertIn("height:calc(var(--h-bnav) + env(safe-area-inset-bottom,0px))", self.shell)
        self.assertIn("padding-bottom:env(safe-area-inset-bottom,0px)", self.shell)

    def test_sheet_max_height_and_scroll(self):
        expected_max_height = (
            "max-height:calc(100vh - var(--h-bnav) - var(--h-top) - 24px - env(safe-area-inset-bottom,0px))"
        )
        self.assertIn(expected_max_height, self.shell)
        self.assertIn("overflow-y:auto", self.shell)

    def test_side_drawer_safe_areas(self):
        self.assertIn("padding-top:env(safe-area-inset-top,0px)", self.shell)
        self.assertIn("padding-bottom:env(safe-area-inset-bottom,0px)", self.shell)

    def test_top_safe_areas(self):
        self.assertIn("padding-left:calc(var(--sp-3) + env(safe-area-inset-left,0px))", self.shell)
        self.assertIn("padding-right:calc(var(--sp-3) + env(safe-area-inset-right,0px))", self.shell)


class MobileGlassCssTests(unittest.TestCase):
    def setUp(self):
        self.glass = read_file("css", "glass.css")

    def test_bnav_not_overflow_hidden(self):
        # bnav must not clip overflow so the 'More' sheet can float above it
        self.assertNotIn("overflow: hidden;\n  }\n  .bnav-i", self.glass)

    def test_bnav_has_solid_surface_background(self):
        # bnav must have solid surface to prevent scrolled page content bleeding through
        self.assertIn("background: var(--surface-1);", self.glass)

    def test_bnav_active_item_no_crescent_shadow(self):
        # bnav-i[aria-current="page"] must not have one-sided inset 2px left shadow on a pill
        bad_shadow = (
            ":root[data-theme=\"obsidian\"] .bnav-i[aria-current=\"page\"] {\n"
            "  background: var(--glass-fill-strong);\n"
            "  color: var(--accent);\n"
            "  box-shadow: inset 2px 0 0"
        )
        self.assertNotIn(bad_shadow, self.glass)


class MobileWorkAndComponentsCssTests(unittest.TestCase):
    def test_work_table_block_display_on_mobile(self):
        work = read_file("css", "work.css")
        self.assertIn(".wk-table,.wk-table tbody{display:block;width:100%}", work)
        self.assertIn("box-sizing:border-box;width:100%", work)

    def test_band_actions_nowrap_on_mobile(self):
        comp = read_file("css", "components.css")
        self.assertIn(".band-actions {flex-direction: column;flex-wrap: nowrap;align-items: stretch}", comp)

    def test_run_item_grid_on_mobile(self):
        comp = read_file("css", "components.css")
        expected_grid = (
            ".run-item {grid-template-columns: minmax(0, 1fr) auto var(--ref-col);"
            "row-gap: var(--sp-1);padding: var(--sp-2) 0}"
        )
        self.assertIn(expected_grid, comp)
        expected_title = (
            ".run-item > .run-title {grid-column: 1 / -1;grid-row: 2;white-space: normal;overflow-wrap: anywhere}"
        )
        self.assertIn(expected_title, comp)

    def test_no_destructive_letter_split_wrap(self):
        comp = read_file("css", "components.css")
        bad_wrap = (
            ".btn,\n.btn-small {height: auto; min-height: 44px; "
            "white-space: normal; overflow-wrap: anywhere;"
        )
        self.assertNotIn(bad_wrap, comp)

    def test_touch_targets_in_components(self):
        comp = read_file("css", "components.css")
        self.assertIn(".btn,\n.btn-small {height: auto; min-height: 44px;", comp)
        self.assertIn(".theme-switch {min-width: 44px; min-height: 44px}", comp)


class MobileSystemAndToolbarCssTests(unittest.TestCase):
    def test_system_more_dropdown_anchored_right(self):
        system = read_file("css", "system.css")
        self.assertIn("position:absolute;top:100%;right:0;left:auto;max-width:calc(100vw - 32px)", system)

    def test_toolbar_popover_docked_above_bnav(self):
        toolbar = read_file("css", "toolbar.css")
        self.assertIn("bottom: calc(var(--h-bnav) + env(safe-area-inset-bottom, 0px));", toolbar)


class MobileNavBehaviorTests(unittest.TestCase):
    def test_nav_exports_close_more(self):
        nav = read_file("js", "views", "nav.js")
        self.assertIn("export function closeMore()", nav)

    def test_app_calls_close_more_on_route_change_and_outside_click(self):
        app = read_file("js", "app.js")
        self.assertIn("closeMore", app)
        self.assertIn("closeMore()", app)


if __name__ == "__main__":
    unittest.main()
