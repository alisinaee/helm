"""Tests for plan import ordering and caps (R3.3b): features are checked before any write and rolled back when
the features write fails, the feature cap holds on updates, a T-line f: merges like an L line, and f: rejects
duplicate ids.
"""

import os
import unittest
from unittest import mock

from roadmap.core import planfmt
from roadmap.errors import RoadmapError
from roadmap.services import tasks
from tests.unit.test_store_support import HomeCase

PROJECT_ID = "demo"
BASE = """P M1 todo | Foundations
T M1.1 todo 5 haiku/low | Scaffold
T M1.2 todo 8 sonnet/medium | Data model
"""


class ImportFixCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.folder = self.make_project(PROJECT_ID)
        self.docs = self.folder + "/docs"
        os.makedirs(self.docs)
        self.run_plan(BASE)

    def run_plan(self, text):
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        return tasks.apply(self.docs, records, project_id=PROJECT_ID)

    def task_lines(self):
        return [planfmt.format_task(t) for t in tasks.load(self.docs)["tasks"]]


class ParseDuplicateFeatsTests(unittest.TestCase):
    def test_duplicate_feature_id_in_f_is_rejected(self):
        _, errors = planfmt.parse_plan("P M1 todo | A\nT M1.1 todo 5 haiku/low f:F1,F2,F1 | x\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("twice", errors[0])

    def test_distinct_feature_ids_parse(self):
        records, errors = planfmt.parse_plan("P M1 todo | A\nT M1.1 todo 5 haiku/low f:F1,F2 | x\n")
        self.assertEqual(errors, [])
        self.assertEqual(records[1]["feats"], ["F1", "F2"])


class FeatsMergeTests(ImportFixCase):
    def setUp(self):
        super().setUp()
        self.run_plan("F F1 - 2 M1 - | One\nF F2 - 2 M1 - | Two\nF F3 - 2 M1 - | Three\nF F4 - 2 M1 - | Four\n")

    def test_t_line_f_adds_to_existing_links(self):
        self.run_plan("T M1.1 todo 5 haiku/low f:F1 | Scaffold\n")
        self.run_plan("T M1.1 todo 5 haiku/low f:F2 | Scaffold\n")
        self.assertEqual(tasks.load(self.docs)["tasks"][0]["feats"], ["F1", "F2"])

    def test_t_line_f_dash_keeps_links(self):
        self.run_plan("T M1.1 todo 5 haiku/low f:F1 | Scaffold\n")
        self.run_plan("T M1.1 todo 5 haiku/low f:- | Scaffold\n")
        self.assertEqual(tasks.load(self.docs)["tasks"][0]["feats"], ["F1"])

    def test_t_line_f_merge_over_three_is_refused(self):
        self.run_plan("T M1.1 todo 5 haiku/low f:F1,F2,F3 | Scaffold\n")
        records, _ = planfmt.parse_plan("T M1.1 todo 5 haiku/low f:F4 | Scaffold\n")
        self.run_plan_expect_usage(records)

    def run_plan_expect_usage(self, records):
        before = self.task_lines()
        with self.assertRaises(RoadmapError) as ctx:
            tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertIn("per task", str(ctx.exception))
        self.assertEqual(self.task_lines(), before)


class FeatureCapTests(ImportFixCase):
    def test_update_over_cap_is_refused_and_writes_nothing(self):
        self.run_plan("F F1 - 2 M1 - | One\n")
        before = self.task_lines()
        records, _ = planfmt.parse_plan("F F1 - 3 M1 - | One renamed\nT M1.1 todo 9 haiku/low | Scaffold\n")
        with mock.patch.object(planfmt, "FEATURES_MAX", 0):
            with self.assertRaises(RoadmapError) as ctx:
                tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertIn("allowed: up to 0", str(ctx.exception))
        self.assertEqual(self.task_lines(), before)


class FeaturesWriteOrderTests(ImportFixCase):
    def test_features_failure_rolls_back_tasks(self):
        from roadmap.services import features as feature_store
        before = self.task_lines()
        records, _ = planfmt.parse_plan("F F1 - 2 M1 - | One\nT M1.3 todo 2 haiku/low f:F1 | New\n")
        with mock.patch.object(feature_store, "apply_records", side_effect=RoadmapError("usage", "boom", 2)):
            with self.assertRaises(RoadmapError):
                tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertEqual(self.task_lines(), before)

    def test_features_and_tasks_import_together(self):
        records, _ = planfmt.parse_plan("F F1 - 2 M1 - | One\nT M1.3 todo 2 haiku/low f:F1 | New\n")
        diff = tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertTrue(diff["wrote"])
        self.assertEqual(tasks.load(self.docs)["tasks"][-1]["feats"], ["F1"])


if __name__ == "__main__":
    unittest.main()
