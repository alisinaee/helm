"""Gap tests for the plan text format (R74): F and L lines, the f: token, format round trips, and the feature
service rules that the plan import relies on (apply_records, link, unlink, status_line). Each test asserts a
concrete result; a case the code gets wrong is marked expectedFailure and listed in the report.
"""

import os
import unittest

from roadmap.core import planfmt
from roadmap.errors import RoadmapError
from roadmap.services import features, tasks
from tests.unit.test_store_support import HomeCase

PROJECT_ID = "demo"
BASE = """P M1 todo | Foundations
T M1.1 todo 5 haiku/low | Scaffold
T M1.2 todo 8 sonnet/medium | Data model
"""


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class FormatFeatureTests(unittest.TestCase):
    def test_minimal_feature_formats_and_round_trips(self):
        feature = {"id": "F1", "title": "Title", "prio": 2, "phase": None, "parent": None, "hold": False, "acc": ""}
        line = planfmt.format_feature(feature)
        self.assertEqual(line, "F F1 - 2 - - | Title")
        records, errors = planfmt.parse_plan(line + "\n")
        self.assertEqual(errors, [])
        rec = records[0]
        self.assertEqual((rec["id"], rec["title"], rec["prio"], rec["phase"], rec["parent"], rec["hold"], rec["acc"]),
                         ("F1", "Title", 2, None, None, False, ""))

    def test_hold_status_token_round_trips(self):
        line = planfmt.format_feature({"id": "F1", "title": "Held", "prio": 2, "hold": True})
        self.assertEqual(line, "F F1 hold 2 - - | Held")
        records, errors = planfmt.parse_plan(line + "\n")
        self.assertEqual(errors, [])
        self.assertIs(records[0]["hold"], True)

    def test_full_feature_keeps_prio_phase_parent_and_acceptance(self):
        feature = {"id": "F3", "title": "Sync", "prio": 1, "phase": "M1", "parent": "F2", "hold": False,
                   "acc": "Works offline"}
        line = planfmt.format_feature(feature)
        self.assertEqual(line, "F F3 - 1 M1 F2 | Sync # Works offline")
        records, errors = planfmt.parse_plan("F F2 - 2 - - | Parent\n" + line + "\n")
        self.assertEqual(errors, [])
        rec = records[1]
        self.assertEqual((rec["prio"], rec["phase"], rec["parent"], rec["acc"]), (1, "M1", "F2", "Works offline"))

    def test_out_of_range_prio_formats_as_default(self):
        for prio in (0, 4):
            line = planfmt.format_feature({"id": "F1", "title": "T", "prio": prio})
            self.assertEqual(line, "F F1 - 2 - - | T")

    def test_blank_acceptance_adds_no_hash(self):
        for acc in ("", "   "):
            line = planfmt.format_feature({"id": "F1", "title": "T", "acc": acc})
            self.assertNotIn("#", line)


class ParseFeatureErrorTests(unittest.TestCase):
    def assert_error(self, line, fragment):
        records, errors = planfmt.parse_plan(line + "\n")
        self.assertEqual(records, [])
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(fragment, errors[0])
        self.assertTrue(errors[0].startswith("line 1: "))

    def test_too_few_tokens_names_the_shape(self):
        self.assert_error("F F1 - 2 | Title", "feature line needs an id, status, prio, phase, parent")

    def test_bad_feature_id(self):
        self.assert_error("F F0 - 2 - - | Title", "feature id 'F0' must look like F3 (allowed: F1 to F99)")
        self.assert_error("F F100 - 2 - - | Title", "feature id 'F100' must look like F3")

    def test_bad_status(self):
        self.assert_error("F F1 done 2 - - | Title", "status 'done' is not valid (allowed: -|hold)")

    def test_bad_prio(self):
        self.assert_error("F F1 - 4 - - | Title", "prio '4' is not valid (allowed: 1|2|3)")

    def test_phase_with_a_dot(self):
        self.assert_error("F F1 - 2 M.1 - | Title", "phase 'M.1' has a dot or a symbol (allowed: phase id or -)")

    def test_bad_parent_id(self):
        self.assert_error("F F1 - 2 - F0 | Title", "parent 'F0' must look like F3 (allowed: feature id or -)")

    def test_feature_cannot_be_its_own_parent(self):
        self.assert_error("F F2 - 2 - F2 | Title", "F2 cannot be its own parent")

    def test_empty_title(self):
        self.assert_error("F F1 - 2 - - |   ", "feature title is empty (allowed: text after the '|')")

    def test_title_over_eighty_characters(self):
        self.assert_error("F F1 - 2 - - | " + "t" * 81, "feature title is 81 characters (allowed: up to 80)")

    def test_title_of_eighty_characters_is_accepted(self):
        records, errors = planfmt.parse_plan("F F1 - 2 - - | " + "t" * 80 + "\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(records[0]["title"]), 80)

    def test_empty_acceptance_after_hash(self):
        self.assert_error("F F1 - 2 - - | Title #", "acceptance is empty (allowed: '# ' followed by text, or no '#')")

    def test_acceptance_over_160_characters(self):
        self.assert_error("F F1 - 2 - - | Title # " + "a" * 161, "acceptance is 161 characters (allowed: up to 160)")

    def test_duplicate_feature_id_in_one_input(self):
        records, errors = planfmt.parse_plan("F F1 - 2 - - | One\nF F1 - 2 - - | Again\n")
        self.assertEqual(len(records), 1)
        self.assertEqual(errors, ["line 2: duplicate feature id F1 (first on line 1) (allowed: each id once per "
                                  "input)"])


class ParseLinkTests(unittest.TestCase):
    def test_link_with_too_few_tokens(self):
        _, errors = planfmt.parse_plan("L F1\n")
        self.assertEqual(errors, ["line 1: link line needs a feature id and at least one task id (allowed: "
                                  "L <featureId> <taskId> [<taskId>...])"])

    def test_link_with_bad_feature_id(self):
        _, errors = planfmt.parse_plan("L F0 M1.1\n")
        self.assertEqual(errors, ["line 1: feature id 'F0' must look like F3 (allowed: F1 to F99)"])

    def test_link_with_bad_task_id(self):
        _, errors = planfmt.parse_plan("L F1 M1\n")
        self.assertEqual(errors, ["line 1: task id 'M1' must look like P1.2 (allowed: <phase>.<number>)"])

    def test_link_with_several_task_ids(self):
        records, errors = planfmt.parse_plan("L F1 M1.1 M1.2\n")
        self.assertEqual(errors, [])
        self.assertEqual(records, [{"kind": "link", "line": 1, "feature": "F1", "tasks": ["M1.1", "M1.2"]}])

    def test_repeated_link_lines_for_one_feature_are_not_duplicates(self):
        records, errors = planfmt.parse_plan("L F1 M1.1\nL F1 M1.2\n")
        self.assertEqual(errors, [])
        self.assertEqual([r["tasks"] for r in records], [["M1.1"], ["M1.2"]])


class TaskFeatsTests(unittest.TestCase):
    def test_format_task_writes_f_token(self):
        line = planfmt.format_task({"id": "M1.1", "title": "x", "feats": ["F1", "F2"]})
        self.assertIn(" f:F1,F2 ", line)

    def test_empty_or_missing_feats_are_omitted(self):
        self.assertNotIn("f:", planfmt.format_task({"id": "M1.1", "title": "x", "feats": []}))
        self.assertNotIn("f:", planfmt.format_task({"id": "M1.1", "title": "x", "feats": None}))

    def test_feats_round_trip_through_parse_plan(self):
        task = {"id": "M1.1", "title": "x", "status": "todo", "tokensK": 3, "model": "haiku", "thinking": "low",
                "feats": ["F1", "F2"]}
        records, errors = planfmt.parse_plan("P M1 todo | m\n" + planfmt.format_task(task) + "\n")
        self.assertEqual(errors, [])
        self.assertEqual(records[1]["feats"], ["F1", "F2"])

    def test_after_then_feats_order_round_trips(self):
        task = {"id": "M1.2", "title": "x", "after": ["M1.1"], "feats": ["F1"]}
        line = planfmt.format_task(task)
        self.assertEqual(line, "T M1.2 - - -/- a:M1.1 f:F1 | x")
        records, errors = planfmt.parse_plan("P M1 todo | m\n" + line + "\n")
        self.assertEqual(errors, [])
        self.assertEqual((records[1]["after"], records[1]["feats"]), (["M1.1"], ["F1"]))

    def test_f_dash_gives_none(self):
        records, errors = planfmt.parse_plan("P M1 todo | m\nT M1.1 todo 5 haiku/low f:- | x\n")
        self.assertEqual(errors, [])
        self.assertIsNone(records[1]["feats"])

    def test_f_with_bad_feature_id(self):
        _, errors = planfmt.parse_plan("P M1 todo | m\nT M1.1 todo 5 haiku/low f:F0 | x\n")
        self.assertEqual(errors, ["line 2: feature id 'F0' must look like F3 (allowed: F1 to F99, comma separated)"])

    def test_f_with_more_than_three_ids(self):
        _, errors = planfmt.parse_plan("P M1 todo | m\nT M1.1 todo 5 haiku/low f:F1,F2,F3,F4 | x\n")
        self.assertEqual(errors, ["line 2: f: has 4 features (allowed: up to 3 per task)"])


class ApplyRecordsTests(HomeCase):
    def setUp(self):
        super().setUp()
        folder = self.make_project(PROJECT_ID)
        self.docs = folder + "/docs"
        os.makedirs(self.docs)
        records, errors = planfmt.parse_plan(BASE)
        self.assertEqual(errors, [])
        tasks.apply(self.docs, records, project_id=PROJECT_ID)

    def feature_file(self):
        return os.path.join(self.docs, features.FILE)

    def test_non_feature_records_are_skipped(self):
        recs = [{"kind": "task", "id": "M1.1"}, {"kind": "link", "feature": "F9", "tasks": ["M1.1"]},
                features.record_of("F1", "One")]
        result = features.apply_records(self.docs, recs)
        self.assertEqual(result["added"], ["F1"])
        self.assertTrue(result["wrote"])

    def test_dry_run_writes_nothing(self):
        result = features.apply_records(self.docs, [features.record_of("F1", "One")], dry_run=True)
        self.assertEqual((result["added"], result["wrote"]), (["F1"], False))
        self.assertFalse(os.path.exists(self.feature_file()))

    def test_validation_failure_raises_usage_and_leaves_file_unchanged(self):
        features.apply_records(self.docs, [features.record_of("F1", "One")])
        before = read_text(self.feature_file())
        bad = features.record_of("F2", "Two", parent="F9")
        with self.assertRaises(RoadmapError) as ctx:
            features.apply_records(self.docs, [bad])
        self.assertEqual(ctx.exception.code, "usage")
        self.assertEqual(read_text(self.feature_file()), before)


class LinkUnlinkTests(HomeCase):
    def setUp(self):
        super().setUp()
        folder = self.make_project(PROJECT_ID)
        self.docs = folder + "/docs"
        os.makedirs(self.docs)
        records, _ = planfmt.parse_plan(BASE + "F F1 - 2 M1 - | One\nF F2 - 2 M1 - | Two\nF F3 - 2 M1 - | Three\n"
                                        "F F4 - 2 M1 - | Four\n")
        tasks.apply(self.docs, records, project_id=PROJECT_ID)

    def feats_of(self, tid):
        return tasks.get(self.docs, tid).get("feats")

    def test_link_clears_orphan_status(self):
        self.assertIn("M1.1", features.derived(self.docs)["orphans"])
        result = features.link(self.docs, "M1.1", ["F1"])
        self.assertEqual(result["added"], ["F1"])
        self.assertNotIn("M1.1", features.derived(self.docs)["orphans"])

    def test_link_of_an_already_linked_feature_is_idempotent(self):
        features.link(self.docs, "M1.1", ["F1"])
        result = features.link(self.docs, "M1.1", ["F1"])
        self.assertEqual(result["added"], [])
        self.assertEqual(self.feats_of("M1.1"), ["F1"])

    def test_link_up_to_the_cap_of_three(self):
        result = features.link(self.docs, "M1.1", ["F1", "F2", "F3"])
        self.assertEqual(result["added"], ["F1", "F2", "F3"])
        self.assertEqual(self.feats_of("M1.1"), ["F1", "F2", "F3"])

    def test_unlink_of_a_missing_task_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            features.unlink(self.docs, "M9.9", ["F1"])
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertIn("no task M9.9", str(ctx.exception))

    def test_unlink_of_a_feature_not_on_the_task_changes_nothing(self):
        features.link(self.docs, "M1.1", ["F1"])
        result = features.unlink(self.docs, "M1.1", ["F2"])
        self.assertEqual(result["removed"], [])
        self.assertEqual(self.feats_of("M1.1"), ["F1"])

    def test_unlinking_the_last_feature_drops_feats_and_restores_orphan(self):
        features.link(self.docs, "M1.1", ["F1"])
        features.unlink(self.docs, "M1.1", ["F1"])
        self.assertNotIn("feats", tasks.get(self.docs, "M1.1"))
        self.assertIn("M1.1", features.derived(self.docs)["orphans"])


class StatusLineOrphanTests(HomeCase):
    def setUp(self):
        super().setUp()
        folder = self.make_project(PROJECT_ID)
        self.docs = folder + "/docs"
        os.makedirs(self.docs)
        records, _ = planfmt.parse_plan(BASE + "F F1 - 2 M1 - | One\n")
        tasks.apply(self.docs, records, project_id=PROJECT_ID)

    def test_zero_orphans_omits_the_orphan_clause(self):
        features.link(self.docs, "M1.1", ["F1"])
        features.link(self.docs, "M1.2", ["F1"])
        self.assertNotIn("orphan", features.status_line(self.docs))

    def test_one_orphan_is_singular(self):
        features.link(self.docs, "M1.1", ["F1"])
        self.assertIn("; 1 orphan task)", features.status_line(self.docs))

    def test_many_orphans_are_plural(self):
        self.assertIn("; 2 orphan tasks)", features.status_line(self.docs))


if __name__ == "__main__":
    unittest.main()
