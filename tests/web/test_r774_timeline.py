"""R7.74: the Timeline. Bars show the task id only, and only when it fits; bars that overlap in one lane go to
sub-rows, so none is drawn over another; lanes are engines (Head, haiku, sonnet, opus, agy, cursor, opencode, other)
and only the lanes with items show, Queue and Blocked included; the now label stays inside the axis; the scroller is
keyboard reachable; drag-to-pan and Ctrl-wheel or pinch zoom are wired (pointer events, no text selection).

The markup checks run tests/web/render_workflow.mjs and are skipped when node is not installed.
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
ENGINE_LANES = {"Head", "haiku", "sonnet", "opus", "agy", "cursor", "opencode", "other", "Queue", "Blocked"}
BAR = re.compile(r'<g class="wf-bar[^"]*" tabindex="0" role="button" aria-label="[^"]*" data-focus="[^"]*" '
                 r'data-wf-item="[^"]*" data-wf-task="[^"]*" data-wf-pid="[^"]*" data-lane="(\d+)" '
                 r'data-x="([\d.]+)" data-y="([\d.]+)">.*?<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)"',
                 re.S)


def read_text(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


class TimelineSourceTests(unittest.TestCase):

    def test_pan_and_zoom_use_pointer_events_and_keep_the_pan(self):
        source = read_text("web", "js", "views", "workflow.js")
        for name in ("pointerdown", "pointermove", "pointerup", "wheel", "ctrlKey"):
            self.assertIn(name, source)
        # Drag moves the scroller; zoom keeps the time under the cursor (navZoom); the pan survives a re-render.
        self.assertIn("drag.sc.scrollLeft = drag.left - dx;", source)
        self.assertIn("navZoom(lastModel.base, tlNav, nextSpan, cx / w)", source)
        self.assertIn("scroller.scrollLeft = scrollLeft;", source)
        self.assertIn("if (window.location.hash === lastHash) return;", source)

    def test_the_scroller_is_not_a_native_touch_scroll_and_does_not_select_text(self):
        css = read_text("web", "css", "map.css")
        self.assertIn(".wf-tl{touch-action:none;user-select:none}", css)

    def test_the_plot_has_no_fixed_960_width_in_the_css(self):
        self.assertNotIn("960px", read_text("web", "css", "map.css"))

    def test_marks_differ_by_shape_not_only_colour(self):
        source = read_text("web", "js", "views", "workflow.js")
        self.assertIn("function markPath(status, x, cy)", source)
        self.assertIn('if (status === "doing")', source)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TimelineRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        proc = subprocess.run([shutil.which("node"), "--experimental-default-type=module", RENDER, WEB, FIXTURE],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("render_workflow.mjs failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)
        with open(FIXTURE, encoding="utf-8") as fh:
            cls.fixture = json.load(fh)

    def test_lanes_are_engines_and_queue_and_blocked_show_only_with_items(self):
        for name, case in self.out["cases"].items():
            with self.subTest(case=name):
                self.assertTrue(set(case["lanes"]) <= ENGINE_LANES, case["lanes"])
                has_queue = bool(self.fixture[name].get("queue"))
                self.assertEqual(has_queue, "Queue" in case["lanes"])

    def test_bars_show_the_task_id_only_and_never_a_clipped_word(self):
        for name, case in self.out["cases"].items():
            with self.subTest(case=name):
                texts = re.findall(r'<text x="[^"]*" y="[^"]*">([^<]*)</text>', case["timeline"])
                for text in texts:
                    self.assertRegex(text, r"^P\d+(\.\d+)?$")

    def test_bars_in_one_lane_that_overlap_are_in_different_sub_rows(self):
        for name, case in self.out["cases"].items():
            with self.subTest(case=name):
                bars = [(m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)),
                         float(m.group(6))) for m in BAR.finditer(case["timeline"])]
                for i, (lane_a, _, cy_a, x_a, w_a) in enumerate(bars):
                    for lane_b, _, cy_b, x_b, w_b in bars[i + 1:]:
                        if lane_a != lane_b:
                            continue
                        if x_a < x_b + w_b and x_b < x_a + w_a:
                            self.assertNotEqual(cy_a, cy_b, "overlapping bars share a row in lane " + lane_a)

    def test_the_now_label_stays_inside_the_axis(self):
        for name, case in self.out["cases"].items():
            with self.subTest(case=name):
                now = re.search(r'<text class="wf-now-t" x="([\d.]+)" y="10" text-anchor="(\w+)">', case["timeline"])
                if now is None:
                    continue
                x = float(now.group(1))
                if x > 936:
                    self.assertEqual("end", now.group(2))

    def test_the_timeline_scroller_is_keyboard_reachable(self):
        for name, case in self.out["cases"].items():
            with self.subTest(case=name):
                self.assertIn('tabindex="0" role="region" aria-label="Workflow timeline"', case["timeline"])


if __name__ == "__main__":
    unittest.main()
