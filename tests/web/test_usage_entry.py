"""Checks for the usage band (R7.27, R7.77, R7.100): no Claude Code login (no_token, no_item) is unavailable with a
Sync now button and no red error; a denied keychain gives the plain-words message and a Sync now button; the
manual "Enter usage" form, the one-line "Updated ... , source" note.

Node renders web/js/views/usage.js with fake view models (no DOM). The checks: net and other errors keep Sync now;
the form has two labelled decimal inputs wired to usage.set through the form; the markup has no inline style or on*
handler; the source is named in words; normalizeUsage keeps syncError. The node checks are skipped when node is not
installed.
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

INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
NO_AUTO_TITLE = "Usage is old."
NO_AUTO_DETAIL = "It updates by itself when the service can read it; see docs/USAGE-SOURCES.md."
UNAVAILABLE_DETAIL = "No Claude Code login on this Mac: run claude auth login once (docs/USAGE-SOURCES.md)."

SCRIPT = """
const usage = await import(process.argv[1]);
const state = await import(process.argv[2]);
const now = 1800000000000;
const base = { loaded: true, weeklyPercent: 40, fiveHourPercent: 10, weeklyResetsAt: null,
  fiveHourResetsAt: null, ageNow: 300, stale: false, veryOld: false, lastError: "keychain entry has no usable token",
  source: "manual push", sync: null };
const vm = (extra) => ({ view: "home", route: { name: "home" }, now: now, projects: [],
  usage: Object.assign({}, base, extra) });
const out = {
  noToken: usage.usageView(vm({ syncError: "no_token", veryOld: true })),
  noItem: usage.usageView(vm({ syncError: "no_item", stale: true, veryOld: true })),
  denied: usage.usageView(vm({ syncError: "denied", veryOld: true, source: "Anthropic usage endpoint" })),
  net: usage.usageView(vm({ syncError: "net", veryOld: true })),
  other: usage.usageView(vm({ syncError: "other", veryOld: true })),
  plainOld: usage.usageView(vm({ syncError: null, veryOld: true })),
  norm: state.normalizeUsage({ syncError: "denied", lastError: null }, now).syncError,
};
console.log(JSON.stringify(out));
"""


class UsageEntryTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the usage band render check is skipped")
        usage_url = "file://" + os.path.join(WEB, "js", "views", "usage.js")
        state_url = "file://" + os.path.join(WEB, "js", "state.js")
        proc = subprocess.run([shutil.which("node"), "--input-type=module", "-e", SCRIPT, usage_url, state_url],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr[-800:])
        cls.html = json.loads(proc.stdout)

    def test_denied_says_so_in_plain_words(self):
        self.assertIn(NO_AUTO_TITLE, self.html["denied"])
        self.assertIn(NO_AUTO_DETAIL, self.html["denied"])
        self.assertNotIn("Usage data outdated", self.html["denied"])

    def test_no_login_is_unavailable_not_an_error(self):
        for key in ("noToken", "noItem"):
            self.assertIn(NO_AUTO_TITLE, self.html[key], key)
            self.assertIn(UNAVAILABLE_DETAIL, self.html[key], key)
            self.assertNotIn("Usage data outdated", self.html[key], key)
            self.assertNotIn("is-danger", self.html[key], key)
            self.assertNotIn("keychain entry has no usable token", self.html[key], key)

    def test_no_login_offers_sync_now(self):
        for key in ("noToken", "noItem"):
            self.assertIn('data-action="sync-usage"', self.html[key], key)
            self.assertIn("Sync now", self.html[key], key)
            self.assertNotIn("Request update", self.html[key], key)

    def test_denied_offers_sync_now(self):
        self.assertIn('data-action="sync-usage"', self.html["denied"])
        self.assertIn("Sync now", self.html["denied"])
        self.assertNotIn("Request update", self.html["denied"])

    def test_net_and_other_errors_keep_sync_now(self):
        for key in ("net", "other", "plainOld"):
            self.assertIn('data-action="sync-usage"', self.html[key], key)
            self.assertIn("Sync now", self.html[key], key)

    def test_stale_reading_without_error_keeps_the_old_banner(self):
        self.assertIn("Usage data outdated: ", self.html["plainOld"])

    def test_entry_form_has_two_labelled_decimal_inputs(self):
        html = self.html["noToken"]
        self.assertIn("data-usage-entry", html)
        self.assertIn('<form class="tk-override usage-entry" data-usage-entry novalidate>', html)
        for label in ("This week %", "Last 5 hours %"):
            self.assertIn('<span class="lim-label">' + label + "</span>", html)
        self.assertEqual(html.count('inputmode="decimal"'), 2)
        self.assertEqual(html.count('data-usage-field="'), 2)
        self.assertIn('type="submit"', html)

    def test_source_and_age_share_one_line(self):
        self.assertRegex(self.html["noToken"], r'<span class="band-sub">Updated [^<]*, by the head from the app</span>')
        self.assertRegex(self.html["denied"], r'<span class="band-sub">Updated [^<]*, synced</span>')

    def test_markup_has_no_inline_style_or_handlers(self):
        for key, html in self.html.items():
            if key == "norm":
                continue
            self.assertIsNone(INLINE.search(html), key)

    def test_normalize_keeps_sync_error(self):
        self.assertEqual(self.html["norm"], "denied")


if __name__ == "__main__":
    unittest.main()
