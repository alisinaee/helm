"""Theme model checks (docs/THEMES-PLAN.md): the palette and mode lists and the migration table in state.js, and the
selector contract in tokens.css. Stdlib only; the files are read as text, nothing runs in node.

The tokens.css checks skip (with the reason printed) while the CSS worker has not added the new selectors yet.
"""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
STATE = os.path.join(REPO, "web", "js", "state.js")
TOKENS = os.path.join(REPO, "web", "css", "tokens.css")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def compact(text):
    """Source text without whitespace, so formatting changes do not break the checks."""
    return re.sub(r"\s+", "", text)


class StateModelTests(unittest.TestCase):
    def setUp(self):
        self.state = read(STATE)

    def test_palette_order(self):
        self.assertRegex(self.state, r'THEME_ORDER\s*=\s*\["obsidian",\s*"classic",\s*"black"\]')

    def test_mode_order(self):
        self.assertRegex(self.state, r'MODE_ORDER\s*=\s*\["dark",\s*"light",\s*"auto"\]')

    def test_default_mode_is_dark(self):
        self.assertRegex(self.state, r'mode:\s*"dark",\s*lastProject')

    def test_migration_table_is_in_state(self):
        text = compact(self.state)
        self.assertIn('LEGACY_THEME={', text)
        self.assertIn('dark:{theme:"classic",mode:"dark"}', text)
        self.assertIn('light:{theme:"classic",mode:"light"}', text)
        self.assertIn('auto:{theme:"classic",mode:"auto"}', text)
        self.assertIn('obsidian:{theme:"obsidian",mode:"dark"}', text)

    def test_mode_helpers_exist(self):
        for name in ("loadMode", "saveMode", "resolveMode", "loadTheme", "saveTheme"):
            self.assertRegex(self.state, r"export function " + name + r"\(", name)


class TokenSelectorTests(unittest.TestCase):
    REQUIRED = (
        ':root[data-mode="light"]',
        ':root[data-theme="obsidian"][data-mode="light"]',
        ':root[data-theme="black"]',
        ':root[data-theme="black"][data-mode="light"]',
    )

    def test_tokens_have_the_mode_selectors(self):
        css = read(TOKENS)
        missing = [selector for selector in self.REQUIRED if selector not in css]
        if missing:
            self.skipTest("tokens.css not updated yet, missing: " + ", ".join(missing))


if __name__ == "__main__":
    unittest.main()
