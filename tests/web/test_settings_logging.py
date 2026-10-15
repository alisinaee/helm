"""Checks for Settings > Logging (R7.16 step 5a) in web/js/views/settings.js: the switch goes through log.js setEnabled(),
the status line reads GET /api/v1/log/status, the copy button reads GET /api/v1/log/report?n=30 as text, the log
folder is not opened from here, the Mark button is not added, and the markup follows the CSP and dom.js rules.
The checks read the source only (no browser, no network).
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
SETTINGS_JS = os.path.join(REPO, "web", "js", "views", "settings.js")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class SettingsLoggingSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(SETTINGS_JS)

    def test_switch_uses_log_client(self):
        self.assertIn('import { setEnabled, status as logStatusNow } from "../log.js";', self.src)
        self.assertIn('setEnabled(el.getAttribute("data-value") === "on")', self.src)
        self.assertIn('data-action="log-report"', self.src)
        self.assertIn('"set-log"', self.src)

    def test_switch_is_on_and_off_buttons_with_pressed_state(self):
        self.assertIn('{ id: "on", label: "On" }', self.src)
        self.assertIn('{ id: "off", label: "Off" }', self.src)
        self.assertIn("aria-checked", self.src)

    def test_switch_label_and_group_name(self):
        self.assertIn("Record what happens in this dashboard (stays on this Mac)", self.src)

    def test_status_route_is_read_only_and_never_shows_contents(self):
        self.assertIn('const LOG_STATUS_URL = "/api/v1/log/status";', self.src)
        self.assertIn("getJson(LOG_STATUS_URL)", self.src)
        self.assertNotIn("api/v1/log/status", re.sub(r'"/api/v1/log/status"', "", self.src))

    def test_report_is_same_origin_get_text(self):
        self.assertIn('const LOG_REPORT_URL = "/api/v1/log/report?n=30";', self.src)
        self.assertRegex(self.src, r'fetch\(LOG_REPORT_URL, \{\s*method: "GET",')
        self.assertIn('credentials: "same-origin"', self.src)
        self.assertIn("await res.text()", self.src)

    def test_report_failure_is_a_sentence_and_does_not_throw(self):
        self.assertIn("The debug report could not be read.", self.src)
        self.assertIn("copyReport().catch(function () {});", self.src)

    def test_copy_uses_clipboard_with_read_only_fallback(self):
        self.assertIn("nav.clipboard.writeText(text)", self.src)
        self.assertIn("field.readOnly = true;", self.src)
        self.assertIn("field.select();", self.src)
        self.assertIn('showToast({ text: "Copied" });', self.src)

    def test_no_open_folder_and_no_mark_action(self):
        lowered = self.src.lower()
        self.assertNotIn("open folder", lowered)
        self.assertNotIn("open-folder", lowered)
        self.assertNotIn("mark", lowered)

    def test_aria_labels_and_focus_hooks(self):
        self.assertIn('aria-label="Copy debug report"', self.src)
        self.assertIn('data-focus="log-report"', self.src)
        self.assertIn('aria-live="polite"', self.src)

    def test_csp_and_dom_rules(self):
        self.assertNotIn("innerHTML", self.src)
        self.assertNotIn("style=", self.src)
        self.assertNotIn("<script", self.src.lower())
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", self.src))

    def test_phone_has_no_logging_section(self):
        self.assertIn("const logging = typeof document !== \"undefined\" && csrfToken() ? loggingHtml() : \"\";",
                      self.src)

    def test_lines_fit_120_columns(self):
        for number, line in enumerate(self.src.split("\n"), 1):
            self.assertLessEqual(len(line), 120, "line %d is %d columns" % (number, len(line)))

    def test_one_sentence_mentions_roadmap_logs(self):
        self.assertIn("agents can read it with roadmap logs.", self.src)
        self.assertIn("never form values or passwords", self.src)


if __name__ == "__main__":
    unittest.main()
