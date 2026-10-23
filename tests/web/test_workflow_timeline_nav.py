"""R11.109: Workflow timeline navigation. Pure helpers (navWindow, navZoom, navPan, layout with nav) run in node; the
markup is checked for static aria-labels, the Now button and the key handling."""

import json
import os
import shutil
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, "web", "js", "views", "workflow.js")
SCRIPT = """
globalThis.document = { dispatchEvent() { return true; }, addEventListener() {} };
const m = await import(process.argv[1]);
const H = 3600000;
const out = {};
out.same = m.navWindow(0, 2 * H, 1, 0);
out.zoomIn = m.navWindow(0, 2 * H, 0.5, 0);
out.past = m.navWindow(0, 2 * H, 1, H);
out.clampSpan = [m.navWindow(0, H, 1000, 0).span, m.navWindow(0, H, 0, 0).span];
out.noFuture = m.navWindow(0, H, 1, -5).shift;
const base = { t0: 0, t1: 2 * H };
const z = m.navZoom(base, { span: 1, shift: 0 }, 0.5, 0.25);
const w = m.navWindow(0, 2 * H, z.span, z.shift);
out.anchorKept = [0.25 * 2 * H, w.t0 + 0.25 * (w.t1 - w.t0)];
out.panBack = m.navPan(base, { span: 1, shift: 0 }, -0.25).shift;
out.panFwdLimit = m.navPan(base, { span: 1, shift: 0 }, 0.25).shift;
const snap = { project: { id: "p", title: "P" }, jobs: [], tasks: [] };
const now = 1000 * H;
const a = m.layout(snap, "2h", now, null);
const b = m.layout(snap, "2h", now, { span: 1, shift: H });
out.range = [a.range.t1 - a.range.t0, b.range.t1 - b.range.t0, a.range.t1 - b.range.t1, b.base.t1 === a.range.t1];
console.log(JSON.stringify(out));
"""


class TimelineNavTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("node is not installed")
        proc = subprocess.run([node, "--experimental-default-type=module", "--input-type=module", "-e", SCRIPT,
            "file://" + SRC],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("node failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout.strip().splitlines()[-1])

    def test_window_math(self):
        h = 3600000
        o = self.out
        self.assertEqual((o["same"]["t0"], o["same"]["t1"]), (0, 2 * h))
        self.assertEqual(o["zoomIn"]["t1"] - o["zoomIn"]["t0"], h)
        self.assertEqual((o["past"]["t0"], o["past"]["t1"]), (-h, h))
        self.assertEqual(o["clampSpan"], [8, 1])
        self.assertEqual(o["noFuture"], 0)

    def test_zoom_keeps_anchor_and_pan_stops_at_now(self):
        o = self.out
        self.assertAlmostEqual(o["anchorKept"][0], o["anchorKept"][1], places=3)
        self.assertGreater(o["panBack"], 0)
        self.assertEqual(o["panFwdLimit"], 0)

    def test_layout_applies_nav(self):
        h = 3600000
        r = self.out["range"]
        self.assertEqual(r[0], r[1])
        self.assertEqual(r[2], h)
        self.assertTrue(r[3])

    def test_markup_and_keys(self):
        src = open(SRC, encoding="utf-8").read()
        for label in ("Earlier", "Later", "Zoom out", "Zoom in", "Jump to now"):
            self.assertIn('aria-label="' + label + '"', src)
        self.assertIn('data-wf-now="1"', src)
        for key in ("ArrowLeft", "ArrowRight"):
            self.assertIn(key + ': "', src)


if __name__ == "__main__":
    unittest.main()
