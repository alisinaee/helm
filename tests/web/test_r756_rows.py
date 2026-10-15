"""Checks for R7.56 (the 375px findings left by 9a029b0): phone rows stay grids, agent rows nest and wrap inside
their tracks, the Overview blocker rows have an action slot, the list flag numbers sit in right-aligned cells, and the
Workflow detail strip has number cells and one action column on a phone. Static checks only; no inline style.
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
CSS = os.path.join(REPO, "web", "css")
VIEWS = os.path.join(REPO, "web", "js", "views")
INLINE = re.compile(r"""\sstyle\s*=|\son[a-z]{3,}\s*=""", re.IGNORECASE)


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class PhoneRowsTest(unittest.TestCase):

    def test_phone_rows_stay_grids_not_flex_wraps(self):
        css = read(CSS, "components.css")
        self.assertNotIn("display: flex;\n  flex-wrap: wrap;\n  gap: var(--sp-1) var(--sp-2);", css)
        self.assertNotIn(".rg-main {\n  flex: 1 1 100%", css)

    def test_agent_rows_use_a_phone_layout_below_640px(self):
        css = read(CSS, "components.css")
        start = css.index(".row-grid.rg-agent { grid-template-columns: minmax(0, 1fr) 5rem")
        block = css[start:start + 1200]
        self.assertIn(".row-grid.rg-head { display: none; }", block)
        self.assertIn(".rg-agent>:nth-child(8) { grid-column: 3; grid-row: 1 / 6 }", block)
        self.assertIn(".rg-agent>.rg-chips, .rg-agent>.rg-main { flex-wrap: wrap", block)

    def test_nested_workers_indent_once_on_a_phone(self):
        self.assertIn(".ag-kids .ag-kids { padding-left: 0; border-left: 0 }", read(CSS, "components.css"))


class OverviewAndListTest(unittest.TestCase):

    def test_blocker_rows_have_text_and_action_slots(self):
        text = read(VIEWS, "overview.js")
        self.assertIn('<li class="nz-row nz-slot"><span class="nz-txt">', text)
        self.assertIn('<span class="nz-act"></span></li>', text)
        flow = read(CSS, "flow.css")
        self.assertIn(".nz-slot { display: grid; grid-template-columns: minmax(0, 1fr) var(--ref-col)", flow)

    def test_flag_numbers_sit_in_right_aligned_cells(self):
        self.assertIn('<span class="num wk-fn">', read(VIEWS, "list.js"))
        work = read(CSS, "work.css")
        self.assertIn(".wk-fn{display:inline-block;min-width:3.5rem;text-align:right}", work)


class WorkflowDetailPhoneTest(unittest.TestCase):

    def test_detail_strip_has_number_cells_and_one_action_column(self):
        flow = read(CSS, "flow.css")
        self.assertIn(".row-grid.wf-cols{grid-template-columns:minmax(0,1fr) 4.5rem 4.5rem 6.5rem}", flow)
        self.assertIn(".wf-cols>:nth-child(8){grid-column:4;grid-row:2;justify-self:end}", flow)


class InlineStyleTest(unittest.TestCase):

    def test_touched_views_have_no_inline_style_or_handlers(self):
        for name in ("overview.js", "agents.js", "list.js", "workflow.js"):
            self.assertIsNone(INLINE.search(read(VIEWS, name)), name)


if __name__ == "__main__":
    unittest.main()
