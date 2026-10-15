"""R7.13 H4: `feature tree` (the outline), `feature move`, `feature set` and `--ask` on `feature add`, and
`plan template --tree` (which must import cleanly in a project).

Outline lines: indent by depth, then P1.2 F7 doing 3/5 gaps:1 [ask] title. Lines are in outline order and capped.
"""

import os
import unittest
from unittest import mock

from roadmap.commands import feature
from tests.unit.test_cmd_support import CmdCase
from tests.unit.test_project_support import run_cli


def agent_free_env(case):
    """Run the test without an agent marker in the environment (feature accept is refused for agents)."""
    patch = mock.patch.dict(os.environ, {})
    patch.start()
    case.addCleanup(patch.stop)
    os.environ.pop("CLAUDECODE", None)


class Tree(CmdCase):
    def setUp(self):
        super().setUp()
        agent_free_env(self)
        self.cli(["feature", "add", "Engine"])                         # F1, top level
        self.cli(["feature", "add", "Surface"])                        # F2, top level
        self.cli(["feature", "add", "Offline sync", "--parent", "F1", "--ask"])   # F3 under F1
        self.cli(["feature", "add", "Export", "--parent", "F1"])        # F4 under F1, no tasks yet
        self.cli(["feature", "link", "F1", "P1.1", "P1.2"])
        self.cli(["feature", "link", "F3", "P1.3"])

    def test_tree_is_an_indented_outline_in_outline_order(self):
        code, out, err = self.cli(["feature", "tree"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [
            "P0 F1 todo 0/3 gaps:1 Engine",
            "  P0.0 F3 todo 0/1 [ask] Offline sync",
            "  P0.1 F4 uncovered 0/0 Export",
            "P1 F2 uncovered 0/0 Surface",
            "next: roadmap feature link F4 <TASK>",
        ])

    def test_tree_next_points_at_the_first_uncovered_item_or_the_first_open_one(self):
        self.cli(["feature", "link", "F4", "P2.1"])
        _, out, _ = self.cli(["feature", "tree"])
        self.assertEqual(out.splitlines()[-1], "next: roadmap feature link F2 <TASK>")
        self.cli(["feature", "link", "F2", "P2.1"])
        _, out, _ = self.cli(["feature", "tree"])
        self.assertEqual(out.splitlines()[-1], "next: roadmap feature show F1")

    def test_tree_json_has_the_lines_total_and_next(self):
        code, out = self.envelope(["feature", "tree"])
        self.assertEqual(code, 0)
        self.assertEqual(out["data"]["total"], 4)
        self.assertEqual(out["data"]["lines"][1], "  P0.0 F3 todo 0/1 [ask] Offline sync")
        self.assertEqual(out["data"]["next"], "roadmap feature link F4 <TASK>")

    def test_tree_is_capped_and_says_how_many_more(self):
        with mock.patch.object(feature, "TREE_MAX", 3):
            _, out, _ = self.cli(["feature", "tree"])
        lines = out.splitlines()
        self.assertEqual(lines[:2], ["P0 F1 todo 0/3 gaps:1 Engine", "  P0.0 F3 todo 0/1 [ask] Offline sync"])
        self.assertEqual(lines[2], "+2 more")
        self.assertLessEqual(len(lines), 4)

    def test_tree_lines_fit_the_width(self):
        _, out, _ = self.cli(["feature", "tree"])
        for line in out.splitlines():
            self.assertLessEqual(len(line), 120, line)


class Ask(CmdCase):
    def setUp(self):
        super().setUp()
        agent_free_env(self)

    def test_an_empty_plan_says_so_and_points_at_the_template(self):
        self.assertEqual(self.cli(["feature", "tree"])[1].splitlines(),
                         ["no plan yet", "next: roadmap plan template --tree"])

    def test_add_with_ask_marks_the_item_and_no_ask_clears_it_on_set(self):
        code, out, err = self.cli(["feature", "add", "Offline sync", "--ask"])
        self.assertEqual((code, out.strip()), (0, "F1 added: Offline sync"), err)
        self.assertIn("[ask]", self.cli(["feature", "tree"])[1])
        code, out, err = self.cli(["feature", "set", "F1", "--no-ask"])
        self.assertEqual((code, out.strip()), (0, "F1 not asked for"), err)
        self.assertNotIn("[ask]", self.cli(["feature", "tree"])[1])
        code, out, _ = self.cli(["feature", "set", "F1", "--ask"])
        self.assertEqual(out.strip(), "F1 asked for")

    def test_set_ask_is_an_undoable_write_with_json(self):
        self.cli(["feature", "add", "Visual"])
        code, out = self.envelope(["feature", "set", "F1", "--ask"])
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertIn("activity", out["data"])
        self.assertEqual(out["data"]["changed"], ["ask"])

    def test_add_without_ask_is_not_asked(self):
        self.cli(["feature", "add", "Visual"])
        self.assertNotIn("[ask]", self.cli(["feature", "tree"])[1])


class Move(CmdCase):
    def setUp(self):
        super().setUp()
        agent_free_env(self)
        self.cli(["feature", "add", "Engine"])
        self.cli(["feature", "add", "Surface"])
        self.cli(["feature", "add", "Export", "--parent", "F1"])
        self.cli(["feature", "add", "Sync", "--parent", "F1"])

    def test_move_up_and_down_swap_siblings_and_print_the_new_label(self):
        code, out, err = self.cli(["feature", "move", "F4", "--up"])
        self.assertEqual((code, out.strip()), (0, "F4 now P0.0"), err)
        code, out, err = self.cli(["feature", "move", "F4", "--down"])
        self.assertEqual((code, out.strip()), (0, "F4 now P0.1"), err)

    def test_moving_past_the_edge_is_refused(self):
        code, _, err = self.cli(["feature", "move", "F3", "--up"])
        self.assertNotEqual(code, 0)
        self.assertIn("already first", err)

    def test_move_under_a_parent_and_back_to_the_top_level(self):
        code, out, err = self.cli(["feature", "move", "F3", "--parent", "F2"])
        self.assertEqual((code, out.strip()), (0, "F3 now P1.0"), err)
        code, out, err = self.cli(["feature", "move", "F3", "--parent", "-"])
        self.assertEqual((code, out.strip()), (0, "F3 now P2"), err)

    def test_a_fourth_level_move_is_refused_with_a_next(self):
        self.cli(["feature", "add", "Deep", "--parent", "F4"])
        code, _, err = self.cli(["feature", "move", "F2", "--parent", "F5"])
        self.assertNotEqual(code, 0)
        self.assertIn("3 levels", err)
        self.assertIn("next: ", err)

    def test_move_json_returns_the_envelope(self):
        code, out = self.envelope(["feature", "move", "F4", "--up"])
        self.assertEqual(code, 0)
        self.assertEqual(out["data"]["label"], "P0.0")
        self.assertIn("undo", out["data"])


class PlanTemplateTree(CmdCase):
    def test_the_tree_template_prints_the_spec_example(self):
        code, out, err = run_cli(["plan", "template", "--tree"])
        self.assertEqual(code, 0, err)
        self.assertIn("F F9 - 1 R2 F8 | Schema and migrations", out)
        self.assertIn("T R2.2 todo 30 haiku/low f:F8,F5 | Sync queue", out)
        self.assertNotIn("F F9", run_cli(["plan", "template"])[1])

    # Known blocker (R7.13 H4): services/tasks.py _apply_features still refuses a sub-feature of a sub-feature
    # ("only one level of sub-features"), so the 3-level template does not import yet. Outside H4's files; remove
    # this decorator when that check moves to the 3-level rule.
    def test_the_tree_template_imports_cleanly_in_a_project(self):
        from roadmap.commands.plan import TREE
        path = os.path.join(self.tmp, "tree.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(TREE + "\n")
        code, out, err = self.cli(["plan", "import", path])
        self.assertEqual(code, 0, err)
        _, tree_out, _ = self.cli(["feature", "tree"])
        self.assertIn("  P2.0 F8 todo 0/2 Storage layer", tree_out)
        self.assertIn("    P2.0.0 F9 todo 0/1 Schema and migrations", tree_out)


if __name__ == "__main__":
    unittest.main()
