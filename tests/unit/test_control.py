"""Control state service: stop, resume, override, the sentinel, budget, phase, task and weekly limits, agent refusals.

Times are passed in explicitly (now=) so the expiry rules are tested without sleeping.
"""

import datetime
import json
import os
from unittest import mock

from roadmap.errors import EXIT_INVALID_DATA, RoadmapError
from roadmap.services import control, limits_v2, queue, questions
from tests.unit.test_control_support import ControlCase, read_json, write_json

MOMENT = datetime.datetime(2026, 10, 13, 14, 2, tzinfo=datetime.timezone.utc).astimezone()
AGENT = {"CLAUDECODE": "1"}


class StopResumeTests(ControlCase):
    def test_stop_writes_state_and_sentinel_with_an_activity_reference(self):
        state = control.stop("demo", now=MOMENT)
        self.assertTrue(state["stop"])
        self.assertEqual(state["stopRef"], "A1")
        self.assertEqual(self.control()["stop"], True)
        self.assertTrue(self.sentinel_exists())
        with open(os.path.join(self.docs, "activity.jsonl"), encoding="utf-8") as fh:
            last = json.loads(fh.read().splitlines()[-1])
        self.assertEqual((last["op"], last["src"], last["undo"]), ("control.stop", "cli", True))

    def test_resume_clears_the_stop_and_removes_the_sentinel(self):
        control.stop("demo", now=MOMENT)
        state = control.resume("demo", now=MOMENT)
        self.assertFalse(state["stop"])
        self.assertFalse(self.sentinel_exists())
        self.assertEqual(control.summary_line("demo"), "running")

    def test_stop_is_allowed_from_an_agent_but_resume_is_refused(self):
        with mock.patch.dict(os.environ, AGENT):
            control.stop("demo", now=MOMENT)
            with self.assertRaises(RoadmapError) as ctx:
                control.resume("demo", now=MOMENT)
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertTrue(self.control()["stop"])

    def test_stop_task_only_lists_that_task_and_is_resumed_with_resume(self):
        state = control.stop("demo", task="P0.2", now=MOMENT)
        self.assertFalse(state["stop"])
        self.assertEqual(state["stopTasks"], ["P0.2"])
        self.assertIn("P0.2", state["taskBlocks"])
        self.assertTrue(self.sentinel_exists())
        self.assertEqual(control.resume("demo", now=MOMENT)["stopTasks"], [])
        self.assertFalse(self.sentinel_exists())

    def test_task_id_must_be_a_plain_id(self):
        with self.assertRaises(RoadmapError) as ctx:
            control.stop("demo", task="bad id;rm", now=MOMENT)
        self.assertEqual(ctx.exception.exit, 2)

    def test_unknown_project_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            control.stop("ghost", now=MOMENT)
        self.assertEqual(ctx.exception.exit, 3)


class OverrideTests(ControlCase):
    def test_override_sets_a_time_one_to_four_hours_away(self):
        state = control.override("demo", 2, now=MOMENT)
        until = datetime.datetime.fromisoformat(state["overrideUntil"])
        self.assertEqual(until - MOMENT, datetime.timedelta(hours=2))

    def test_override_outside_one_to_four_hours_is_a_usage_error(self):
        for hours in (0, 0.5, 4.5, 9, "x"):
            with self.assertRaises(RoadmapError) as ctx:
                control.override("demo", hours, now=MOMENT)
            self.assertEqual(ctx.exception.exit, 2)

    def test_override_is_refused_from_an_agent(self):
        with mock.patch.dict(os.environ, AGENT), self.assertRaises(RoadmapError):
            control.override("demo", 1, now=MOMENT)
        self.assertIsNone(self.control())

    def test_an_expired_override_is_dropped_on_recompute(self):
        control.override("demo", 1, now=MOMENT)
        state = control.recompute("demo", now=MOMENT + datetime.timedelta(hours=3))
        self.assertIsNone(state["overrideUntil"])


class BudgetAndWeeklyTests(ControlCase):
    def test_project_budget_warns_at_80_and_blocks_at_100(self):
        self.set_budget(limits={"project": 100}, spent={"P0.2": {"sonnet": 85}})
        state = control.recompute("demo", now=MOMENT)
        self.assertIsNone(state["block"])
        self.assertTrue(any("80" in w or "85" in w for w in state["warn"]))
        self.assertFalse(self.sentinel_exists())
        self.set_budget(limits={"project": 100}, spent={"P0.2": {"sonnet": 100}})
        state = control.recompute("demo", now=MOMENT)
        self.assertEqual(state["block"]["scope"], "project")
        self.assertIn("project budget 100%", state["block"]["reason"])
        self.assertTrue(self.sentinel_exists())
        self.assertEqual(control.summary_line("demo", now=MOMENT), "blocked: " + state["block"]["reason"])

    def test_task_cap_stops_only_that_task(self):
        self.set_budget(spent={"P0.1": {"sonnet": 60}})
        state = control.recompute("demo", now=MOMENT)
        self.assertEqual(state["stopTasks"], ["P0.1"])
        self.assertIsNone(state["block"])
        self.assertTrue(self.sentinel_exists())

    def test_budget_limit_for_a_task_overrides_its_cap(self):
        self.set_budget(limits={"tasks": {"P0.1": 200}}, spent={"P0.1": {"sonnet": 60}})
        self.assertEqual(control.recompute("demo", now=MOMENT)["stopTasks"], [])

    def test_phase_cap_stops_every_task_of_that_phase(self):
        self.set_budget(limits={"phases": {"P0": 10}}, spent={"P0.2": {"haiku": 12}})
        state = control.recompute("demo", now=MOMENT)
        self.assertEqual(state["stopTasks"], ["P0.1", "P0.2"])
        self.assertNotIn("P1.1", state["stopTasks"])

    def test_weekly_usage_blocks_at_stop_at_percent(self):
        limits_v2.set_window("week", {"on": True, "mode": "cap", "value": 100})
        self.set_usage(101)
        state = control.recompute("demo", now=MOMENT)
        self.assertIn("week usage reached the stop at 100%", state["block"]["reason"])

    def test_weekly_limit_set_lower_blocks_earlier_and_warns_before(self):
        self.set_usage(85)
        control.set_weekly_limit("demo", 90, now=MOMENT)
        state = control.recompute("demo", now=MOMENT)
        self.assertIsNone(state["block"])
        control.set_weekly_limit("demo", 80, now=MOMENT)
        self.assertIn("week usage reached the stop at 80%", control.recompute("demo", now=MOMENT)["block"]["reason"])

    def test_weekly_limit_is_refused_from_an_agent(self):
        with mock.patch.dict(os.environ, AGENT), self.assertRaises(RoadmapError) as ctx:
            control.set_weekly_limit("demo", 50, now=MOMENT)
        self.assertEqual(ctx.exception.code, "agent_refused")

    def test_weekly_limit_must_be_a_percent_from_1_to_100(self):
        for value in (0, 101, "x"):
            with self.assertRaises(RoadmapError):
                control.set_weekly_limit("demo", value, now=MOMENT)

    def test_override_lets_a_budget_block_through_only_until_it_expires(self):
        limits_v2.set_window("week", {"on": True, "mode": "cap", "value": 100})
        self.set_usage(120)
        control.recompute("demo", now=MOMENT)
        control.override("demo", 1, now=MOMENT)
        self.assertTrue(self.sentinel_exists())
        self.assertIn("override", control.summary_line("demo", now=MOMENT))
        self.assertTrue(control.summary_line("demo", now=MOMENT).startswith("running"))

    def test_budget_raise_is_refused_from_an_agent_but_a_lower_limit_is_allowed(self):
        control.set_budget_limit("demo", "project", None, 100, now=MOMENT)
        with mock.patch.dict(os.environ, AGENT):
            with self.assertRaises(RoadmapError) as ctx:
                control.set_budget_limit("demo", "project", None, 200, now=MOMENT)
            self.assertEqual(ctx.exception.code, "agent_refused")
            with self.assertRaises(RoadmapError):
                control.set_budget_limit("demo", "project", None, None, now=MOMENT)
            control.set_budget_limit("demo", "project", None, 50, now=MOMENT)
        self.assertEqual(control.recompute("demo", now=MOMENT)["stopTasks"], [])
        self.assertEqual(read_json(os.path.join(self.docs, "budget.json"))["limits"]["project"], 50)

    def test_setting_a_first_limit_is_allowed_from_an_agent(self):
        with mock.patch.dict(os.environ, AGENT):
            control.set_budget_limit("demo", "tasks", "P0.2", 30, now=MOMENT)
        self.assertEqual(read_json(os.path.join(self.docs, "budget.json"))["limits"]["tasks"], {"P0.2": 30.0})

    def test_unknown_budget_scope_is_refused(self):
        with self.assertRaises(RoadmapError):
            control.set_budget_limit("demo", "team", "x", 1, now=MOMENT)


class PhaseApprovalTests(ControlCase):
    def test_approve_marks_the_phase_once(self):
        result = control.approve_phase("demo", "P0", now=MOMENT)
        self.assertEqual(result, {"phase": "P0", "approved": True, "changed": True})
        self.assertTrue(self.read_tasks()["phases"][0]["approved"])
        again = control.approve_phase("demo", "P0", now=MOMENT)
        self.assertFalse(again["changed"])

    def test_approve_unknown_phase_is_not_found_and_agents_are_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            control.approve_phase("demo", "P9", now=MOMENT)
        self.assertEqual(ctx.exception.exit, 3)
        with mock.patch.dict(os.environ, AGENT), self.assertRaises(RoadmapError):
            control.approve_phase("demo", "P0", now=MOMENT)
        self.assertNotIn("approved", self.read_tasks()["phases"][0])


class RobustnessTests(ControlCase):
    def test_a_corrupt_control_file_refuses_the_write_and_is_left_alone(self):
        path = os.path.join(self.state_dir, "control-demo.json")
        os.makedirs(self.state_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("[1, 2]")
        with self.assertRaises(RoadmapError) as ctx:
            control.stop("demo", now=MOMENT)
        self.assertEqual(ctx.exception.exit, EXIT_INVALID_DATA)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "[1, 2]")

    def test_after_write_never_raises(self):
        os.makedirs(self.state_dir, exist_ok=True)
        with open(os.path.join(self.state_dir, "control-demo.json"), "w", encoding="utf-8") as fh:
            fh.write("garbage")
        self.assertIsNone(control.after_write("demo", now=MOMENT))
        self.assertIsNone(control.after_write("ghost", now=MOMENT))

    def test_a_broken_tasks_file_is_a_warning_not_a_crash(self):
        with open(os.path.join(self.docs, "tasks.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.set_budget(spent={"P0.1": {"sonnet": 1}})
        state = control.recompute("demo", now=MOMENT)
        self.assertTrue(any("tasks.json unreadable" in w for w in state["warn"]))

    def test_summary_line_states(self):
        self.assertEqual(control.summary_line("demo"), "running")
        control.stop("demo", now=MOMENT)
        self.assertEqual(control.summary_line("demo"), "stopped by user at " + MOMENT.strftime("%H:%M"))


class PendingLinesTests(ControlCase):
    def test_queued_requests_and_open_questions_are_listed(self):
        queue.enqueue(os.path.join(self.docs), "P0.2", by="lead", now=MOMENT)
        questions.ask(os.path.join(self.docs), "P0.1", "Use plan A?", opts=["A", "B"], default="A", now=MOMENT)
        lines = control.pending_lines(os.path.join(self.docs), limit=6, now=MOMENT)
        self.assertEqual(lines[0], "queued: P0.2 (lead)")
        self.assertTrue(lines[1].startswith("open question Q1"))
        self.assertLessEqual(len(control.pending_lines(os.path.join(self.docs), limit=1, now=MOMENT)), 1)
