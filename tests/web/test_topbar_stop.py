"""Q2 (checkpoint 10): the top bar reads the weekly stop from the snapshot's meters. A project's own stop in
autonomy.json (an acct row) shows as "stop 98%" when there is no global limit row. The snapshot's meters are an object
{limits, today, week}, so the top bar must read its limits list. Skipped without node."""

import json
import os
import shutil
import subprocess
import unittest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")

SCRIPT = """
const top = await import(process.argv[1]);
const usage = { weeklyPercent: 12, stale: false };
const auto = { id: "AUTO", scope: "project", window: "week", kind: "acct", used: 12, limit: 98, state: "ok",
  src: "autonomy", action: "block" };
const shape = (limits) => ({ limits: limits, today: { pts: 0 }, week: { pct: 12 } });
console.log(JSON.stringify({
  autonomyOnly: top.meterText(usage, shape([auto])),
  arrayRows: top.meterText(usage, [auto]),
  noRows: top.meterText(usage, shape([])),
  noMeters: top.meterText(usage, null),
}));
"""


class TopBarStopTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed")
        url = "file://" + os.path.join(WEB, "js", "views", "topbar.js")
        proc = subprocess.run([shutil.which("node"), "--input-type=module", "-e", SCRIPT, url],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_autonomy_stop_shows_when_no_global_row(self):
        self.assertIn("stop 98%", self.out["autonomyOnly"])

    def test_plain_rows_list_still_works(self):
        self.assertIn("stop 98%", self.out["arrayRows"])

    def test_no_limit_rows_reads_stop_off(self):
        self.assertIn("stop off", self.out["noRows"])

    def test_no_meters_reads_stop_unknown(self):
        self.assertIn("stop unknown", self.out["noMeters"])

if __name__ == "__main__":
    unittest.main()
