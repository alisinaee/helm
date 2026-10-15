"""R7.54: agy 375px audit fixes. Rule 0 (fixed row tracks, numbers right-aligned), no horizontal overflow at 375px,
44px touch targets on phone, and no orphan CSS. Static checks on the renderers and the shared CSS."""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
CSS = os.path.join(REPO, "web", "css")
VIEWS = os.path.join(REPO, "web", "js", "views")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class TrackTest(unittest.TestCase):
    def test_spend_resets_text_wraps_inside_its_track(self):
        self.assertIn(".tk-spend > :last-child { white-space: normal; overflow-wrap: anywhere }",
                      read(CSS, "components.css"))

    def test_limit_forms_have_their_own_tracks(self):
        css = read(CSS, "components.css")
        self.assertIn(".rg-share { --rg:", css)
        self.assertIn(".rg-weekly { --rg:", css)
        self.assertIn('<span class="rg-num">Used</span>', read(VIEWS, "limits.js"))

    def test_workflow_detail_action_track_fits_the_button(self):
        self.assertRegex(read(CSS, "map.css"), r"\.wf-cols\{--rg:[^;]*4\.5rem auto;")
        self.assertIn(".wf-table .rg-num{text-align:right}", read(CSS, "map.css"))
        self.assertIn('<span class="wf-gn">Jobs</span><span class="wf-gt">Tokens</span>',
                      read(VIEWS, "workflow.js"))

    def test_finished_agents_have_the_column_header(self):
        agents = read(VIEWS, "agents.js")
        self.assertIn("'<ol class=\"ag-list\" aria-label=\"Last finished jobs\">' + head +", agents)

    def test_spend_project_name_has_full_title(self):
        self.assertIn('<span class="rg-t" title="\' + esc(name) + \'">\' + esc(name) +',
                      read(VIEWS, "tokens.js"))


class MobileWorkTest(unittest.TestCase):
    def test_table_title_can_shrink_and_numbers_stay_visible(self):
        css = read(CSS, "work.css")
        self.assertIn(".wk-table .wk-c-title{min-width:0}", css)
        mobile = css[css.index("@media (max-width:767px)"):]
        self.assertNotRegex(mobile, r"\.wk-c-est,\.wk-c-spent,\.wk-c-cap[^{]*\{display:none")
        self.assertIn(".wk-table .wk-c-est,.wk-table .wk-c-spent,.wk-table .wk-c-cap{order:3", css)

    def test_tree_word_and_flags_do_not_share_a_cell(self):
        css = read(CSS, "work.css")
        self.assertIn(".wk-tree-row>.wk-word{grid-column:2;grid-row:2}", css)
        self.assertIn(".wk-tree-row>.rg-chips{grid-column:2;grid-row:3", css)

    def test_subtask_copy_sits_in_a_fixed_trailing_track(self):
        self.assertIn(".wk-subs li{display:grid;grid-template-columns:minmax(0,1fr) var(--ref-col)",
                      read(CSS, "work.css"))

    def test_task_tabs_wrap_on_phone(self):
        self.assertIn(".wk-tabs{display:flex;flex-wrap:wrap;", read(CSS, "work.css"))


class PhoneTargetTest(unittest.TestCase):
    def test_copy_button_has_a_44px_hit_area_on_coarse_pointers(self):
        css = read(CSS, "components.css")
        self.assertIn('.ref-copy::before{content:"";position:absolute;inset:-10px}', css)
        self.assertIn("@media (pointer:coarse){.ref-copy{opacity:1}}", css)

    def test_usage_numbers_are_right_aligned(self):
        self.assertIn(".mt-text { text-align: right; font-variant-numeric: tabular-nums }",
                      read(CSS, "flow.css"))


class OrphanCssTest(unittest.TestCase):
    def test_legacy_classes_are_gone(self):
        admin = read(CSS, "admin.css")
        for name in ("spend-name", "spend-val", "met-row", "mbar", "mrail", "met-value"):
            self.assertNotIn("." + name, admin, name)
        self.assertNotIn(".act-tok", read(CSS, "components.css"))

    def test_css_total_stays_under_the_cap(self):
        total = 0
        for name in os.listdir(CSS):
            if name.endswith(".css"):
                total += os.path.getsize(os.path.join(CSS, name))
        self.assertLessEqual(total, 72 * 1024)

    def test_no_inline_style_in_changed_views(self):
        for name in ("agents.js", "tokens.js", "limits.js", "workflow.js", "work.js", "overview.js"):
            self.assertIsNone(re.search(r"style=\"", read(VIEWS, name)), name)


if __name__ == "__main__":
    unittest.main()
