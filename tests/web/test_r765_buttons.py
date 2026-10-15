"""R7.65: action buttons have a short fixed visible label; the full text goes in aria-label and title, and the shared
button classes in action columns keep one line inside their track (no wrap, no overflow). Static checks only."""

import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
VIEWS = os.path.join(REPO, "web", "js", "views")
CSS = os.path.join(REPO, "web", "css", "components.css")

# Views owned by other workers, and head.js, are not checked here.
SKIP = {"tokens.js", "topbar.js", "limits.js", "head.js"}

# Buttons whose visible text is a variable on purpose. Each is a fixed word set by the caller (state, tab, option
# or control name), or a user's own answer or plan item that must be read in full (the answer also has its
# aria-label). A new entry here needs a reason; any other concatenated label fails the test.
ALLOWED = {
    ("board.js", 197): "task state word from a fixed table",
    ("git.js", 195): "git tab name from a fixed list",
    ("settings.js", 50): "option label from a fixed list",
    ("workflow.js", 716): "control text passed by fixed callers",
    ("details.js", 394): "the user's own answer option, full text, aria-label names the question",
    ("planner.js", 117): "plan item text in a picker menu, shown in full",
}

# A button whose visible text is built from a variable: >" + esc(x) + "</button> or >' + esc(x) + '</button>.
DYNAMIC_LABEL = re.compile(r"""\+\s*esc\([^)]*\)\s*\+\s*["']</button>""")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def view_files():
    return sorted(name for name in os.listdir(VIEWS) if name.endswith(".js") and name not in SKIP)


class ButtonLabelTest(unittest.TestCase):
    def test_no_button_label_concatenates_dynamic_text(self):
        found = set()
        for name in view_files():
            for number, line in enumerate(read(VIEWS, name).split("\n"), 1):
                if "</button>" in line and DYNAMIC_LABEL.search(line):
                    found.add((name, number))
        self.assertEqual(sorted(found), sorted(ALLOWED), "new dynamic button label: check the line numbers")

    def test_undo_activity_label_is_short_and_full_text_is_in_title(self):
        text = read(VIEWS, "activity.js")
        self.assertIn('aria-label="\' + esc("Undo " + what)', text)
        self.assertIn('title="\' + esc("Undo " + what)', text)
        self.assertIn('>Undo</button>', text)
        self.assertNotIn('esc("Undo " + what) + "</button>"', text)


class ActionColumnCssTest(unittest.TestCase):
    def test_shared_row_button_keeps_one_line_and_clips(self):
        css = read(CSS)
        self.assertIn(".row-grid > .btn {", css)
        start = css.index(".row-grid > .btn {")
        rule = css[start:css.index("}", start)]
        for decl in ("white-space: nowrap", "overflow: hidden", "text-overflow: ellipsis",
                     "min-width: 0", "max-width: 100%"):
            self.assertIn(decl, rule.replace(";", "; ").replace("  ", " "))

    def test_activity_row_puts_the_button_on_the_text_line_in_a_fixed_column(self):
        css = read(CSS)
        self.assertIn(".row-grid.act-row { grid-template-columns: 5.5rem minmax(0, 1fr) 6.5rem }", css)
        self.assertIn(".row-grid.act-row > .act-main { grid-area: auto; grid-column: 2 }", css)
        self.assertIn(".row-grid.act-row > .btn { white-space: nowrap; margin: 0 }", css)


if __name__ == "__main__":
    unittest.main()
