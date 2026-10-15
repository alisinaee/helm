"""R7.13 H3b: `plan import` honours the 3-level plan tree (phase > sub plan > item) with core/features.py's rules.

Depth, loops and forward parents within one input are checked by planfmt; the service checks the parent chain that
reaches into stored features, and the whole subtree of each imported feature. Errors carry the line and a next command,
and a refused input writes nothing (tasks.json and features.json stay as they were).
"""

import os
import unittest

from tests.unit.test_cmd_support import CmdCase


def write(case, name, lines):
    path = os.path.join(case.tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


CHAIN = [
    "F F10 - 1 P1 - | Top",
    "F F11 - 1 P1 F10 | Middle",
    "F F12 - 1 P1 F11 | Leaf",
]


class ImportTree(CmdCase):
    def test_three_levels_import_in_one_file_even_with_the_parent_last(self):
        path = write(self, "chain.txt", list(reversed(CHAIN)))
        code, out, err = self.cli(["plan", "import", path])
        self.assertEqual(code, 0, err)
        _, tree, _ = self.cli(["feature", "tree"])
        self.assertIn("    P0.0.0 F12 uncovered 0/0 Leaf", tree)

    def test_a_fourth_level_in_one_file_is_refused_with_line_and_next(self):
        path = write(self, "deep.txt", CHAIN + ["F F13 - 1 P1 F12 | Too deep"])
        code, _, err = self.cli(["plan", "import", path])
        self.assertNotEqual(code, 0)
        self.assertIn("line 4: F13 would be level 4", err)
        self.assertIn("next: move F13 to a parent one level up", err)

    def test_a_fourth_level_under_a_stored_chain_is_refused(self):
        self.assertEqual(self.cli(["plan", "import", write(self, "chain.txt", CHAIN)])[0], 0)
        path = write(self, "under.txt", ["F F13 - 1 P1 F12 | Too deep"])
        code, _, err = self.cli(["plan", "import", path])
        self.assertNotEqual(code, 0)
        self.assertIn("line 1: F13 would be level 4", err)

    def test_moving_a_stored_subtree_down_checks_its_sub_features(self):
        self.assertEqual(self.cli(["plan", "import", write(self, "chain.txt", CHAIN)])[0], 0)
        path = write(self, "move.txt", ["F F20 - 1 P1 - | Other", "F F10 - 1 P1 F20 | Top"])
        code, _, err = self.cli(["plan", "import", path])
        self.assertNotEqual(code, 0)
        self.assertIn("line 2: F10 would be level 4 with its sub-features", err)
        self.assertIn("next: roadmap feature move F10 --parent -", err)

    def test_a_parent_loop_in_one_file_is_refused(self):
        path = write(self, "loop.txt", ["F F1 - 1 P1 F2 | A", "F F2 - 1 P1 F1 | B"])
        code, _, err = self.cli(["plan", "import", path])
        self.assertNotEqual(code, 0)
        self.assertIn("line 1: F1 is its own ancestor (parent loop back to F1)", err)

    def test_a_parent_that_is_not_stored_or_in_the_file_is_refused(self):
        path = write(self, "gone.txt", ["F F5 - 1 P1 F9 | Orphan"])
        code, _, err = self.cli(["plan", "import", path])
        self.assertNotEqual(code, 0)
        self.assertIn("line 1: parent F9 does not exist", err)

    def test_a_refused_input_writes_nothing(self):
        before = self.cli(["feature", "tree"])[1]
        path = write(self, "deep.txt", CHAIN + ["F F13 - 1 P1 F12 | Too deep"])
        self.assertNotEqual(self.cli(["plan", "import", path])[0], 0)
        self.assertEqual(self.cli(["feature", "tree"])[1], before)
        self.assertNotIn("F10", self.cli(["feature", "tree"])[1])


if __name__ == "__main__":
    unittest.main()
