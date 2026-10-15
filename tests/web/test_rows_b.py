"""Row alignment, part B (R7.5, UI checklist rule 0): the tree and list rows, the Overview phase rows, the
research notes and the rule rows keep their numbers in right-aligned tracks and their copy buttons in the
one fixed last column. The check reads the renderers and the shared CSS; no browser is needed."""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
VIEWS = os.path.join(REPO, "web", "js", "views")
CSS = os.path.join(REPO, "web", "css")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class TreeRowsTest(unittest.TestCase):
    def test_task_rows_use_the_shared_grid_with_flags_and_copy_in_their_tracks(self):
        tree = read(VIEWS, "tree.js")
        self.assertIn('<div class="wk-tree-row row-grid">', tree)
        self.assertIn('<span class="rg-chips">', tree)
        self.assertIn('class="wk-title rg-t"', tree)

    def test_phase_header_counts_are_right_aligned_and_names_ellipsize(self):
        tree = read(VIEWS, "tree.js")
        self.assertIn('class="wk-count num rg-num"', tree)
        self.assertIn("<span class=\"rg-t\">' + esc(name)", tree)
        work = read(CSS, "work.css")
        self.assertRegex(work, r"\.wk-phase-btn\{display:grid;grid-template-columns:1rem 4\.5rem")
        self.assertRegex(work, r"\.wk-phase-h\{display:grid;grid-template-columns:minmax\(0,1fr\) var\(--ref-col\)")

    def test_tree_row_track_is_defined_by_the_row_not_by_flex(self):
        work = read(CSS, "work.css")
        self.assertRegex(work, r"\.wk-tree-row\{--rg:4\.5rem minmax\(0,1fr\) 6\.5rem 8rem;")
        self.assertNotIn(".wk-tree-row{display:flex", work)


class ListRowsTest(unittest.TestCase):
    def test_copy_button_has_its_own_last_column_not_the_title_cell(self):
        lst = read(VIEWS, "list.js")
        self.assertIn("'<td class=\"wk-c-ref\">' + taskCopyHtml(", lst)
        self.assertIn('+ "</a></td>" +', lst)
        self.assertIn('<th scope="col" class="wk-c-ref">', lst)
        self.assertIn('colspan="11"', lst)

    def test_table_has_fixed_layout_and_one_width_per_column(self):
        work = read(CSS, "work.css")
        self.assertIn(".wk-table{table-layout:fixed}", work)
        for cls in ("wk-c-sel", "wk-c-id", "wk-c-phase", "wk-c-status", "wk-c-model", "wk-c-flags", "wk-c-ref"):
            self.assertRegex(work, r"\." + cls + r"[^{]*\{[^}]*width:", cls)

    def test_numbers_are_right_aligned_and_the_title_has_no_width_cap(self):
        work = read(CSS, "work.css")
        self.assertRegex(work, r"\.wk-c-est,\.wk-c-spent,\.wk-c-cap\{width:3\.75rem;text-align:right\}")
        self.assertNotIn("max-width:360px", work)
        self.assertRegex(work, r"\.wk-table \.wk-c-title a\{display:block;overflow:hidden;text-overflow:ellipsis")

    def test_phone_list_rows_keep_the_copy_button_at_the_right_edge(self):
        work = read(CSS, "work.css")
        self.assertIn(".wk-table .wk-c-ref{order:3;width:auto;margin-left:auto}", work)


class OverviewPhaseRowsTest(unittest.TestCase):
    def test_overview_main_column_is_a_size_container(self):
        flow = read(CSS, "components.css")
        self.assertIn(".ov-main { container-type: inline-size; }", flow)

    def test_phase_rows_reflow_to_two_lines_when_the_card_is_narrow(self):
        css = read(CSS, "components.css")
        start = css.index("@container (max-width: 560px) {")
        body = css[start:css.index("@media (max-width: 639px)", start)]
        self.assertIn(".phase-row", body)
        self.assertIn(".ph-head", body)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 72px 48px;", body)

    def test_phase_rows_keep_their_counts_in_right_aligned_cells(self):
        phases = read(VIEWS, "phases.js")
        self.assertIn('class="ph-count num"', phases)
        self.assertIn('class="ph-pct num"', phases)
        self.assertNotIn(" style=", phases)


class ResearchAndRulesRowsTest(unittest.TestCase):
    def test_research_note_numbers_sit_in_their_own_right_aligned_cells(self):
        research = read(VIEWS, "research.js")
        self.assertIn('<span class="ov-sum rg-num">', research)
        self.assertIn('<span class="note-main">', research)
        css = read(CSS, "components.css")
        self.assertIn(".note-row.row-grid > .btn {", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 5.5rem 4.5rem;", css)

    def test_rule_budget_has_its_own_track_and_the_row_keeps_the_copy_column(self):
        rules = read(VIEWS, "rules.js")
        self.assertIn("'<span class=\"rg-num num\">' + value + \"</span>\"", rules)
        self.assertNotIn('" (" + esc(r.value)', rules)
        admin = read(CSS, "admin.css")
        self.assertIn(".rule-row { --rg: minmax(0, 1fr) 6rem 4.5rem 5.5rem;", admin)


if __name__ == "__main__":
    unittest.main()
