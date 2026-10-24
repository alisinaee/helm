"""Static checks for R10.17: a failed section import is retried, not latched as "Coming soon".

web/js/app.js must not keep a failed import (no missingSections latch). A failure shows an inline "Could not load this
section" state with a Retry button (data-action section-retry), and one automatic retry runs after about 1 s. The retry
URL gets a query, because the browser caches a failed module URL. tools/ui_smoke.py waits for the section's marker.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
APP = os.path.join(REPO, "web", "js", "app.js")
SMOKE = os.path.join(REPO, "tools", "ui_smoke.py")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def function_body(src, name):
    match = re.search(r"\nfunction " + re.escape(name) + r"\([^)]*\) \{\n(.*?)\n\}\n", src, re.S)
    return match.group(1) if match else None


class SectionImportRetryTests(unittest.TestCase):
    def setUp(self):
        self.app = read(APP)

    def test_no_latch_of_failed_imports(self):
        self.assertNotIn("missingSections", self.app)
        ensure = function_body(self.app, "ensureLoaded")
        self.assertIsNotNone(ensure)
        self.assertIn("importErrors.set(section.id", ensure)
        self.assertIn("importErrors.delete(section.id)", ensure)

    def test_module_url_gets_a_query_on_retry(self):
        ensure = function_body(self.app, "ensureLoaded")
        self.assertIn('"?retry=" + tries', ensure)
        self.assertIn("tries > 1", ensure)

    def test_network_failures_retry_with_backoff_and_on_reconnect(self):
        ensure = function_body(self.app, "ensureLoaded")
        self.assertIn("importVerdict(", ensure)
        self.assertIn("scheduleRetry(section.id, tries)", ensure)
        self.assertIsNotNone(function_body(self.app, "retryAllSections"))
        self.assertIn("if (wasOk === false && store.conn.ok) retryAllSections();", self.app)
        self.assertIn("Reconnecting", function_body(self.app, "mainHtml"))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_retry_policy(self):
        script = (
            'import { retryDelayMs, isNetworkError, importVerdict } from %r;'
            'const e = new TypeError("Failed to fetch dynamically imported module: x");'
            'console.log(JSON.stringify([[1,2,3,4,5,9].map(retryDelayMs), isNetworkError(e),'
            ' isNetworkError(new SyntaxError("bad")), importVerdict(e, 0, 29000), importVerdict(e, 0, 30000),'
            ' importVerdict(new SyntaxError("x"), 0, 10)]));'
        ) % ("file://" + os.path.join(REPO, "web", "js", "retry.js"))
        out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout),
                         [[1000, 2000, 4000, 8000, 15000, 15000], True, False, "quiet", "error", "error"])

    def test_inline_error_with_retry_button(self):
        body = function_body(self.app, "importErrorHtml")
        self.assertIsNotNone(body)
        self.assertIn("Could not load this section", body)
        self.assertIn('data-action="section-retry"', body)
        self.assertIn('data-section="\' + esc(section.id) +', body)
        self.assertIn('"section-retry"', self.app)
        self.assertIn("retrySection(el.getAttribute(\"data-section\"))", self.app)

    def test_main_shows_error_state_without_reimporting_in_a_loop(self):
        main = function_body(self.app, "mainHtml")
        self.assertIsNotNone(main)
        error_at = main.index("importErrorHtml(section)")
        ensure_at = main.index("ensureLoaded(section)")
        self.assertLess(error_at, ensure_at)

    def test_failed_import_never_shows_coming_soon(self):
        main = function_body(self.app, "mainHtml")
        self.assertIn("if (!section.module) return comingSoonHtml(section);", main)
        self.assertEqual(main.count("comingSoonHtml("), 2)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_app_js_parses(self):
        result = subprocess.run(["node", "--check", APP], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class SmokeWaitsForMarkerTests(unittest.TestCase):
    def test_ready_needs_the_section_marker(self):
        src = read(SMOKE)
        match = re.search(r"def app_ready\(scan, marker=None\):.*?\n\n", src, re.S)
        self.assertIsNotNone(match)
        self.assertIn('scan.has("." + (marker or PAGE_MARK))', match.group(0))
        self.assertIn("lambda found: app_ready(found, marker)", src)


if __name__ == "__main__":
    unittest.main()
