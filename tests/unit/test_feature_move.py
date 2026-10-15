"""R7.13 H3: feature.move (sibling swap and reparent, both with exact undo), ask on feature add and set, and the
level and cycle refusals. Runs in-process under a temp ROADMAP_HOME through the feature service and ops."""

import unittest

from roadmap.errors import RoadmapError
from roadmap.services import commands, features
from roadmap.store import lock
from tests.unit.test_features_service import FeatureCase


def _ids(data_dir):
    return [f["id"] for f in features.load_doc(data_dir)["features"]]


def _row(data_dir, fid):
    return features.row_of(data_dir, fid)


class MoveSibling(FeatureCase):
    def setUp(self):
        super().setUp()
        for title in ("Alpha", "Beta", "Gamma"):
            self.add(title)

    def test_down_swaps_with_the_next_sibling_and_undo_restores_order(self):
        reply = self.op("feature.move", {"id": "F1", "dir": "down"})
        self.assertEqual(_ids(self.data), ["F2", "F1", "F3"])
        self.assertEqual(reply["data"]["label"], "P1")
        commands.run("undo", {"activity": reply["activity"]}, "cli", self.data)
        self.assertEqual(_ids(self.data), ["F1", "F2", "F3"])

    def test_the_edge_is_refused_with_a_next_hint(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.move", {"id": "F1", "dir": "up"})
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertIn("already first", ctx.exception.message)
        self.assertTrue(ctx.exception.next)

    def test_a_bad_direction_is_a_usage_error(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.move", {"id": "F1", "dir": "sideways"})
        self.assertEqual(ctx.exception.code, "usage")

    def test_only_siblings_swap_so_a_sub_plan_keeps_its_place(self):
        self.add("Child", parent="F1")          # F4 under F1
        self.op("feature.move", {"id": "F3", "dir": "up"})
        self.assertEqual(_ids(self.data), ["F1", "F3", "F2", "F4"])
        self.assertEqual(_row(self.data, "F3")["label"], "P1")
        self.assertEqual(_row(self.data, "F4")["label"], "P0.0")


class Reparent(FeatureCase):
    def setUp(self):
        super().setUp()
        self.add("Phase")                   # F1
        self.add("Sub plan", parent="F1")   # F2
        self.add("Item", parent="F2")       # F3
        self.add("Loose")                   # F4

    def test_reparent_under_a_sub_plan_and_undo_restores_the_order(self):
        before = _ids(self.data)
        reply = self.op("feature.move", {"id": "F4", "parent": "F2"})
        row = _row(self.data, "F4")
        self.assertEqual((row["parent"], row["label"]), ("F2", "P0.0.1"))
        commands.run("undo", {"activity": reply["activity"]}, "cli", self.data)
        self.assertEqual(_ids(self.data), before)
        self.assertIsNone(_row(self.data, "F4")["parent"])

    def test_a_cycle_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.move", {"id": "F1", "parent": "F3"})
        self.assertIn("cycle", ctx.exception.message)
        self.assertTrue(ctx.exception.next)
        with self.assertRaises(RoadmapError):
            self.op("feature.move", {"id": "F1", "parent": "F1"})

    def test_a_fourth_level_is_refused_and_nothing_moves(self):
        before = _ids(self.data)
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.move", {"id": "F4", "parent": "F3"})
        self.assertIn("deeper than 3 levels", ctx.exception.message)
        self.assertEqual(_ids(self.data), before)
        self.assertIsNone(_row(self.data, "F4")["parent"])

    def test_a_subtree_that_would_grow_past_three_levels_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.move", {"id": "F1", "parent": "F4"})     # F4 > F1 > F2 > F3 is four levels
        self.assertIn("deeper than 3 levels", ctx.exception.message)

    def test_top_level_move_and_unknown_parent(self):
        self.op("feature.move", {"id": "F3", "parent": ""})
        self.assertIsNone(_row(self.data, "F3")["parent"])
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.move", {"id": "F3", "parent": "F9"})
        self.assertEqual(ctx.exception.code, "not_found")

    def test_dir_and_parent_together_are_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.move", {"id": "F4", "dir": "up", "parent": "F1"})
        self.assertEqual(ctx.exception.code, "usage")


class Ask(FeatureCase):
    def test_add_and_set_ask_and_undo(self):
        reply = self.add("Offline sync", ask=True)
        self.assertTrue(_row(self.data, "F1")["ask"])
        commands.run("undo", {"activity": reply["activity"]}, "cli", self.data)
        self.add("Export")
        set_reply = self.op("feature.set", {"id": "F1", "ask": True})
        self.assertTrue(_row(self.data, "F1")["ask"])
        commands.run("undo", {"activity": set_reply["activity"]}, "cli", self.data)
        self.assertFalse(_row(self.data, "F1")["ask"])

    def test_ask_never_marks_acceptance(self):
        self.add("Offline sync", ask=True)
        self.assertIsNone(features.load_doc(self.data)["features"][0].get("accepted"))

    def test_ask_must_be_a_bool(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.add("Bad", ask="yes")
        self.assertEqual(ctx.exception.code, "usage")

    def test_plan_rewrite_keeps_ask_and_reports_only_real_changes(self):
        self.add("Offline")
        with lock.locked(self.data):
            first = features.apply_records(self.data, [features.record_of("F1", "Offline", ask=True)])
            again = features.apply_records(self.data, [features.record_of("F1", "Offline", ask=True)])
            cleared = features.apply_records(self.data, [features.record_of("F1", "Offline", ask=False)])
        self.assertEqual(first["changed"], ["F1"])
        self.assertEqual(again["changed"], [])
        self.assertEqual(cleared["changed"], ["F1"])
        self.assertNotIn("ask", features.load_doc(self.data)["features"][0])


if __name__ == "__main__":
    unittest.main()
