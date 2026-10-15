"""R7.13 H1 plan tree core: a 3-level parent chain, cycle refusal, rollup over all descendants, gaps, the ask flag,
derived outline labels and the slim snapshot rows. Pure functions only."""

import unittest

from roadmap.core import features


def task(tid, state="todo", tokens=10, feats=None):
    t = {"id": tid, "phase": tid.split(".")[0], "title": "T " + tid, "state": state, "tokensK": float(tokens),
         "thinking": "low", "model": "haiku", "needsUser": False, "check": "none", "checkK": 0.0, "note": None}
    if feats is not None:
        t["feats"] = feats
    return t


def feat(fid, **extra):
    base = {"id": fid, "title": "Feature " + str(fid), "acc": "works", "prio": 2, "parent": None, "phase": None,
            "hold": False, "accepted": None}
    base.update(extra)
    return base


def row(result, fid):
    return next(r for r in result["rows"] if r["id"] == fid)


class DepthTests(unittest.TestCase):
    def test_three_levels_are_allowed(self):
        feats = [feat("F1"), feat("F2", parent="F1"), feat("F3", parent="F2")]
        result = features.derive(feats, [], [])
        self.assertEqual(result["errors"], [])
        self.assertEqual([r["id"] for r in result["rows"]], ["F1", "F2", "F3"])

    def test_a_fourth_level_is_refused_with_a_clear_error(self):
        feats = [feat("F1"), feat("F2", parent="F1"), feat("F3", parent="F2"), feat("F4", parent="F3")]
        result = features.derive(feats, [], [])
        self.assertEqual([r["id"] for r in result["rows"]], ["F1", "F2", "F3"])
        self.assertEqual(result["errors"], [
            "F4: is a 4th level; a plan has at most 3 levels (phase, sub plan, item)"])

    def test_children_of_a_refused_feature_are_refused_too(self):
        feats = [feat("F1"), feat("F2", parent="F1"), feat("F3", parent="F2"), feat("F4", parent="F3"),
                 feat("F5", parent="F4")]
        result = features.derive(feats, [], [])
        self.assertEqual([r["id"] for r in result["rows"]], ["F1", "F2", "F3"])
        self.assertEqual(len(result["errors"]), 2)

    def test_a_forward_parent_in_the_same_list_is_fine(self):
        feats = [feat("F3", parent="F2"), feat("F2", parent="F1"), feat("F1")]
        result = features.derive(feats, [], [])
        self.assertEqual(result["errors"], [])
        self.assertEqual({r["id"] for r in result["rows"]}, {"F1", "F2", "F3"})


class CycleTests(unittest.TestCase):
    def test_two_cycle_is_refused_for_both(self):
        feats = [feat("F1", parent="F2"), feat("F2", parent="F1")]
        result = features.derive(feats, [], [])
        self.assertEqual(result["rows"], [])
        self.assertEqual(len(result["errors"]), 2)
        self.assertTrue(all("cycle" in e for e in result["errors"]))

    def test_a_longer_cycle_is_refused(self):
        feats = [feat("F1", parent="F3"), feat("F2", parent="F1"), feat("F3", parent="F2")]
        self.assertEqual(len(features.validate(feats)), 3)

    def test_a_child_of_a_cycle_is_refused_and_good_features_stay(self):
        feats = [feat("F1"), feat("F2", parent="F3"), feat("F3", parent="F2"), feat("F4", parent="F2")]
        result = features.derive(feats, [], [])
        self.assertEqual([r["id"] for r in result["rows"]], ["F1"])
        self.assertTrue(any("F4" in e for e in result["errors"]))


class RollupTests(unittest.TestCase):
    def test_a_parent_covers_tasks_of_all_descendants(self):
        feats = [feat("F1"), feat("F2", parent="F1"), feat("F3", parent="F2")]
        tasks = [task("A.1", "done", feats=["F3"]), task("A.2", "todo", feats=["F2"])]
        result = features.derive(feats, tasks, [])
        top = row(result, "F1")
        self.assertEqual(top["tasks"], ["A.1", "A.2"])
        self.assertEqual((top["done"], top["total"], top["state"]), (1, 2, "doing"))
        self.assertEqual(row(result, "F2")["tasks"], ["A.1", "A.2"])
        self.assertEqual(row(result, "F3")["tasks"], ["A.1"])

    def test_a_task_linked_at_two_levels_counts_once_in_the_parent(self):
        feats = [feat("F1"), feat("F2", parent="F1")]
        tasks = [task("A.1", "done", feats=["F1", "F2"])]
        self.assertEqual(row(features.derive(feats, tasks, []), "F1")["total"], 1)


class GapsTests(unittest.TestCase):
    def test_gaps_counts_direct_children_with_no_tasks(self):
        feats = [feat("F1"), feat("F2", parent="F1"), feat("F3", parent="F1"), feat("F4", parent="F3")]
        tasks = [task("A.1", "todo", feats=["F4"])]
        result = features.derive(feats, tasks, [])
        self.assertEqual(row(result, "F1")["gaps"], 1)      # F2 has no tasks; F3 has F4's task through its subtree
        self.assertEqual(row(result, "F3")["gaps"], 0)
        self.assertEqual(row(result, "F2")["gaps"], 0)

    def test_hold_children_are_not_gaps(self):
        feats = [feat("F1"), feat("F2", parent="F1", hold=True)]
        self.assertEqual(row(features.derive(feats, [], []), "F1")["gaps"], 0)


class AskTests(unittest.TestCase):
    def test_ask_defaults_to_false_and_accepts_true(self):
        result = features.derive([feat("F1"), feat("F2", ask=True), feat("F3", ask=None)], [], [])
        self.assertEqual([row(result, f)["ask"] for f in ("F1", "F2", "F3")], [False, True, False])

    def test_ask_must_be_a_bool(self):
        for bad in ("yes", 1, 0, []):
            errs = features.validate([feat("F1", ask=bad)])
            self.assertEqual(errs, ["F1: ask must be true or false"], bad)


class OutlineTests(unittest.TestCase):
    def test_labels_follow_file_order_and_depth(self):
        feats = [feat("F1"), feat("F4", parent="F1"), feat("F5", parent="F4"), feat("F6", parent="F4"),
                 feat("F7"), feat("F8", parent="F7")]
        labels = features.outline_labels(features._check(feats)[0])
        self.assertEqual(labels, {"F1": "P0", "F4": "P0.0", "F5": "P0.0.0", "F6": "P0.0.1", "F7": "P1",
                                  "F8": "P1.0"})

    def test_derive_rows_carry_the_derived_label(self):
        result = features.derive([feat("F1"), feat("F2"), feat("F3", parent="F2")], [], [])
        self.assertEqual([r["label"] for r in result["rows"]], ["P0", "P1", "P1.0"])

    def test_labels_are_not_stored_in_the_raw_features(self):
        raw = [feat("F1")]
        features.derive(raw, [], [])
        self.assertNotIn("label", raw[0])


class SlimRowTests(unittest.TestCase):
    def test_slim_rows_drop_priority_estimate_and_spend(self):
        feats = [feat("F1", prio=1), feat("F2", parent="F1")]
        tasks = [task("A.1", "todo", tokens=40, feats=["F2"])]
        slim = features.snapshot_rows(features.derive(feats, tasks, [])["rows"])
        for key in ("prio", "estK", "spentK", "running", "hold"):
            self.assertNotIn(key, slim[0])
        self.assertEqual(slim[0]["label"], "P0")

    def test_ask_and_gaps_appear_only_when_set(self):
        feats = [feat("F1"), feat("F2", parent="F1", ask=True), feat("F3", parent="F1")]
        slim = features.snapshot_rows(features.derive(feats, [], [])["rows"])
        top, asked, plain = slim
        self.assertEqual(top["gaps"], 2)
        self.assertEqual(asked["ask"], True)
        self.assertNotIn("ask", plain)
        self.assertNotIn("gaps", asked)

    def test_acc_stays_until_accepted_even_when_done(self):
        feats = [feat("F1", acc="ship it"), feat("F2", acc="ship it", accepted="2026-10-14")]
        tasks = [task("A.1", "done", feats=["F1"]), task("A.2", "done", feats=["F2"])]
        first, second = features.snapshot_rows(features.derive(feats, tasks, [])["rows"])
        self.assertEqual(first["acc"], "ship it")
        self.assertNotIn("acc", second)

    def test_bad_input_gives_no_rows(self):
        self.assertEqual(features.snapshot_rows(None), [])


if __name__ == "__main__":
    unittest.main()
