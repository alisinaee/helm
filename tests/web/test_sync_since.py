"""Client side of the snapshot ?since=<rev> answer (R9.19): api.js builds the since URL and reports a 304 with no kept
body as unchanged; app.js sends the stored rev on each snapshot read and skips the render of a pass that changed
nothing (at least every SKIP_RENDER_MAX_MS). Static checks only: the files are read as text."""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
API = os.path.join(REPO, "web", "js", "api.js")
APP = os.path.join(REPO, "web", "js", "app.js")


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


class SinceUrlTests(unittest.TestCase):
    def setUp(self):
        self.api = read(API)
        self.body = function_body(self.api, "sinceUrl")

    def test_since_url_is_exported(self):
        self.assertRegex(self.api, r"export\s+function\s+sinceUrl\s*\(")

    def test_empty_rev_leaves_url_unchanged(self):
        self.assertRegex(self.body, r"if\s*\(\s*!rev\s*\)\s*return\s+url;")

    def test_query_separator_is_chosen_and_rev_is_encoded(self):
        self.assertIn('url.indexOf("?") >= 0 ? "&" : "?"', self.body)
        self.assertIn('"since=" + encodeURIComponent(rev)', self.body)


class GetJsonNotModifiedTests(unittest.TestCase):
    def setUp(self):
        self.body = function_body(read(API), "getJson")

    def test_304_with_kept_body_is_unchanged(self):
        self.assertRegex(self.body, r"if\s*\(\s*cached\s*\)\s*return\s*\{[^}]*changed:\s*false")

    def test_304_without_kept_body_is_unchanged_with_null_data(self):
        self.assertRegex(self.body, r"return\s*\{\s*status:\s*304,\s*data:\s*null,\s*etag:\s*null,\s*changed:\s*false\s*\}")

    def test_304_is_handled_before_the_ok_check(self):
        self.assertLess(self.body.find("response.status === 304"), self.body.find("!response.ok"))


class RefreshSinceTests(unittest.TestCase):
    def setUp(self):
        self.app = read(APP)
        self.refresh = function_body(self.app, "refresh")
        self.loop = function_body(self.app, "loop")

    def test_app_imports_since_url(self):
        self.assertRegex(self.app, r'import\s*\{[^}]*\bsinceUrl\b[^}]*\}\s*from\s*"\./api\.js"')

    def test_snapshot_read_sends_the_stored_rev(self):
        self.assertIn('sinceUrl("/api/v1/projects/" + encodeURIComponent(id) + "/snapshot", storedRev(id))',
                      self.refresh)

    def test_refresh_reports_whether_anything_changed(self):
        self.assertRegex(self.refresh, r"let\s+changed\s*=\s*false;")
        self.assertRegex(self.refresh, r"return\s+changed;")
        self.assertRegex(self.refresh, r"if\s*\(\s*res\.changed\s*\)\s*\{[^}]*changed\s*=\s*true;")

    def test_loop_skips_render_when_nothing_changed(self):
        self.assertRegex(self.loop, r"changed\s*=\s*await\s+refresh\(\);")
        self.assertRegex(self.loop, r"if\s*\(\s*changed\s*\|\|\s*followUp\s*\|\|\s*due\s*\)\s*\{\s*render\(\);")

    def test_skip_render_has_a_time_bound(self):
        self.assertRegex(self.app, r"const\s+SKIP_RENDER_MAX_MS\s*=\s*\d+;")
        self.assertIn("Date.now() - lastRenderAt >= SKIP_RENDER_MAX_MS", self.loop)

    def test_loop_always_reschedules_even_when_render_throws(self):
        self.assertRegex(self.loop, r"\}\s*finally\s*\{\s*const again = followUp;[\s\S]*schedule\(")

    def test_get_requests_time_out(self):
        api = read(API)
        self.assertIn("GET_TIMEOUT_MS", api)
        self.assertIn("AbortController", api)

    def test_no_sse_added(self):
        self.assertNotIn("EventSource", self.app)
        self.assertNotIn("EventSource", read(API))


if __name__ == "__main__":
    unittest.main()
