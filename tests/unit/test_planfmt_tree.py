"""Tests for the plan tree grammar in planfmt: the optional ask word on F lines, parents defined earlier or later in
one import, levels deeper than three, parent loops, and the export and import round trip."""

import unittest

from roadmap.core import planfmt


class AskTokenTests(unittest.TestCase):
    def test_ask_round_trips_with_the_plan_order_kept(self):
        text = "F F5 - 1 R1 F4 ask | Offline sync # offline edits merge on reconnect"
        records, errors = planfmt.parse_plan(text + "\n")
        self.assertEqual(errors, [])
        self.assertIs(records[0]["ask"], True)
        self.assertEqual(planfmt.format_feature(records[0]), text)

    def test_ask_is_omitted_when_false(self):
        records, errors = planfmt.parse_plan("F F4 - 1 R1 - | Requirements\n")
        self.assertEqual(errors, [])
        self.assertNotIn("ask", records[0])
        self.assertEqual(planfmt.format_feature({"id": "F4", "title": "Requirements", "prio": 1, "phase": "R1",
                                                 "parent": None, "ask": False}), "F F4 - 1 R1 - | Requirements")

    def test_ask_on_a_hold_top_level_feature(self):
        records, errors = planfmt.parse_plan("F F9 hold 2 - - ask | Later\n")
        self.assertEqual(errors, [])
        self.assertEqual(planfmt.format_feature(records[0]), "F F9 hold 2 - - ask | Later")

    def test_other_word_in_place_of_ask_is_an_error(self):
        _, errors = planfmt.parse_plan("F F4 - 1 R1 - maybe | Requirements\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("line 1: 'maybe' is not valid after the parent (allowed: ask, or nothing)", errors[0])

    def test_seven_tokens_without_ask_keep_the_shape_error(self):
        _, errors = planfmt.parse_plan("F F4 - 1 R1 - ask ask | Requirements\n")
        self.assertIn("line 1: feature line needs an id, status, prio, phase, parent", errors[0])


class ForwardParentTests(unittest.TestCase):
    def test_parent_defined_later_in_the_same_import_is_fine(self):
        text = "F F8 - 1 R2 F7 | Storage layer\nF F7 - 1 R2 - | Core engine\n"
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        self.assertEqual([rec["id"] for rec in records], ["F8", "F7"])

    def test_three_levels_in_one_import_are_allowed(self):
        text = ("F F1 - 1 R0 - | Top\n"
                "F F2 - 1 R0 F1 | Sub plan\n"
                "F F3 - 1 R0 F2 | Item\n")
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 3)


class DepthAndLoopTests(unittest.TestCase):
    def test_fourth_level_is_an_error_with_the_line_and_a_next_hint(self):
        text = ("F F1 - 1 R0 - | Top\n"
                "F F2 - 1 R0 F1 | Sub plan\n"
                "F F3 - 1 R0 F2 | Item\n"
                "F F4 - 1 R0 F3 | Too deep\n")
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(len(records), 4)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("line 4: F4 would be level 4 (allowed: 3 levels"), errors[0])
        self.assertIn("next: move F4 to a parent one level up", errors[0])

    def test_depth_error_uses_the_line_of_the_deep_feature_when_parent_comes_later(self):
        text = ("F F4 - 1 R0 F3 | Too deep\n"
                "F F3 - 1 R0 F2 | Item\n"
                "F F2 - 1 R0 F1 | Sub plan\n"
                "F F1 - 1 R0 - | Top\n")
        _, errors = planfmt.parse_plan(text)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("line 1: F4 would be level 4"), errors[0])

    def test_parent_loop_is_an_error_with_the_line(self):
        _, errors = planfmt.parse_plan("F F1 - 1 R0 F2 | A\nF F2 - 1 R0 F1 | B\n")
        self.assertEqual(len(errors), 2)
        self.assertTrue(errors[0].startswith("line 1: F1 is its own ancestor (parent loop back to F1)"), errors[0])
        self.assertIn("next: set the parent of F1 to -", errors[0])

    def test_parent_outside_the_input_is_not_checked_here(self):
        records, errors = planfmt.parse_plan("F F9 - 1 R0 F8 | Child of a stored feature\n")
        self.assertEqual(errors, [])
        self.assertEqual(records[0]["parent"], "F8")

    def test_round_trip_of_an_export_has_no_changes(self):
        stored = [
            {"id": "F1", "title": "Research", "acc": "brief", "prio": 1, "parent": None, "phase": "R0",
             "hold": False},
            {"id": "F5", "title": "Offline sync", "acc": "", "prio": 1, "parent": "F1", "phase": "R1",
             "hold": False, "ask": True},
            {"id": "F6", "title": "Export to PDF", "acc": "A4", "prio": 2, "parent": "F5", "phase": None,
             "hold": True},
        ]
        text = "\n".join(planfmt.format_feature(item) for item in stored) + "\n"
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        self.assertEqual([planfmt.format_feature(rec) for rec in records], text.splitlines())
        self.assertIs(records[1]["ask"], True)
        self.assertNotIn("ask", records[0])


if __name__ == "__main__":
    unittest.main()
