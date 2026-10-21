"""Loading state for buttons that wait on the server (docs/MOTION-PLAN.md, JS worker). Stdlib only; the files are read
as text, nothing runs in node.

busy.js must export setBusy and withBusy, withBusy must clear the busy mark in a finally, and the views that already
track a busy action (tokens_history.js) must draw aria-busy="true" on the pressed button. The write views import
withBusy from busy.js.
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
JS = os.path.join(REPO, "web", "js")
BUSY = os.path.join(JS, "busy.js")
TOKENS_HISTORY = os.path.join(JS, "views", "tokens_history.js")
WRITERS = {
    "git.js": os.path.join(JS, "views", "git.js"),
    "rules.js": os.path.join(JS, "views", "rules.js"),
    "limits_v2.js": os.path.join(JS, "views", "limits_v2.js"),
    "cmd.js": os.path.join(JS, "cmd.js"),
    "app.js": os.path.join(JS, "app.js"),
}


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def function_body(source, name):
    """The text of `function name(...) {...}` (brace matched), or '' when absent."""
    match = re.search(r"(?:export\s+)?(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(", source)
    if not match:
        return ""
    start = source.index("{", match.end())
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    return ""


class BusyModuleTests(unittest.TestCase):
    def setUp(self):
        self.source = read(BUSY)

    def test_exports_set_busy_and_with_busy(self):
        self.assertRegex(self.source, r"export\s+function\s+setBusy\s*\(")
        self.assertRegex(self.source, r"export\s+async\s+function\s+withBusy\s*\(")

    def test_with_busy_clears_the_mark_in_finally(self):
        body = function_body(self.source, "withBusy")
        self.assertTrue(body, "withBusy not found")
        self.assertRegex(body, r"finally\s*\{[^}]*setBusy\(\s*el\s*,\s*false\s*\)")

    def test_with_busy_sets_the_mark_before_awaiting(self):
        body = function_body(self.source, "withBusy")
        self.assertLess(body.index("setBusy(el, true)"), body.index("await"))

    def test_set_busy_uses_aria_busy_and_disabled(self):
        body = function_body(self.source, "setBusy")
        self.assertIn('setAttribute("aria-busy", "true")', body)
        self.assertIn('removeAttribute("aria-busy")', body)
        self.assertIn("disabled", body)

    def test_no_dom_at_import(self):
        # Top-level code is only declarations and comments: no document or window access outside functions.
        top = re.sub(r"function\s+\w+\s*\([^)]*\)\s*\{.*?\n\}", "", self.source, flags=re.S)
        top = re.sub(r"async\s+function\s+\w+\s*\([^)]*\)\s*\{.*?\n\}", "", top, flags=re.S)
        self.assertNotRegex(top, r"\b(document|window)\b")


class TokensHistoryBusyTests(unittest.TestCase):
    def setUp(self):
        self.source = read(TOKENS_HISTORY)

    def test_pressed_account_button_emits_aria_busy(self):
        self.assertIn('return acct.busy === act && acct.busyId === id ? \' aria-busy="true"\' : "";', self.source)
        self.assertIn('aria-busy="true"', self.source)

    def test_account_buttons_use_the_busy_attribute(self):
        for helper in ("acctButton", "removeButton"):
            body = function_body(self.source, helper)
            self.assertIn("busyAttr(", body, helper + " must call busyAttr")

    def test_add_paths_record_their_busy_id(self):
        self.assertIn('acct.busyId = "form";', self.source)
        self.assertIn('acct.busyId = "default";', self.source)
        self.assertIn("acct.busyId = id;", self.source)


class WritersUseWithBusyTests(unittest.TestCase):
    def test_writing_modules_import_with_busy(self):
        for name, path in WRITERS.items():
            with self.subTest(module=name):
                source = read(path)
                self.assertRegex(source, r"import\s*\{[^}]*\bwithBusy\b[^}]*\}\s*from\s*\"(\.\./|\./)busy\.js\"")
                # At least one call site (the import line has no parenthesis).
                self.assertGreaterEqual(len(re.findall(r"\bwithBusy\(", source)), 1)

    def test_views_marking_the_pressed_button_are_wired(self):
        self.assertIn("withBusy(el, postJson", read(os.path.join(JS, "views", "rules.js")))
        self.assertIn("busyEl", read(os.path.join(JS, "views", "rules.js")))
        self.assertIn("busyEl", read(os.path.join(JS, "cmd.js")))
        self.assertIn("withBusy(busyOn", read(os.path.join(JS, "cmd.js")))
        self.assertIn('withBusy(el, load(pid))', read(WRITERS["git.js"]))
        self.assertIn('document.querySelector(\'[data-action="sync-usage"]\')', read(WRITERS["app.js"]))


if __name__ == "__main__":
    unittest.main()
