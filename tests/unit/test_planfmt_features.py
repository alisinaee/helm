"""Tests for the plan record types F (feature) and L (link), the f: token on T lines, and their apply rules.

Covers parse and format round trips, caps (3 feats per task, 60 features), validation messages with 'line N:',
idempotent re-import, the export then import round trip, and that plans without the new records behave as before.
"""

import json
import os
import unittest

from roadmap.core import planfmt
from roadmap.services import tasks
from tests.unit.test_store_support import HomeCase

PROJECT_ID = "demo"
BASE = """P M1 todo | Foundations
T M1.1 todo 5 haiku/low | Scaffold
T M1.2 todo 8 sonnet/medium | Data model
T M1.3 todo 3 haiku/low | Sync
T M1.4 todo 2 haiku/low | Docs
"""


class ParseFormatTests(unittest.TestCase):
    def test_feature_line_round_trips(self):
        text = "F F3 - 2 M1 F2 | Roadmap visual # lanes, timeline; usable at 1440 and 375"
        records, errors = planfmt.parse_plan(text + "\n")
        self.assertEqual(errors, [])
        rec = records[0]
        self.assertEqual((rec["kind"], rec["id"], rec["hold"], rec["prio"]), ("feature", "F3", False, 2))
        self.assertEqual((rec["phase"], rec["parent"]), ("M1", "F2"))
        self.assertEqual(rec["title"], "Roadmap visual")
        self.assertEqual(rec["acc"], "lanes, timeline; usable at 1440 and 375")
        self.assertEqual(planfmt.format_feature(rec), text)

    def test_feature_without_acceptance_or_links_round_trips(self):
        records, errors = planfmt.parse_plan("F F4 hold 1 - - | Palette\n")
        self.assertEqual(errors, [])
        rec = records[0]
        self.assertIs(rec["hold"], True)
        self.assertIsNone(rec["phase"])
        self.assertIsNone(rec["parent"])
        self.assertEqual(rec["acc"], "")
        self.assertEqual(planfmt.format_feature(rec), "F F4 hold 1 - - | Palette")

    def test_format_feature_takes_a_stored_dict(self):
        line = planfmt.format_feature({"id": "F7", "title": "Links", "acc": "", "prio": 3, "parent": None,
                                       "phase": "R6", "hold": False, "accepted": "2026-10-14"})
        self.assertEqual(line, "F F7 - 3 R6 - | Links")

    def test_link_line_parses(self):
        records, errors = planfmt.parse_plan("L F3 R6.6 R2.1\n")
        self.assertEqual(errors, [])
        self.assertEqual(records[0], {"kind": "link", "line": 1, "feature": "F3", "tasks": ["R6.6", "R2.1"]})

    def test_feats_token_round_trips_on_a_task_line(self):
        task = {"id": "M1.1", "title": "x", "status": "todo", "tokensK": 5, "thinking": "low", "model": "haiku",
                "feats": ["F3", "F7"]}
        line = planfmt.format_task(task)
        self.assertEqual(line, "T M1.1 todo 5 haiku/low f:F3,F7 | x")
        records, errors = planfmt.parse_plan(line + "\n")
        self.assertEqual(errors, [])
        self.assertEqual(records[0]["feats"], ["F3", "F7"])

    def test_task_without_feats_parses_to_none(self):
        records, errors = planfmt.parse_plan("T M1.1 todo 5 haiku/low | x\nT M1.2 todo 5 haiku/low f:- | y\n")
        self.assertEqual(errors, [])
        self.assertIsNone(records[0]["feats"])
        self.assertIsNone(records[1]["feats"])

    def test_feats_token_after_a_and_bang_order(self):
        records, errors = planfmt.parse_plan("T M1.2 todo 5 haiku/low ! a:M1.1 f:F1 | x\n")
        self.assertEqual(errors, [])
        self.assertIs(records[0]["needsUser"], True)
        self.assertEqual(records[0]["after"], ["M1.1"])
        self.assertEqual(records[0]["feats"], ["F1"])

    def test_unknown_record_error_keeps_old_text_and_lists_new_records(self):
        records, errors = planfmt.parse_plan("X M1.1 todo\n")
        self.assertEqual(records, [])
        self.assertIn("unknown record 'X' (allowed: P, T, #, blank)", errors[0])
        self.assertIn("F, L", errors[0])

    def test_feature_errors_name_the_line_and_allowed_values(self):
        cases = {
            "F F100 - 2 - - | x": "feature id 'F100' must look like F3",
            "F F0 - 2 - - | x": "feature id 'F0' must look like F3",
            "F F3 doing 2 - - | x": "status 'doing' is not valid (allowed: -|hold)",
            "F F3 - 4 - - | x": "prio '4' is not valid (allowed: 1|2|3)",
            "F F3 - - - - | x": "prio '-' is not valid (allowed: 1|2|3)",
            "F F3 - 2 M.1 - | x": "phase 'M.1' has a dot or a symbol",
            "F F3 - 2 - F3 | x": "F3 cannot be its own parent",
            "F F3 - 2 - F2x | x": "parent 'F2x' must look like F3",
            "F F3 - 2 - - |  ": "feature title is empty",
            "F F3 - 2 - - # x": "feature line needs an id, status, prio, phase, parent",
            "F F3 - 2 - - | x #": "acceptance is empty",
            "F F3 - 2 - - | " + "t" * 81: "feature title is 81 characters (allowed: up to 80)",
            "F F3 - 2 - - | x # " + "a" * 161: "acceptance is 161 characters (allowed: up to 160)",
            "L F3": "link line needs a feature id and at least one task id",
            "L X1 M1.1": "feature id 'X1' must look like F3",
            "L F3 M1": "task id 'M1' must look like P1.2",
            "T M1.1 todo 5 haiku/low f:F1,F2,F3,F4 | x": "f: has 4 features (allowed: up to 3 per task)",
            "T M1.1 todo 5 haiku/low f:F0 | x": "feature id 'F0' must look like F3",
        }
        for text, problem in cases.items():
            with self.subTest(text=text):
                records, errors = planfmt.parse_plan(text + "\n")
                self.assertEqual(records, [])
                self.assertEqual(len(errors), 1)
                self.assertTrue(errors[0].startswith("line 1: "), errors[0])
                self.assertIn(problem, errors[0])
                self.assertIn("(allowed:", errors[0])


class ApplyCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.folder = self.make_project(PROJECT_ID)
        self.docs = os.path.join(self.folder, "docs")
        os.makedirs(self.docs)

    @property
    def features_file(self):
        return os.path.join(self.docs, "features.json")

    def run_plan(self, text, dry_run=False):
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        return tasks.apply(self.docs, records, dry_run=dry_run, project_id=PROJECT_ID)

    def feature_doc(self):
        with open(self.features_file, encoding="utf-8") as fh:
            return json.load(fh)

    def task(self, tid):
        return tasks.get(self.docs, tid)

    def seed(self):
        self.run_plan(BASE)


class ApplyTests(ApplyCase):
    def test_features_and_task_feats_are_written_and_reimport_changes_nothing(self):
        self.seed()
        plan = ("F F3 - 2 M1 - | Roadmap visual # lanes and timeline\n"
                "F F7 hold 1 - F3 | Sub feature\n"
                "T M1.1 todo 5 haiku/low f:F3,F7 | Scaffold\n")
        diff = self.run_plan(plan)
        self.assertEqual((diff["features_added"], diff["tasks_changed"]), (["F3", "F7"], ["M1.1"]))
        doc = self.feature_doc()
        self.assertEqual(doc["schemaVersion"], 1)
        self.assertEqual([f["id"] for f in doc["features"]], ["F3", "F7"])
        self.assertEqual(doc["features"][1], {"id": "F7", "title": "Sub feature", "acc": "", "prio": 1,
                                              "parent": "F3", "phase": None, "hold": True, "accepted": None})
        self.assertEqual(self.task("M1.1")["feats"], ["F3", "F7"])
        again = self.run_plan(plan)
        self.assertEqual((again["changed"], again["wrote"]), (0, False))

    def test_link_adds_feature_once_and_second_import_changes_nothing(self):
        self.seed()
        self.run_plan("F F3 - 2 M1 - | Visual\n")
        first = self.run_plan("L F3 M1.2 M1.3\n")
        self.assertEqual(first["tasks_changed"], ["M1.2", "M1.3"])
        self.assertEqual(self.task("M1.2")["feats"], ["F3"])
        second = self.run_plan("L F3 M1.2 M1.3\n")
        self.assertEqual((second["changed"], second["wrote"]), (0, False))
        self.assertEqual(self.task("M1.2")["feats"], ["F3"])

    def test_link_keeps_existing_feats_and_appends(self):
        self.seed()
        self.run_plan("F F1 - 1 - - | One\nF F2 - 1 - - | Two\nT M1.1 todo 5 haiku/low f:F1 | Scaffold\n")
        self.run_plan("L F2 M1.1\n")
        self.assertEqual(self.task("M1.1")["feats"], ["F1", "F2"])

    def test_feats_cap_is_three_per_task(self):
        self.seed()
        self.run_plan("F F1 - 1 - - | One\nF F2 - 1 - - | Two\nF F3 - 1 - - | Three\nF F4 - 1 - - | Four\n")
        self.run_plan("L F1 M1.1\nL F2 M1.1\nL F3 M1.1\n")
        records, _ = planfmt.parse_plan("L F4 M1.1\n")
        with self.assertRaises(tasks.PlanError) as ctx:
            tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertIn("line 1: M1.1 already has 3 features (allowed: up to 3 per task)", ctx.exception.errors)
        self.assertEqual(self.task("M1.1")["feats"], ["F1", "F2", "F3"])

    def test_feature_cap_is_sixty(self):
        self.seed()
        lines = "\n".join("F F" + str(i) + " - 2 - - | Feature " + str(i) for i in range(1, 62)) + "\n"
        records, errors = planfmt.parse_plan(lines)
        self.assertEqual(errors, [])
        with self.assertRaises(tasks.PlanError) as ctx:
            tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertIn("line 1: the file would have 61 features (allowed: up to 60)", ctx.exception.errors[0])
        self.assertFalse(os.path.exists(self.features_file))

    def test_sixty_features_is_allowed(self):
        self.seed()
        lines = "\n".join("F F" + str(i) + " - 2 - - | Feature " + str(i) for i in range(1, 61)) + "\n"
        self.run_plan(lines)
        self.assertEqual(len(self.feature_doc()["features"]), 60)

    def test_validation_errors_name_the_line_and_write_nothing(self):
        self.seed()
        records, _ = planfmt.parse_plan("F F1 - 1 - - | One\nF F2 - 1 - F9 | Two\nL F1 M1.9\n"
                                        "T M1.1 todo 5 haiku/low f:F5 | x\n")
        with self.assertRaises(tasks.PlanError) as ctx:
            tasks.apply(self.docs, records, project_id=PROJECT_ID)
        errors = ctx.exception.errors
        self.assertIn("line 2: parent F9 does not exist", errors[0])
        self.assertIn("line 3: no task M1.9 in tasks.json", errors[1])
        self.assertIn("line 4: feature F5 does not exist", errors[2])
        self.assertFalse(os.path.exists(self.features_file))

    def test_plan_tree_allows_three_levels_and_refuses_a_fourth(self):
        self.seed()
        self.run_plan("F F1 - 1 - - | Top\nF F2 - 1 - F1 | Child\nF F3 - 1 - F2 | Grandchild\n")
        records, _ = planfmt.parse_plan("F F4 - 1 - F3 | Great-grandchild\n")
        with self.assertRaises(tasks.PlanError) as ctx:
            tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertIn("line 1", ctx.exception.errors[0])

    def test_dry_run_summary_shows_feature_counts_and_writes_nothing(self):
        self.seed()
        diff = self.run_plan("F F3 - 2 - - | Visual\nT M1.1 todo 5 haiku/low f:F3 | Scaffold\n", dry_run=True)
        self.assertEqual(tasks.describe(diff), "would: +F1 ~T1 (no write)")
        self.assertFalse(os.path.exists(self.features_file))
        self.assertNotIn("feats", self.task("M1.1"))

    def test_feature_accepted_date_survives_reimport(self):
        self.seed()
        self.run_plan("F F3 - 2 - - | Visual\n")
        doc = self.feature_doc()
        doc["features"][0]["accepted"] = "2026-10-14"
        with open(self.features_file, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        diff = self.run_plan("F F3 - 2 - - | Visual\n")
        self.assertEqual(diff["changed"], 0)
        self.assertEqual(self.feature_doc()["features"][0]["accepted"], "2026-10-14")

    def test_export_then_import_round_trips(self):
        self.seed()
        self.run_plan("F F3 - 2 M1 - | Visual # lanes\nF F7 hold 1 - F3 | Sub\n"
                      "T M1.1 todo 5 haiku/low f:F3,F7 | Scaffold # note\nL F3 M1.2\n")
        features = tasks.load_features(self.docs)
        lines = [planfmt.format_feature(f) for f in features]
        lines.append(planfmt.format_phase(tasks.load(self.docs)["phases"][0]))
        lines += [planfmt.format_task(t) for t in tasks.load(self.docs)["tasks"]]
        text = "\n".join(lines) + "\n"
        self.assertEqual(lines[0], "F F3 - 2 M1 - | Visual # lanes")
        self.assertEqual(lines[1], "F F7 hold 1 - F3 | Sub")
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        before = self.raw_state()
        diff = tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertEqual((diff["changed"], diff["wrote"]), (0, False))
        self.assertEqual(self.raw_state(), before)

    def raw_state(self):
        with open(os.path.join(self.docs, "tasks.json"), "rb") as fh:
            tasks_raw = fh.read()
        with open(self.features_file, "rb") as fh:
            return tasks_raw, fh.read()


class OldPlanTests(ApplyCase):
    def test_plan_without_new_records_writes_no_features_file(self):
        diff = self.run_plan(BASE)
        self.assertEqual(diff["features_added"], [])
        self.assertFalse(os.path.exists(self.features_file))
        self.assertNotIn("feats", self.task("M1.1"))

    def test_old_plan_round_trip_stays_unchanged(self):
        self.run_plan(BASE)
        again = self.run_plan(BASE)
        self.assertEqual(again["changed"], 0)
        self.assertFalse(os.path.exists(self.features_file))


if __name__ == "__main__":
    unittest.main()
