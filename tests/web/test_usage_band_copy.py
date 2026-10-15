"""R7.77: the band never gives /login advice, names the source and age, folds the manual form while fresh; the top bar
shows the stop that binds first (the lower of the project's own and the global weekly stop). Skipped without node."""

import json
import os
import shutil
import subprocess
import unittest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")

SCRIPT = """
const usage = await import(process.argv[1]);
const top = await import(process.argv[2]);
const now = 1800000000000;
const base = { loaded: true, weeklyPercent: 80, fiveHourPercent: 67, weeklyResetsAt: null, fiveHourResetsAt: null,
  ageNow: 300, stale: false, veryOld: false, lastError: null, source: "manual push", sync: null };
const vm = (extra) => ({ view: "home", route: { name: "home" }, now: now, projects: [],
  usage: Object.assign({}, base, extra) });
const rows = [{ scope: "global", kind: "pct", window: "week", limit: 95, action: "block" },
  { scope: "project", kind: "acct", window: "week", limit: 85, action: "block" }];
console.log(JSON.stringify({
  fresh: usage.usageView(vm({ syncError: "no_token" })),
  old: usage.usageView(vm({ syncError: "no_token", stale: true, veryOld: true, ageNow: 7200 })),
  hook: usage.usageView(vm({ source: "Claude Code hook" })),
  stop: top.meterText({ weeklyPercent: 80, stale: false }, rows),
  onlyGlobal: top.meterText({ weeklyPercent: 80, stale: false }, rows.slice(0, 1)),
}));
"""


class UsageBandCopyTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed")
        urls = ["file://" + os.path.join(WEB, "js", "views", name) for name in ("usage.js", "topbar.js")]
        proc = subprocess.run([shutil.which("node"), "--input-type=module", "-e", SCRIPT] + urls,
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_no_login_advice_anywhere(self):
        for key in ("fresh", "old", "hook"):
            self.assertNotIn("/login", self.out[key], key)
            self.assertNotIn("not synced automatically", self.out[key], key)

    def test_fresh_reading_has_no_banner_and_a_folded_form(self):
        html = self.out["fresh"]
        self.assertNotIn("Usage is old.", html)
        self.assertIn('<details class="usage-more">', html)
        self.assertIn("Updated 5 min ago, by the head from the app", html)

    def test_old_reading_says_so_and_opens_the_form(self):
        self.assertIn("Usage is old.", self.out["old"])
        self.assertIn('<details class="usage-more" open>', self.out["old"])

    def test_hook_source_is_named(self):
        self.assertIn(", from Claude Code</span>", self.out["hook"])

    def test_top_bar_shows_the_binding_stop(self):
        self.assertIn("stop 85%", self.out["stop"])
        self.assertIn("stop 95%", self.out["onlyGlobal"])


if __name__ == "__main__":
    unittest.main()
