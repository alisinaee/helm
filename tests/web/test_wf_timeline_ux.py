"""R7.115: the Timeline UX fixes (SYSTEM-DESIGN-SECTION B-3). The plot fills the scroller and resizes; overflow rows
grow the lane up to 8 and a "+N" chip counts the rest; queued tasks are compact chips wrapped into rows, not piled at
the right edge; bars past the range get an edge cue; the id is the label when it fits and the tooltip otherwise; edges
are drawn above the bars; tick labels are thinned to the width; the default range is the narrowest one with jobs; a Now
button scrolls back to the now line. The markup checks run tests/web/render_workflow.mjs and are skipped without node.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_workflow.mjs")
FIXTURE = os.path.join(TESTS, "fixtures", "workflow_snapshot.json")
RECT = re.compile(r'<g class="wf-bar[^"]*"[^>]*>.*?<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)"', re.S)
PLOT = re.compile(r'<svg class="wf-plot" width="([\d.]+)" height="([\d.]+)"')


def read_text(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


class TimelineUxSourceTests(unittest.TestCase):

    def setUp(self):
        self.source = read_text("web", "js", "views", "workflow.js")

    def test_the_plot_fills_the_scroller_and_follows_its_size(self):
        self.assertNotIn("PLOT_W * timelineZoom", self.source)
        self.assertIn("const W = Math.max(PLOT_MIN, tlPlotW || PLOT_W) * timelineZoom;", self.source)
        self.assertIn("function measureTimeline(root)", self.source)
        self.assertIn("new ResizeObserver(", self.source)
        self.assertIn("measureTimeline(el);", self.source)

    def test_overflow_rows_grow_the_lane_and_a_chip_counts_the_rest(self):
        self.assertIn("const MAX_ROWS = 8;", self.source)
        self.assertIn("hidden[g.lane] += 1;", self.source)
        self.assertIn("'\" text-anchor=\"end\">+' + n", self.source)

    def test_queued_tasks_are_compact_chips_not_bars_at_the_edge(self):
        self.assertNotIn("W - QUEUE_W", self.source)
        self.assertIn("const QUEUE_CHIP = 28;", self.source)
        self.assertIn("const perRow = Math.max(1, Math.floor((W - qStart) / (QUEUE_CHIP + QUEUE_GAP)));",
                      self.source)

    def test_edges_are_drawn_above_the_bars_at_sixty_percent(self):
        self.assertIn("grid + bars + paths.join(\"\") + marks + more", self.source)
        self.assertIn('class="wf-edge wf-e-handoff" opacity="0.6"', self.source)

    def test_bars_past_the_range_get_an_edge_cue(self):
        self.assertIn("clipL: it.start < r.t0", self.source)
        self.assertIn("continues after this range", self.source)
        self.assertIn("const cueL = g.clipL ?", self.source)

    def test_the_id_is_the_label_when_it_fits_and_the_tooltip_otherwise(self):
        self.assertIn("const title = barTitle(it) +", self.source)
        self.assertIn("const fits = label.length * 6.6 + 10 <= w;", self.source)

    def test_tick_labels_are_thinned_to_the_available_width(self):
        self.assertIn("const TICK_MIN_PX = 64;", self.source)
        self.assertIn("function ticksOf(range, every)", self.source)

    def test_the_default_range_is_the_narrowest_with_jobs_and_the_map_keeps_today(self):
        self.assertIn("const range = view === \"map\" ? rangeOf(route) : rangeIn(route) || defaultRangeOf(route, raws);",
                      self.source)
        self.assertIn('return hit || "all";', self.source)

    def test_the_now_button_scrolls_back_to_the_now_line(self):
        self.assertIn('data-wf-now="1">Now</button>', self.source)
        self.assertIn("jumpToNow(closestEl(nowBtn, \".wf-page\"));", self.source)

    def test_the_lane_rows_have_no_fixed_height_classes(self):
        self.assertNotIn("wf-r2", self.source)
        self.assertNotIn("wf-r4", read_text("web", "css", "map.css"))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TimelineUxRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        proc = subprocess.run([shutil.which("node"), "--experimental-default-type=module", RENDER, WEB, FIXTURE],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("render_workflow.mjs failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_every_bar_sits_inside_the_plot(self):
        for name, case in self.out["cases"].items():
            with self.subTest(case=name):
                plot = PLOT.search(case["timeline"])
                self.assertIsNotNone(plot)
                width = float(plot.group(1))
                for m in RECT.finditer(case["timeline"]):
                    self.assertLessEqual(float(m.group(1)) + float(m.group(3)), width + 0.5)

    def test_the_label_column_has_one_cell_per_sub_row(self):
        for name, case in self.out["cases"].items():
            with self.subTest(case=name):
                plot = PLOT.search(case["timeline"])
                rows = round(float(plot.group(2)) / 44)
                labels = case["timeline"].count('class="wf-lbl')
                self.assertEqual(rows, labels)


if __name__ == "__main__":
    unittest.main()
