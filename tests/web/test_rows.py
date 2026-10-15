"""Row alignment (WP36, UI checklist rule 0): every list of rows that shows numbers or actions uses the shared
`.row-grid` utility, so its tracks line up. The check reads the renderers and the shared CSS; no browser is needed."""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
VIEWS = os.path.join(REPO, "web", "js", "views")
COMPONENTS = os.path.join(REPO, "web", "css", "components.css")

# The renderers that show rows with numbers or actions, and the class each must use.
ROW_RENDERERS = {
    "agents.js": "row-grid rg-agent",
    "running.js": "row-grid run-item",
    "home.js": "row-grid run-row",
    "activity.js": 'class="act-row row-grid"',
    "limits.js": "row-grid rg-share",
    "inbox.js": "qc-opts row-grid",
    "issues.js": "iss-top row-grid",
    "projects.js": "p-badges row-grid",
}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class RowGridTest(unittest.TestCase):
    def test_each_row_renderer_uses_the_shared_grid_class(self):
        for name, marker in ROW_RENDERERS.items():
            self.assertIn(marker, read(os.path.join(VIEWS, name)), name)

    def test_renderers_keep_numbers_in_their_own_right_aligned_cell(self):
        # The shared rule right-aligns .rg-num; the renderers that show counts or times must use it.
        for name in ("agents.js", "running.js", "home.js"):
            self.assertIn("rg-num", read(os.path.join(VIEWS, name)), name)

    def test_shared_grid_is_defined_with_a_track_variable(self):
        css = read(COMPONENTS)
        self.assertRegex(css, r"\.row-grid\s*\{[^}]*grid-template-columns:\s*var\(--rg\)")
        self.assertRegex(css, r"\.rg-num\s*\{[^}]*text-align:\s*right")

    def test_numbers_and_actions_use_fixed_helpers(self):
        agents = read(os.path.join(VIEWS, "agents.js"))
        self.assertGreaterEqual(len(re.findall(r'class="rg-num num"', agents)), 2)
        self.assertIn('class="row-grid rg-agent rg-head"', agents)


class TokensAndPhasesRowsTest(unittest.TestCase):
    def test_spend_rows_use_the_shared_grid_with_numbers_in_their_own_cells(self):
        tokens = read(os.path.join(VIEWS, "tokens.js"))
        self.assertIn('<li class="row-grid tk-spend">', tokens)
        self.assertNotIn("spend-row", tokens)
        self.assertGreaterEqual(tokens.count('class="rg-num num'), 2)

    def test_spend_track_has_one_fixed_action_column(self):
        css = read(COMPONENTS)
        self.assertRegex(css, r"\.tk-spend\s*\{[^}]*--rg:\s*minmax\(0,\s*1fr\)(\s+[0-9.]+rem){4}")
        self.assertNotIn(".spend-row {", css)

    def test_phase_counts_ellipsize_instead_of_spilling_into_the_next_column(self):
        css = read(COMPONENTS)
        self.assertRegex(css, r"\.ph-count,\s*\.ph-left,\s*\.ph-pct\s*\{[^}]*text-overflow:\s*ellipsis")

    def test_no_inline_style_or_handlers_in_the_rows(self):
        for name in ("tokens.js", "phases.js"):
            text = read(os.path.join(VIEWS, name))
            self.assertNotIn(" style=", text, name)
            self.assertIsNone(re.search(r"\son[a-z]{3,}=", text), name)


if __name__ == "__main__":
    unittest.main()
