"""Checks for the client sync contract (R7.51): a 304 keeps the stored snapshot, pending writes settle on a rev change,
every project whose rev differs is read, and usage comes from snap.usage.

The checks read the client files as text. They confirm the rules in the code, and that no client file adds inline
script or style (CSP) and that no line is wider than 120 columns.
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web", "js")
API = os.path.join(WEB, "api.js")
APP = os.path.join(WEB, "app.js")
CMD = os.path.join(WEB, "cmd.js")
STATE = os.path.join(WEB, "state.js")
TOKENS = os.path.join(WEB, "views", "tokens.js")
CLIENT_FILES = (API, APP, CMD, STATE, TOKENS)


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


class NotModifiedTests(unittest.TestCase):
    def setUp(self):
        self.api = read(API)
        self.app = read(APP)
        self.refresh = function_body(self.app, "refresh")

    def test_get_json_reports_changed_flag(self):
        self.assertRegex(self.api, r"status:\s*304,\s*data:\s*cached\.data,\s*etag:\s*cached\.etag,\s*changed:\s*false")
        self.assertRegex(self.api, r"etag:\s*etag,\s*changed:\s*true")

    def test_304_does_not_normalize_or_store(self):
        self.assertTrue(self.refresh, "refresh() not found in app.js")
        store_line = self.refresh.find("store.snapshots[id] = normalizeSnapshot(res.data, now)")
        self.assertGreater(store_line, -1)
        self.assertRegex(self.refresh[:store_line], r"if\s*\(\s*res\.changed\s*\)")

    def test_snapshot_fetch_time_is_not_set_on_304_path(self):
        self.assertNotIn("fetchedAt: now", self.refresh)
        self.assertNotIn("usageFetchedAt", self.app)


class PendingSettleTests(unittest.TestCase):
    def setUp(self):
        self.cmd = read(CMD)
        self.settled = function_body(self.cmd, "settled")

    def test_settle_compares_rev_not_body_time(self):
        self.assertTrue(self.settled, "settled() not found in cmd.js")
        self.assertRegex(self.settled, r"return\s+rev\s*!==\s*entry\.baseRev;")

    def test_settle_needs_a_reply_first(self):
        self.assertRegex(self.settled, r"if\s*\(\s*entry\.repliedAt\s*===\s*null\s*\)\s*return\s+false;")

    def test_fallback_to_body_time_only_without_rev(self):
        self.assertRegex(self.settled, r"if\s*\(\s*rev\s*===\s*null")
        self.assertIn("fetchedAt > entry.repliedAt", self.settled)

    def test_configure_takes_rev_getter(self):
        self.assertRegex(self.cmd, r"revOf\s*=\s*opts\.rev\s*\|\|\s*revOf;")
        self.assertIn("rev: storedRev", read(APP))

    def test_entries_record_base_rev_when_sent(self):
        self.assertRegex(self.cmd, r"baseRev:\s*revOf\(project\)")


class RefreshAllProjectsTests(unittest.TestCase):
    def setUp(self):
        self.app = read(APP)
        self.ids = function_body(self.app, "idsToRead")

    def test_open_project_is_always_read(self):
        self.assertTrue(self.ids, "idsToRead() not found in app.js")
        self.assertRegex(self.ids, r"route\.name\s*===\s*\"project\"\s*\?\s*\[route\.id\]\s*:\s*\[\]")

    def test_other_projects_read_only_when_rev_differs(self):
        self.assertRegex(self.ids, r"if\s*\(\s*!rev\s*\|\|\s*storedRev\(row\.id\)\s*!==\s*rev\s*\)\s*ids\.push")

    def test_refresh_uses_the_selection(self):
        self.assertIn("idsToRead(route)", function_body(self.app, "refresh"))


class UsageFromSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.app = read(APP)
        self.state = read(STATE)
        self.tokens = read(TOKENS)

    def test_no_separate_usage_poll_or_store(self):
        self.assertNotIn("USAGE_MS", self.app)
        self.assertNotIn("/api/v1/usage\"", self.app)
        self.assertNotIn("store.usage", self.app)
        self.assertNotIn("store.usage", self.state)

    def test_sync_button_posts_then_schedules_poll(self):
        body = function_body(self.app, "syncUsage")
        self.assertIn('postJson("/api/v1/usage/sync", {})', body)
        self.assertIn("schedule(0)", body)

    def test_snapshot_carries_rev_and_usage(self):
        self.assertIn('rev: typeof raw.rev === "string" ? raw.rev : null', self.state)
        self.assertIn("usage: raw.usage && typeof raw.usage === \"object\" ? normalizeUsage(raw.usage, fetchedAt)",
                      self.state)

    def test_view_model_reads_usage_from_snapshot(self):
        self.assertRegex(self.state, r"usage:\s*usageView\(usageSource\(store, route\), store\.sync, now\)")
        source = function_body(self.state, "usageSource")
        self.assertIn("snap.usage", source)

    def test_tokens_notes_missing_usage(self):
        self.assertIn("vm.usage && vm.usage.loaded", self.tokens)


class CspAndWidthTests(unittest.TestCase):
    def test_no_inline_script_or_style_in_client_files(self):
        for path in CLIENT_FILES:
            source = read(path)
            self.assertNotIn("<script", source, path)
            self.assertNotIn("<style", source, path)
            self.assertNotRegex(source, r"\sstyle\s*=\s*[\"']", path)
            self.assertNotRegex(source, r"\son[a-z]+\s*=\s*[\"']", path)

    def test_lines_fit_120_columns(self):
        for path in CLIENT_FILES:
            for number, line in enumerate(read(path).split("\n"), 1):
                self.assertLessEqual(len(line), 120, "%s:%d" % (path, number))


if __name__ == "__main__":
    unittest.main()
