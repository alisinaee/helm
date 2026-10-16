"""Static checks for the aria fixes in views a-l (R7.9c). Stdlib only; reads the view sources as text.

Each named control must carry the accessible name written here. Whitespace is collapsed before matching so that
line wraps in the source do not matter. The skipped rows (board filters, limits presets and steppers,
nav collapse) must stay as they were, because their aria-controls values name classes, not ids.
"""

import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIEWS = os.path.join(REPO, "web", "js", "views")

EXPECTED = {
    "activity.js": ['aria-label="\' + label'],
    "agents.js": ['aria-label="\' + esc("Task " + job.task)'],
    "board.js": [
        'aria-label="\' + esc("Move task " + task.id + " to Todo")',
        'aria-label="\' + esc("Queue task " + task.id)',
        'aria-label="\' + esc("Stop task " + task.id)',
        'const colId = "wk-col-" + col.key;',
        'aria-controls="\' + esc(colId)',
    ],
    "details.js": [
        'aria-label="\' + esc("Set status to " + s[1] + " for " + task.id)',
        'aria-label="\' + esc("Start task " + task.id)',
        'aria-label="\' + esc("Stop task " + task.id)',
        'aria-label="Copy launch command"',
        'aria-label="\' + esc("Save token cap for " + task.id)',
        'aria-label="\' + esc("Clear token cap for " + task.id)',
        'aria-label="\' + esc("Add subtask to " + task.id)',
        'aria-label="\' + esc("Add comment to " + task.id)',
        'aria-label="\' + esc("Close issue " + issue.id)',
        'aria-label="\' + esc("Answer " + opt + " for " + question.id)',
        'role="group" aria-label="\' + esc("Answers for " + question.id)',
        'aria-label="\' + esc("Send answer for " + question.id)',
    ],
    "inbox.js": [
        'aria-label="\' + esc("Choose " + part.label + " for " + q.id)',
        'aria-label="\' + esc("View task " + q.task)',
        'aria-label="\' + esc("View task " + entry.item.id)',
        'aria-label="\' + esc("View question " + e.q.id)',
    ],
    "list.js": [
        'aria-label="Start selected tasks"',
        'aria-label="Stop selected tasks"',
        'const label = "Sort by " + h[1]',
        'aria-label="\' + esc(label)',
    ],
}

SKIPPED = {
    "board.js": ['aria-controls="wk-filters"'],
    "nav.js": ['aria-controls="nav-list"'],
}


def normalized(name):
    with open(os.path.join(VIEWS, name), encoding="utf-8") as fh:
        return re.sub(r"\s+", " ", fh.read())


class AriaFixes(unittest.TestCase):
    def test_named_controls_are_present(self):
        missing = []
        for name, needles in EXPECTED.items():
            text = normalized(name)
            for needle in needles:
                if needle not in text:
                    missing.append("%s: %s" % (name, needle))
        self.assertEqual(missing, [])

    def test_skipped_rows_are_unchanged(self):
        found = []
        for name, needles in SKIPPED.items():
            text = normalized(name)
            for needle in needles:
                if needle in text:
                    found.append("%s: %s" % (name, needle))
        # None of these aria-controls values may be added: each one names a class, not an id.
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
