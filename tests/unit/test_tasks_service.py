"""Tests for the tasks service: upsert by id, '-' semantics, idempotency, all-or-nothing validation, key order,
phase status recompute, replace_phase, backups, queries and the summary budget."""

import json
import os
import unittest

from roadmap.core import planfmt
from roadmap.errors import EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import tasks
from roadmap.store import paths
from tests.unit.test_store_support import HomeCase

PROJECT_ID = "demo"
CANON = ["id", "phase", "title", "status", "tokensK", "thinking", "model", "needsUser", "check", "checkK", "note"]


class ServiceCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.folder = self.make_project(PROJECT_ID)
        self.docs = os.path.join(self.folder, "docs")
        os.makedirs(self.docs)

    @property
    def path(self):
        return os.path.join(self.docs, "tasks.json")

    def write_tasks(self, phases=(), task_list=()):
        doc = {"schemaVersion": 1, "updated": "2026-10-01", "phases": list(phases), "tasks": list(task_list)}
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")

    def raw(self):
        if not os.path.exists(self.path):
            return None
        with open(self.path, "rb") as fh:
            return fh.read()

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def plan(self, text, **kwargs):
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        return tasks.apply(self.docs, records, project_id=PROJECT_ID, **kwargs)

    def bulk(self, text, **kwargs):
        records, errors = planfmt.parse_set_text(text)
        self.assertEqual(errors, [])
        return tasks.apply(self.docs, records, project_id=PROJECT_ID, **kwargs)


EXAMPLE = """P M1 todo | Foundations
T M1.1 todo 20 haiku/low | Scaffold repo, CI and lint
T M1.2 todo 40 sonnet/medium c:sonnet/8 | Data model and storage layer
T M1.3 todo 5 haiku/low ! | Create hosting account and API key # needs your login
T M1.4 todo 80 opus/high c:opus/15 | Sync engine design and spike
T M1.5 todo 10 haiku/low | README quick start
"""


class ApplyCreateTests(ServiceCase):
    def test_create_writes_phases_tasks_with_canonical_order_and_defaults(self):
        diff = self.plan(EXAMPLE)
        self.assertTrue(diff["wrote"])
        self.assertEqual(diff["phases_added"], ["M1"])
        self.assertEqual(len(diff["tasks_added"]), 5)
        doc = self.read()
        self.assertEqual(doc["schemaVersion"], 1)
        self.assertEqual(doc["updated"], planfmt.today())
        self.assertEqual(doc["phases"], [{"id": "M1", "name": "Foundations", "status": "todo"}])
        first, third = doc["tasks"][0], doc["tasks"][2]
        self.assertEqual(list(first), ["id", "phase", "title", "status", "tokensK", "thinking", "model",
                                       "needsUser", "check", "checkK"])
        self.assertEqual(first["check"], "none")
        self.assertEqual(first["checkK"], 0)
        self.assertIs(first["needsUser"], False)
        self.assertEqual(list(third)[:9], CANON[:9])
        self.assertEqual(third["note"], "needs your login")
        self.assertIs(doc["tasks"][2]["needsUser"], True)

    def test_dry_run_reports_would_and_writes_nothing(self):
        diff = self.plan(EXAMPLE, dry_run=True)
        self.assertFalse(diff["wrote"])
        self.assertEqual(tasks.describe(diff), "would: +P1 +T5 (no write)")
        self.assertIsNone(self.raw())

    def test_describe_lists_counts_in_order(self):
        self.plan(EXAMPLE)
        diff = self.plan("T M1.1 done 20 haiku/low | Scaffold repo, CI and lint\n"
                         "T M1.2 todo 40 sonnet/medium c:sonnet/8 | Data model and storage layer\n")
        self.assertEqual(tasks.describe(diff), "wrote: ~P1 ~T1 =T1")

    def test_unknown_phase_for_a_task_is_missing_and_writes_nothing(self):
        with self.assertRaises(tasks.PlanError) as ctx:
            self.plan("T X9.1 todo 1 haiku/low | orphan\n")
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertIn("line 1: phase X9 does not exist (allowed: a P X9 line", ctx.exception.message)
        self.assertIsNone(self.raw())

    def test_new_task_without_model_is_invalid(self):
        with self.assertRaises(tasks.PlanError) as ctx:
            self.plan("P M1 todo | m\nT M1.1 todo - -/- | x\n")
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        self.assertIn("line 2: a new task needs a model and a thinking level", ctx.exception.message)
        self.assertIsNone(self.raw())


class IdempotencyTests(ServiceCase):
    def test_second_apply_reports_zero_changed_and_does_not_write(self):
        self.plan(EXAMPLE)
        before_bytes = self.raw()
        os.utime(self.path, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        before_mtime = os.stat(self.path).st_mtime_ns
        diff = self.plan(EXAMPLE)
        self.assertEqual(diff["changed"], 0)
        self.assertEqual(tasks.describe(diff), "0 changed")
        self.assertFalse(diff["wrote"])
        self.assertEqual(self.raw(), before_bytes)
        self.assertEqual(os.stat(self.path).st_mtime_ns, before_mtime)

    def test_bulk_set_repeated_is_a_no_op(self):
        self.plan(EXAMPLE)
        self.bulk("M1.1 status=done tokensK=18\n")
        before = self.raw()
        diff = self.bulk("M1.1 status=done tokensK=18\n")
        self.assertEqual(tasks.describe(diff), "0 changed")
        self.assertEqual(self.raw(), before)


class UpdateSemanticsTests(ServiceCase):
    def setUp(self):
        super().setUp()
        self.write_tasks(
            phases=[{"id": "P1", "name": "Engine", "status": "todo"}],
            task_list=[{"id": "P1.1", "phase": "P1", "title": "First", "status": "partial", "tokensK": 30,
                        "thinking": "medium", "model": "sonnet", "needsUser": True, "check": "opus",
                        "checkK": 5, "note": "old note"}])

    def test_dash_keeps_current_values_and_absent_bang_keeps_needs_user(self):
        diff = self.plan("T P1.1 - - -/- | First renamed\n")
        task = self.read()["tasks"][0]
        self.assertEqual((task["status"], task["tokensK"], task["model"], task["thinking"]),
                         ("partial", 30, "sonnet", "medium"))
        self.assertIs(task["needsUser"], True)
        self.assertEqual((task["check"], task["checkK"], task["note"]), ("opus", 5, "old note"))
        self.assertEqual(task["title"], "First renamed")
        self.assertIn("P1.1 title First→First renamed", diff["field_diffs"])

    def test_bang_sets_needs_user_and_note_replaces(self):
        self.plan("T P1.1 partial 30 sonnet/medium ! | First # new note\n")
        task = self.read()["tasks"][0]
        self.assertIs(task["needsUser"], True)
        self.assertEqual(task["note"], "new note")

    def test_bulk_empty_note_removes_the_key_and_false_clears_needs_user(self):
        self.bulk('P1.1 note="" needsUser=false\n')
        task = self.read()["tasks"][0]
        self.assertNotIn("note", task)
        self.assertIs(task["needsUser"], False)

    def test_bulk_unknown_task_is_not_found_with_next_command(self):
        with self.assertRaises(tasks.PlanError) as ctx:
            self.bulk("P9.9 status=done\n")
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertEqual(ctx.exception.next, "roadmap task list --phase P9")
        self.assertIn("line 1: no task P9.9 in tasks.json", ctx.exception.message)

    def test_get_unknown_task_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            tasks.get(self.docs, "P9.9")
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertEqual(ctx.exception.next, "roadmap task list --phase P9")
        self.assertEqual(tasks.get(self.docs, "P1.1")["title"], "First")

    def test_duplicate_between_plan_and_bulk_lines_is_an_error(self):
        records, _ = planfmt.parse_plan("T P1.1 done 1 haiku/low | a\n")
        bulk, _ = planfmt.parse_set_text("P1.1 status=done\n")
        with self.assertRaises(tasks.PlanError) as ctx:
            tasks.apply(self.docs, records + bulk, project_id=PROJECT_ID)
        self.assertIn("duplicate task id P1.1 (first on line 1)", ctx.exception.message)


class KeyOrderTests(ServiceCase):
    def test_unknown_keys_and_existing_key_order_are_kept(self):
        original = [{"id": "P1.1", "phase": "P1", "title": "First", "status": "todo", "owner": "ali",
                     "tokensK": 5, "thinking": "low", "model": "haiku", "needsUser": False, "note": "n",
                     "check": "none", "checkK": 0}]
        self.write_tasks(phases=[{"id": "P1", "name": "Engine", "status": "todo"}], task_list=original)
        self.plan("T P1.1 done 5 haiku/low | First\n")
        task = self.read()["tasks"][0]
        self.assertEqual(list(task), [k for k in original[0]])
        self.assertEqual(task["owner"], "ali")
        self.assertEqual(task["status"], "done")

    def test_unknown_top_level_keys_survive(self):
        self.write_tasks(phases=[{"id": "P1", "name": "Engine", "status": "todo"}],
                         task_list=[{"id": "P1.1", "phase": "P1", "title": "x", "status": "todo"}])
        with open(self.path, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["extra"] = {"keep": True}
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        self.plan("P P1 todo | Engine\nT P1.1 done 1 haiku/low | x\n")
        self.assertEqual(self.read()["extra"], {"keep": True})


class AllOrNothingTests(ServiceCase):
    def test_one_bad_line_writes_nothing_even_when_others_are_valid(self):
        records, errors = planfmt.parse_plan("P N1 todo | New\nT N1.1 todo 5 haiku/low | good\n")
        bulk, _ = planfmt.parse_set_text("Z.9 status=done\n")
        self.assertEqual(errors, [])
        with self.assertRaises(tasks.PlanError) as ctx:
            tasks.apply(self.docs, records + bulk, project_id=PROJECT_ID)
        self.assertEqual(ctx.exception.errors, ["line 1: no task Z.9 in tasks.json (allowed: an existing task id; "
                                                "list them with roadmap task list --phase Z)"])
        self.assertIsNone(self.raw())

    def test_existing_file_stays_byte_identical_on_error(self):
        self.plan(EXAMPLE)
        before = self.raw()
        with self.assertRaises(tasks.PlanError):
            self.bulk("M1.1 status=done\nM9.1 status=done\n")
        self.assertEqual(self.raw(), before)

    def test_error_list_carries_every_problem_with_its_line(self):
        records, _ = planfmt.parse_plan("T Q1.1 todo 5 haiku/low | a\nT Q1.2 todo 5 haiku/low | b\n")
        with self.assertRaises(tasks.PlanError) as ctx:
            tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertEqual([e.split(":")[0] for e in ctx.exception.errors], ["line 1", "line 2"])
        self.assertEqual(ctx.exception.next, "roadmap status")

    def test_mixed_problems_get_the_fix_it_next_line(self):
        self.plan(EXAMPLE)
        records, _ = planfmt.parse_plan("T M1.6 todo - -/- | needs a model\n")
        with self.assertRaises(tasks.PlanError) as ctx:
            tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        self.assertIn("with --dry-run", ctx.exception.next)


class PhaseStatusTests(ServiceCase):
    def setUp(self):
        super().setUp()
        self.write_tasks(
            phases=[{"id": "P1", "name": "Engine", "status": "todo"},
                    {"id": "P4", "name": "Linux", "status": "hold"}],
            task_list=[{"id": "P1.1", "phase": "P1", "title": "a", "status": "todo"},
                       {"id": "P1.2", "phase": "P1", "title": "b", "status": "todo"},
                       {"id": "P4.1", "phase": "P4", "title": "c", "status": "todo"}])

    def status_of(self, pid):
        return next(p["status"] for p in self.read()["phases"] if p["id"] == pid)

    def test_any_started_task_makes_the_phase_partial_and_all_done_makes_it_done(self):
        diff = self.bulk("P1.1 status=done\n")
        self.assertEqual(self.status_of("P1"), "partial")
        self.assertIn("P1 status todo→partial", diff["field_diffs"])
        self.bulk("P1.2 status=done\n")
        self.assertEqual(self.status_of("P1"), "done")

    def test_back_to_todo_when_nothing_is_started(self):
        self.bulk("P1.1 status=partial\n")
        self.bulk("P1.1 status=todo\n")
        self.assertEqual(self.status_of("P1"), "todo")

    def test_hold_phase_is_untouched_by_task_changes(self):
        self.bulk("P4.1 status=done\n")
        self.assertEqual(self.status_of("P4"), "hold")
        task = next(t for t in self.read()["tasks"] if t["id"] == "P4.1")
        self.assertEqual(task["status"], "done")

    def test_plan_line_keeps_hold_and_renames(self):
        self.plan("P P4 - | Linux backend\n")
        self.assertEqual(self.status_of("P4"), "hold")
        self.assertEqual(next(p["name"] for p in self.read()["phases"] if p["id"] == "P4"), "Linux backend")

    def test_explicit_hold_on_a_new_phase_stays_hold(self):
        self.plan("P P5 hold | Later\nT P5.1 done 1 haiku/low | x\n")
        self.assertEqual(self.status_of("P5"), "hold")

    def test_phase_without_tasks_keeps_its_explicit_status(self):
        self.plan("P P9 partial | Empty\n")
        self.assertEqual(self.status_of("P9"), "partial")


class ReplacePhaseTests(ServiceCase):
    def setUp(self):
        super().setUp()
        self.write_tasks(
            phases=[{"id": "P1", "name": "Engine", "status": "todo"}, {"id": "P2", "name": "UI", "status": "todo"}],
            task_list=[{"id": "P1.1", "phase": "P1", "title": "a", "status": "todo"},
                       {"id": "P1.2", "phase": "P1", "title": "b", "status": "todo"},
                       {"id": "P1.3", "phase": "P1", "title": "c", "status": "todo"},
                       {"id": "P2.1", "phase": "P2", "title": "d", "status": "todo"}])

    def test_dry_run_lists_the_removals_and_writes_nothing(self):
        before = self.raw()
        diff = self.plan("P P1 todo | Engine\nT P1.1 done 1 haiku/low | a\n", replace_phase="P1", dry_run=True)
        self.assertEqual(diff["tasks_removed"], ["P1.2", "P1.3"])
        self.assertEqual(self.raw(), before)

    def test_real_run_removes_only_the_missing_tasks_of_that_phase(self):
        diff = self.plan("P P1 todo | Engine\nT P1.1 done 1 haiku/low | a\n", replace_phase="P1")
        self.assertEqual(diff["tasks_removed"], ["P1.2", "P1.3"])
        ids = [t["id"] for t in self.read()["tasks"]]
        self.assertEqual(ids, ["P1.1", "P2.1"])
        phase = next(p for p in self.read()["phases"] if p["id"] == "P1")
        self.assertEqual(phase["status"], "done")

    def test_unknown_replace_phase_is_missing(self):
        with self.assertRaises(tasks.PlanError) as ctx:
            self.plan("T P1.1 todo 1 haiku/low | a\n", replace_phase="P7")
        self.assertIn("replace phase P7 does not exist", ctx.exception.message)
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)

    def test_without_replace_nothing_is_deleted(self):
        diff = self.plan("T P1.1 todo 1 haiku/low | a\n")
        self.assertEqual(diff["tasks_removed"], [])
        self.assertEqual(len(self.read()["tasks"]), 4)


class SchemaAndBackupTests(ServiceCase):
    def test_schema_version_is_not_bumped(self):
        self.plan(EXAMPLE)
        self.assertEqual(self.read()["schemaVersion"], 1)
        self.assertEqual(tasks.load(self.docs)["schemaVersion"], 1)

    def test_newer_file_is_refused_and_left_alone(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 2, "phases": [], "tasks": []}, fh)
        before = self.raw()
        with self.assertRaises(RoadmapError) as ctx:
            self.plan(EXAMPLE)
        self.assertEqual(ctx.exception.code, "newer_schema")
        self.assertEqual(ctx.exception.exit, EXIT_INVALID_DATA)
        self.assertEqual(self.raw(), before)

    def test_bad_lists_are_invalid_data(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 1, "phases": {}, "tasks": []}, fh)
        with self.assertRaises(RoadmapError) as ctx:
            tasks.load(self.docs)
        self.assertEqual(ctx.exception.code, "invalid_data")

    def test_more_than_ten_changed_tasks_back_up_the_previous_file_first(self):
        self.plan("P M1 todo | Big\nT M1.1 todo 1 haiku/low | seed\n")
        previous = self.raw()
        lines = "\n".join("T M1.%d todo 1 haiku/low | task %d" % (n, n) for n in range(2, 14))
        diff = self.plan("P M1 todo | Big\n" + lines + "\n")
        self.assertEqual(diff["tasks_added"], ["M1.%d" % n for n in range(2, 14)])
        self.assertIsNotNone(diff["backup"])
        with open(os.path.join(diff["backup"], "tasks.json"), "rb") as fh:
            self.assertEqual(fh.read(), previous)
        self.assertTrue(diff["backup"].startswith(paths.backups_dir(PROJECT_ID)))

    def test_ten_changes_or_fewer_make_no_backup(self):
        diff = self.plan(EXAMPLE)
        self.assertEqual(len(diff["tasks_added"]), 5)
        self.assertIsNone(diff["backup"])
        self.assertFalse(os.path.exists(paths.backups_dir(PROJECT_ID)))

    def test_missing_data_folder_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            tasks.apply(os.path.join(self.folder, "nope"), [], project_id=PROJECT_ID)
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)


class QueryTests(ServiceCase):
    def setUp(self):
        super().setUp()
        self.plan(EXAMPLE)
        self.bulk("M1.1 status=done\nM1.2 status=partial\nM1.3 status=hold\n")

    def test_filters_by_phase_status_and_needs_you(self):
        self.assertEqual([t["id"] for t in tasks.query(self.docs, status="todo,partial")],
                         ["M1.2", "M1.4", "M1.5"])
        self.assertEqual([t["id"] for t in tasks.query(self.docs, needs_you=True)], ["M1.3"])
        self.assertEqual(len(tasks.query(self.docs, phase="M1")), 5)
        self.assertEqual(tasks.query(self.docs, phase="M9"), [])

    def test_limit_caps_the_rows(self):
        self.assertEqual(len(tasks.query(self.docs, limit=2)), 2)
        self.assertEqual(len(tasks.query(self.docs)), 5)

    def test_bad_filters_are_usage_errors(self):
        with self.assertRaises(RoadmapError) as ctx:
            tasks.query(self.docs, status="doing")
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        with self.assertRaises(RoadmapError):
            tasks.query(self.docs, limit=0)


class SummaryTests(ServiceCase):
    def test_small_board_has_the_expected_lines(self):
        self.plan(EXAMPLE)
        self.bulk("M1.1 status=done\n")
        lines = tasks.summary(self.docs, [], name="split-net")
        self.assertTrue(lines[0].startswith("split-net  updated " + planfmt.today() + "  5 tasks: 1 done"))
        self.assertIn("left 4 (~", lines[1])
        self.assertIn("needs-you 1  running 0", lines[1])
        self.assertEqual(lines[2], "M1 Foundations 20%")
        self.assertTrue(any(line.startswith("next: M1.2 sonnet 40k") for line in lines))
        self.assertTrue(any(line.startswith("you: M1.3") for line in lines))

    def test_running_jobs_show_under_run(self):
        self.plan(EXAMPLE)
        jobs = [{"id": "j12", "model": "sonnet", "task": "M1.2", "status": "running",
                 "started": "2020-01-01T00:00:00+00:00"}]
        lines = tasks.summary(self.docs, jobs)
        run = [line for line in lines if line.startswith("run: ")]
        self.assertEqual(len(run), 1)
        self.assertTrue(run[0].startswith("run: j12 sonnet M1.2 "))
        self.assertIn("running 1", "\n".join(lines))

    def test_hold_phases_are_left_off_the_phase_line(self):
        self.write_tasks(phases=[{"id": "P1", "name": "Engine", "status": "todo"},
                                 {"id": "P4", "name": "Linux", "status": "hold"}],
                         task_list=[{"id": "P1.1", "phase": "P1", "title": "a", "status": "done"}])
        phase_line = tasks.summary(self.docs)[2]
        self.assertEqual(phase_line, "P1 Engine 100%")

    def test_large_board_stays_within_the_line_and_character_budget(self):
        phase_text = []
        task_text = []
        for p in range(1, 21):
            phase_text.append("P P%d partial | %s" % (p, "Phase name number %d with words" % p))
            for n in range(1, 31):
                status = ("done", "partial", "todo", "hold")[n % 4]
                task_text.append("T P%d.%d %s 40 sonnet/medium %s| %s" % (
                    p, n, status, "! " if n % 7 == 0 else "", "A rather long task title that goes on " * 5))
        self.plan("\n".join(phase_text + task_text) + "\n")
        jobs = [{"id": "j%d" % n, "model": "opus", "task": "P1.%d" % n, "status": "running",
                 "started": "2020-01-01T00:00:00+00:00"} for n in range(1, 8)]
        lines = tasks.summary(self.docs, jobs)
        self.assertLessEqual(len(lines), 8)
        self.assertLessEqual(len("\n".join(lines)), 700)
        self.assertTrue(lines[0].endswith("hold"))


class ResolveTests(ServiceCase):
    def test_resolve_returns_the_registered_project_and_its_data_folder(self):
        from roadmap.store import config
        config.add_project("Demo", self.folder, project_id=PROJECT_ID)
        project, data_dir = tasks.resolve(PROJECT_ID)
        self.assertEqual(project["id"], PROJECT_ID)
        self.assertEqual(os.path.realpath(data_dir), os.path.realpath(self.docs))


if __name__ == "__main__":
    unittest.main()
