"""WP50 planner core: feature states, rollups, coverage and orphans, shared tasks, caps and errors, never-raise on
corrupt input, the features.json kind, and tasks.json without feats unchanged. Pure functions and temp folders only."""

import json
import os
import tempfile
import unittest

from roadmap.core import features
from roadmap.core.parsers import parse_feats, parse_tasks
from roadmap.services import features as feature_service


def task(tid, state="todo", tokens=10, feats=None):
    t = {"id": tid, "phase": tid.split(".")[0], "title": "T " + tid, "state": state, "tokensK": float(tokens),
         "thinking": "low", "model": "haiku", "needsUser": False, "check": "none", "checkK": 0.0, "note": None}
    if feats is not None:
        t["feats"] = feats
    return t


def job(tid, status="done", tokens=5):
    return {"id": "J-" + tid, "task": tid, "status": status, "tokensK": tokens}


def feat(fid, **extra):
    base = {"id": fid, "title": "Feature " + str(fid), "acc": "works", "prio": 2, "parent": None, "phase": None,
            "hold": False, "accepted": None}
    base.update(extra)
    return base


def row(result, fid):
    return next(r for r in result["rows"] if r["id"] == fid)


class StateMatrixTests(unittest.TestCase):
    def test_each_state_in_order(self):
        feats = [feat("F1", hold=True), feat("F2"), feat("F3"), feat("F4"), feat("F5")]
        tasks = [
            task("A.1", "todo", feats=["F1"]),          # F1 hold wins even with todo tasks
            task("B.1", "done", feats=["F3"]),          # F3 all done
            task("C.1", "done", feats=["F4"]),          # F4 doing: one done, one todo
            task("C.2", "todo", feats=["F4"]),
            task("D.1", "todo", feats=["F5"]),         # F5 todo (no running job)
            task("E.1", "todo", feats=["F5"]),
        ]
        result = features.derive(feats, tasks, [])
        self.assertEqual(row(result, "F1")["state"], "hold")
        self.assertEqual(row(result, "F2")["state"], "uncovered")
        self.assertEqual(row(result, "F3")["state"], "done")
        self.assertEqual(row(result, "F4")["state"], "doing")
        self.assertEqual(row(result, "F5")["state"], "todo")
        self.assertEqual(result["uncovered"], ["F2"])
        # hold is its own count and not part of total, so the four states add up to total
        self.assertEqual(result["counts"], {"total": 4, "done": 1, "doing": 1, "todo": 1, "uncovered": 1, "hold": 1})

    def test_hold_with_no_tasks_is_not_uncovered(self):
        result = features.derive([feat("F1", hold=True)], [], [])
        self.assertEqual(row(result, "F1")["state"], "hold")
        self.assertEqual(result["uncovered"], [])

    def test_a_running_job_makes_a_todo_feature_doing(self):
        result = features.derive([feat("F1")], [task("A.1", "todo", feats=["F1"])], [job("A.1", "running")])
        self.assertEqual(row(result, "F1")["state"], "doing")
        self.assertEqual(row(result, "F1")["running"], 1)

    def test_partial_task_makes_a_feature_doing(self):
        result = features.derive([feat("F1")], [task("A.1", "partial", feats=["F1"])], [])
        self.assertEqual(row(result, "F1")["state"], "doing")

    def test_hold_task_blocks_done(self):
        # one done task and one hold task: not all done, so the feature is doing
        feats = [feat("F1")]
        tasks = [task("A.1", "done", feats=["F1"]), task("A.2", "hold", feats=["F1"])]
        self.assertEqual(row(features.derive(feats, tasks, []), "F1")["state"], "doing")


class FiguresTests(unittest.TestCase):
    def test_figures_and_blocked_and_spent(self):
        feats = [feat("F1")]
        tasks = [task("A.1", "done", tokens=20, feats=["F1"]), task("A.2", "todo", tokens=30.5, feats=["F1"])]
        issues = [{"id": "I1", "kind": "blocker", "status": "open", "tasks": ["A.2"]},
                  {"id": "I2", "kind": "blocker", "status": "closed", "tasks": ["A.1"]}]
        result = features.derive(feats, tasks, [job("A.1", "done", 7), job("A.2", "running", 3)], issues)
        r = row(result, "F1")
        self.assertEqual((r["done"], r["total"]), (1, 2))
        self.assertEqual(r["estK"], 50.5)
        self.assertEqual(r["spentK"], 10.0)
        self.assertEqual(r["blocked"], 1)
        self.assertEqual(r["running"], 1)
        self.assertEqual(r["tasks"], ["A.1", "A.2"])

    def test_figures_follow_the_feature_not_the_phase(self):
        result = features.derive([feat("F1", phase="R6")], [task("A.1", feats=["F1"])], [])
        self.assertEqual(row(result, "F1")["phase"], "R6")


class RollupTests(unittest.TestCase):
    def test_parent_rolls_up_children_once(self):
        feats = [feat("F1"), feat("F2", parent="F1"), feat("F3", parent="F1")]
        tasks = [task("A.1", "done", feats=["F2"]), task("A.2", "done", feats=["F2", "F3"]),
                 task("A.3", "todo", feats=["F3"])]
        result = features.derive(feats, tasks, [])
        parent = row(result, "F1")
        self.assertEqual(parent["tasks"], ["A.1", "A.2", "A.3"])
        self.assertEqual((parent["done"], parent["total"]), (2, 3))
        self.assertEqual(parent["state"], "doing")
        self.assertEqual(row(result, "F2")["state"], "done")
        self.assertEqual(row(result, "F3")["state"], "doing")
        self.assertEqual(parent["parent"], None)
        self.assertEqual(row(result, "F2")["parent"], "F1")

    def test_parent_with_no_tasks_of_its_own_is_covered_by_children(self):
        feats = [feat("F1"), feat("F2", parent="F1")]
        result = features.derive(feats, [task("A.1", "todo", feats=["F2"])], [])
        self.assertEqual(row(result, "F1")["state"], "todo")
        self.assertEqual(result["uncovered"], [])

    def test_parent_with_no_tasks_anywhere_is_uncovered(self):
        result = features.derive([feat("F1"), feat("F2", parent="F1")], [], [])
        self.assertEqual(result["uncovered"], ["F1", "F2"])


class CoverageTests(unittest.TestCase):
    def test_orphans_are_tasks_without_a_valid_feature(self):
        feats = [feat("F1")]
        tasks = [task("A.1", feats=["F1"]), task("A.2"), task("A.3", feats=["F9"]), task("A.4", feats=[])]
        result = features.derive(feats, tasks, [])
        self.assertEqual(result["orphans"], ["A.2", "A.3", "A.4"])

    def test_old_tasks_without_feats_are_all_orphans(self):
        tasks = [task("A.1"), task("A.2", "done")]
        result = features.derive([feat("F1")], tasks, [])
        self.assertEqual(result["orphans"], ["A.1", "A.2"])
        self.assertEqual(row(result, "F1")["state"], "uncovered")

    def test_shared_task_counts_per_feature_and_once_globally(self):
        feats = [feat("F1"), feat("F2")]
        tasks = [task("A.1", "done", tokens=10, feats=["F1", "F2"]), task("A.2", "todo", tokens=5, feats=["F2"])]
        result = features.derive(feats, tasks, [job("A.1", "done", 4)])
        self.assertEqual(row(result, "F1")["total"], 1)
        self.assertEqual(row(result, "F2")["total"], 2)
        self.assertEqual(row(result, "F1")["spentK"], 4.0)
        self.assertEqual(row(result, "F2")["spentK"], 4.0)
        self.assertEqual(result["taskTotals"], {"total": 2, "done": 1, "estK": 15.0, "spentK": 4.0})
        self.assertEqual(result["orphans"], [])

    def test_accepted_is_data_only(self):
        result = features.derive([feat("F1", accepted="2026-10-14")], [], [])
        r = row(result, "F1")
        self.assertEqual(r["accepted"], "2026-10-14")
        self.assertEqual(r["state"], "uncovered")


class CapsAndErrorsTests(unittest.TestCase):
    def assertInvalid(self, entry, fragment):
        errors = features.validate([entry])
        self.assertTrue(any(fragment in e for e in errors), errors)
        self.assertEqual(features.derive([entry], [], [])["rows"], [])

    def test_bad_ids(self):
        for bad in ("F0", "F100", "F01", "X1", "f1", "", None, 7):
            self.assertInvalid(feat(bad), "id must be F1 to F99")

    def test_title_and_acc_caps(self):
        self.assertInvalid(feat("F1", title="x" * 81), "title is longer than 80")
        self.assertInvalid(feat("F1", title="   "), "title is required")
        self.assertInvalid(feat("F1", acc="y" * 161), "acc is longer than 160")
        self.assertEqual(features.validate([feat("F1", title="x" * 80, acc="y" * 160)]), [])

    def test_prio_range(self):
        for bad in (0, 4, True, "2", None):
            self.assertInvalid(feat("F1", prio=bad), "prio must be 1, 2 or 3")
        self.assertEqual(features.derive([feat("F1", prio=3)], [], [])["rows"][0]["prio"], 3)

    def test_missing_prio_defaults_to_two(self):
        raw = feat("F1")
        del raw["prio"]
        self.assertEqual(features.derive([raw], [], [])["rows"][0]["prio"], 2)

    def test_parent_rules(self):
        errs = features.validate([feat("F1", parent="F9")])
        self.assertTrue(any("parent F9 is not a valid feature" in e for e in errs))
        self.assertTrue(any("cannot be its own parent" in e for e in features.validate([feat("F1", parent="F1")])))
        chain = [feat("F1"), feat("F2", parent="F1"), feat("F3", parent="F2")]
        result = features.derive(chain, [], [])
        self.assertEqual([r["id"] for r in result["rows"]], ["F1", "F2"])
        self.assertTrue(any("F3" in e and "one level only" in e for e in result["errors"]))

    def test_duplicate_id_keeps_the_first(self):
        result = features.derive([feat("F1", title="first"), feat("F1", title="second")], [], [])
        self.assertEqual([r["title"] for r in result["rows"]], ["first"])
        self.assertTrue(any("more than once" in e for e in result["errors"]))

    def test_phase_must_be_a_phase_id(self):
        self.assertInvalid(feat("F1", phase="P1-x"), "phase must be a phase id")
        self.assertInvalid(feat("F1", phase=7), "phase must be a phase id")
        self.assertEqual(features.derive([feat("F1", phase="P1")], [], [])["rows"][0]["phase"], "P1")
        self.assertIsNone(features.derive([feat("F1", phase="")], [], [])["rows"][0]["phase"])

    def test_accepted_must_be_a_real_date(self):
        for bad in ("yes", "2026-13-01", "2026-02-30", "2026-10-1", 20261014, True):
            self.assertInvalid(feat("F1", accepted=bad), "accepted must look like 2026-10-14")
        self.assertEqual(features.derive([feat("F1", accepted="2026-10-14")], [], [])["rows"][0]["accepted"],
                         "2026-10-14")
        self.assertIsNone(features.derive([feat("F1", accepted="")], [], [])["rows"][0]["accepted"])

    def test_cap_of_sixty_features(self):
        raw = [feat("F" + str(n)) for n in range(1, 62)]
        result = features.derive(raw, [], [])
        self.assertEqual(len(result["rows"]), 60)
        self.assertEqual(result["counts"]["total"], 60)
        self.assertTrue(any("beyond the first 60" in e for e in result["errors"]))

    def test_valid_features_have_no_errors(self):
        self.assertEqual(features.validate([feat("F1"), feat("F2", parent="F1")]), [])


class NeverRaiseTests(unittest.TestCase):
    CORRUPT_FEATURES = [None, 42, "x", {}, {"features": []}, [None], [1, "x", []], [{"id": ["F1"]}], [{"id": "F1",
                        "title": {}}], [feat("F1", parent=["F2"])], [feat("F1", acc=5)], [feat("F1", hold="yes")]]
    CORRUPT_TASKS = [None, 1, "t", [None], [{"id": 3}], [{"id": "A.1", "feats": "F1"}],
                     [{"id": "A.1", "feats": [None, {}, ["F1"]], "state": None, "tokensK": "x"}]]
    CORRUPT_JOBS = [None, "j", [None], [{"task": ["A.1"], "status": "running"}], [{"task": "A.1", "tokensK": {}}]]
    CORRUPT_ISSUES = [None, "i", [None], [{"kind": "blocker", "status": "open", "tasks": "A.1"}],
                      [{"kind": "blocker", "status": "open", "tasks": [None, ["A.1"]]}]]

    def test_derive_never_raises(self):
        for raw in self.CORRUPT_FEATURES:
            for tasks in self.CORRUPT_TASKS + [None]:
                for jobs in self.CORRUPT_JOBS + [None]:
                    for issues in self.CORRUPT_ISSUES + [None]:
                        result = features.derive(raw, tasks, jobs, issues)
                        self.assertEqual(set(result),
                                         {"rows", "uncovered", "orphans", "counts", "taskTotals", "errors"})

    def test_validate_never_raises(self):
        for raw in self.CORRUPT_FEATURES:
            self.assertIsInstance(features.validate(raw), list)

    def test_load_corrupt_files_give_errors(self):
        cases = {"{": "Expecting", "[]": "expected a JSON object", '{"features": 7}': "features array",
                 '{"schemaVersion": 9, "features": []}': "newer", '{"schemaVersion": 0}': "schemaVersion"}
        for text, fragment in cases.items():
            with tempfile.TemporaryDirectory() as folder:
                with open(os.path.join(folder, "features.json"), "w", encoding="utf-8") as fh:
                    fh.write(text)
                items, errors = feature_service.load(folder)
                self.assertEqual(items, [], text)
                self.assertTrue(errors, text)
                self.assertIn(fragment, errors[0]["error"], text)

    def test_load_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(feature_service.load(folder), ([], []))

    def test_load_reads_schema_one_features(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = {"schemaVersion": 1, "features": [feat("F1"), feat("F2", parent="F1")]}
            with open(os.path.join(folder, "features.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            items, errors = feature_service.load(folder)
            self.assertEqual(errors, [])
            self.assertEqual([f["id"] for f in items], ["F1", "F2"])
            self.assertEqual(features.derive(items, [], [])["counts"]["total"], 2)


class SnapshotRowsTests(unittest.TestCase):
    def test_rows_drop_the_task_list_and_keep_acc_only_while_not_done(self):
        feats = [feat("F1", acc="shipped"), feat("F2", acc="still open")]
        tasks = [task("A.1", "done", feats=["F1"]), task("A.2", "todo", feats=["F2"])]
        first, second = features.snapshot_rows(features.derive(feats, tasks, [])["rows"])
        self.assertNotIn("tasks", first)
        self.assertNotIn("acc", first)
        self.assertEqual(second["acc"], "still open")
        self.assertEqual(set(first), set(features.SNAPSHOT_ROW_KEYS))
        self.assertEqual((first["done"], first["total"], first["state"]), (1, 1, "done"))

    def test_bad_input_gives_no_rows(self):
        self.assertEqual(features.snapshot_rows(None), [])
        self.assertEqual(features.snapshot_rows([{"id": "F1"}]), [{"id": "F1"}])


class TaskFeatsTests(unittest.TestCase):
    def tasks_text(self, extra):
        base = {"id": "A.1", "phase": "A", "title": "x", "status": "todo", "tokensK": 1, "thinking": "low",
                "model": "haiku", "needsUser": False, "check": "none", "checkK": 0}
        base.update(extra)
        return json.dumps({"schemaVersion": 1, "updated": "", "phases": [], "tasks": [base]})

    def test_old_tasks_without_feats_are_unchanged(self):
        data, errors = parse_tasks(self.tasks_text({}))
        self.assertEqual(errors, [])
        self.assertNotIn("feats", data["tasks"][0])

    def test_feats_are_kept_in_order_with_the_first_primary(self):
        data, errors = parse_tasks(self.tasks_text({"feats": ["F3", "F7"]}))
        self.assertEqual(data["tasks"][0]["feats"], ["F3", "F7"])
        self.assertEqual(errors, [])

    def test_feats_cap_bad_ids_and_duplicates(self):
        feats, errors = parse_feats(["F1", "F2", "F3", "F4"], "tasks.json", "A.1")
        self.assertEqual(feats, ["F1", "F2", "F3"])
        self.assertEqual(len(errors), 1)
        feats, errors = parse_feats(["F1", "F1", "F0", 7, None, "F12"], "tasks.json", "A.1")
        self.assertEqual(feats, ["F1", "F12"])
        self.assertEqual(len(errors), 3)

    def test_feats_not_a_list_never_raises(self):
        for value in ("F1", 3, None, {"a": 1}):
            feats, errors = parse_feats(value, "tasks.json", "A.1")
            self.assertEqual(feats, [])
            self.assertEqual(len(errors), 1)
        data, errors = parse_tasks(self.tasks_text({"feats": "F1"}))
        self.assertEqual(data["tasks"][0]["feats"], [])
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
