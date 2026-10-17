"""Checks for the Overview Activity card (R11.124).

The card reuses the Activity row (activityRowHtml with a history event and a ctx object). The node render in
tests/web/render_sections.mjs builds the Overview from the synthetic snapshot; these checks read that output: no
"NaN" anywhere, each row shows a clock time and its summary, and the undo control is the small icon button on the
undoable line only. The node checks are skipped when node is not installed.
"""

import os
import re
import shutil
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from tests.web.test_sections import render  # noqa: E402

TIME = re.compile(r'class="hx-time num"[^>]*>(\d\d:\d\d)<')


class OverviewActivityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the Overview activity render check is skipped")
        cls.out = render()

    def test_overview_activity_card_has_no_nan(self):
        for name in ("overviewProject", "overviewGolden", "overviewAll"):
            self.assertNotIn("NaN", self.out[name], name)

    def test_overview_activity_rows_show_time_and_summary(self):
        html = self.out["overviewProject"]
        self.assertIn('<ol class="act-list hx-list">', html)
        self.assertEqual(html.count('class="act-row row-grid"'), 2)
        self.assertEqual(len(TIME.findall(html)), 2)
        self.assertIn("P0.8 done", html)
        self.assertIn("stop", html)

    def test_overview_undo_is_offered_only_on_undoable_lines(self):
        html = self.out["overviewProject"]
        self.assertEqual(html.count('data-action="undo-line"'), 1)
        self.assertIn('data-activity="a1"', html)
        self.assertNotIn('data-activity="a2"', html)


if __name__ == "__main__":
    unittest.main()
