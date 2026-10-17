"""Pure helpers of the Activity timeline strip (R11.117), run in node."""

import json
import os
import shutil
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MOD = os.path.join(REPO, "web", "js", "views", "activity_timeline.js")

SCRIPT = """
import { pathToFileURL } from "node:url";
const t = await import(pathToFileURL(process.argv[1]).href);
const now = Date.parse("2026-10-13T12:00:00Z");
const kinds = ["head", "commit", "task", "job"];
const events = [];
for (let i = 0; i < 2800; i++) {
  events.push({ id: "e" + i, ms: now - i * 37000, kind: kinds[i % 4], summary: "s" + i });
}
const out = {};
const filt = (preset) => ({ preset: preset, from: null, to: null });
const ax = t.axisOf(filt("all"), events, now);
out.bins = t.bin(events, ax[0], ax[1]).length;
out.axis = ax;
const a24 = t.axisOf(filt("24h"), events, now);
out.t24 = t.ticks(a24[0], a24[1], now).map((x) => x.label);
const a7 = t.axisOf(filt("7d"), events, now);
out.t7 = t.ticks(a7[0], a7[1], now).map((x) => x.label);
out.tall = t.ticks(ax[0], ax[1] + 90 * 86400000, now).map((x) => x.label);
out.selx = [t.xOf(events[10].ms, ax[0], ax[1]), t.xOf(now + 9e9, ax[0], ax[1]), t.xOf(0, ax[0], ax[1])];
const st = { filt: filt("all"), sel: "e5" };
out.html = t.timelineHtml(st, events, now);
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(["node", "--input-type=module", "-e", SCRIPT, MOD], capture_output=True, text=True,
                             check=False)
        assert run.returncode == 0, run.stderr
        cls.out = json.loads(run.stdout)

    def test_binning_caps_marks(self):
        self.assertLessEqual(self.out["bins"], 600)
        self.assertGreater(self.out["bins"], 10)

    def test_ticks_per_range(self):
        self.assertRegex(self.out["t24"][0], r"^\d\d:\d\d$")
        self.assertEqual(self.out["t24"][-1], "now")
        self.assertRegex(self.out["t7"][0], r"^\d\d-\d\d$")
        self.assertRegex(self.out["tall"][0], r"^\d{4}-\d\d-\d\d$")

    def test_selected_x_within_axis(self):
        for x in self.out["selx"]:
            self.assertTrue(0 <= x <= 1000)

    def test_markup(self):
        html = self.out["html"]
        self.assertIn('role="img"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("hx-tl-sel", html)
        self.assertIn("Selected:", html)
        self.assertNotIn("style=", html)
        self.assertLessEqual(html.count("hx-tl-m "), 600)


if __name__ == "__main__":
    unittest.main()
