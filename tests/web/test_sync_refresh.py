"""Checks for the client refresh queue and the usage sync refresh (R7.40, review finding 3 and 5).

A refresh requested while another refresh is in flight (a write through refreshNow, a route change) must queue one
follow-up refresh instead of being dropped by the regular poll timer. A successful usage sync must schedule a refresh so
the snapshot meters are updated, not only the usage band. The checks read web/js/app.js and web/js/cmd.js as text and
also confirm that neither file adds inline script or inline style (CSP).
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
APP = os.path.join(REPO, "web", "js", "app.js")
CMD = os.path.join(REPO, "web", "js", "cmd.js")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def function_body(source, name):
    match = re.search(r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", source)
    if not match:
        return ""
    depth = 0
    for index in range(match.end() - 1, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():index + 1]
    return ""


class LoopQueueTests(unittest.TestCase):
    def setUp(self):
        self.app = read(APP)
        self.loop = function_body(self.app, "loop")

    def test_loop_exists(self):
        self.assertTrue(self.loop, "loop() not found in app.js")

    def test_follow_up_flag_declared(self):
        self.assertRegex(self.app, r"let\s+followUp\s*=\s*false")

    def test_busy_request_queues_follow_up_instead_of_dropping(self):
        self.assertRegex(self.loop, r"if\s*\(\s*busy\s*\)\s*\{\s*followUp\s*=\s*true;\s*return;\s*\}")

    def test_loop_reschedules_immediately_when_follow_up_is_queued(self):
        self.assertRegex(self.loop, r"const\s+again\s*=\s*followUp;")
        self.assertRegex(self.loop, r"followUp\s*=\s*false;")
        self.assertRegex(self.loop, r"schedule\(\s*again\s*\?\s*0\s*:")

    def test_busy_flag_is_cleared_before_scheduling(self):
        finally_index = self.loop.find("finally")
        self.assertGreater(finally_index, -1)
        self.assertLess(self.loop.find("busy = false", finally_index), self.loop.find("schedule("))

    def test_refresh_now_path_uses_schedule_zero(self):
        self.assertIn("refresh: function () {\n      schedule(0);", self.app)


class UsageSyncRefreshTests(unittest.TestCase):
    def setUp(self):
        self.body = function_body(read(APP), "syncUsage")

    def test_sync_function_exists(self):
        self.assertTrue(self.body, "syncUsage() not found in app.js")

    def test_successful_sync_schedules_refresh_after_usage_update(self):
        success = self.body.find('store.sync = { state: "ok"')
        self.assertGreater(success, -1)
        self.assertGreater(self.body.find("schedule(0)", success), success)

    def test_failed_sync_does_not_schedule_refresh(self):
        catch = self.body.find("catch (err)")
        self.assertGreater(catch, -1)
        self.assertEqual(self.body.find("schedule(0)", catch), -1)


class CspTests(unittest.TestCase):
    def test_no_inline_script_or_style_in_client_files(self):
        for path in (APP, CMD):
            source = read(path)
            self.assertNotIn("<script", source, path)
            self.assertNotIn("<style", source, path)
            self.assertNotRegex(source, r"\sstyle\s*=\s*[\"']", path)
            self.assertNotRegex(source, r"\son[a-z]+\s*=\s*[\"']", path)


if __name__ == "__main__":
    unittest.main()
