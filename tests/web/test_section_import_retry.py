"""Static checks for R10.17: a failed section import is retried, not latched as "Coming soon".

web/js/app.js must not keep a failed import (no missingSections latch). A failure shows an inline "Could not load this
section" state with a Retry button (data-action section-retry), and one automatic retry runs after about 1 s. The retry
URL gets a query, because the browser caches a failed module URL. tools/ui_smoke.py waits for the section's marker.
"""

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

    def test_one_automatic_retry_after_about_a_second(self):
        self.assertIn("const AUTO_RETRY_MS = 1000;", self.app)
        ensure = function_body(self.app, "ensureLoaded")
        self.assertIn("autoRetried.has(section.id)", ensure)
        self.assertIn("}, AUTO_RETRY_MS);", ensure)

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
