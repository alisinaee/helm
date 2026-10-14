"""Gap tests for the control state (services/control.py): the small parsers and guards, the sentinel text, the warning
and cap texts of a recompute, and the Stop pickup record functions.

Times are passed in (now=) as in tests/unit/test_control.py. Every test runs in a temp ROADMAP_HOME with the
ControlCase fixture; nothing touches the real home, the running service or ~/.claude.
"""

import datetime
import os
import unittest

from roadmap.errors import EXIT_INVALID_DATA, EXIT_USAGE, RoadmapError
from roadmap.services import control
from tests.unit.test_control_support import ControlCase, read_json

MOMENT = datetime.datetime(2026, 10, 13, 14, 2, tzinfo=datetime.timezone.utc).astimezone()


class ParserGuardTests(unittest.TestCase):
    def test_a_project_id_that_is_not_a_plain_id_is_refused_before_any_path_is_built(self):
        with self.assertRaises(RoadmapError) as ctx:
            control.control_path("../escape")
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("invalid_input", EXIT_USAGE))
        with self.assertRaises(RoadmapError):
            control.sentinel_path("bad id")

    def test_a_malformed_time_parses_to_none_and_a_bad_clock_text_is_empty(self):
        self.assertIsNone(control.parse_time("not a time"))
        self.assertIsNone(control.parse_time(""))
        self.assertIsNone(control.parse_time(None))
        self.assertIsNone(control.parse_time(42))
        self.assertIsNotNone(control.parse_time("2026-10-13T14:02:00+00:00"))
        self.assertEqual(control.clock_text("not a time"), "")

    def test_only_real_numbers_are_numbers(self):
        self.assertEqual(control._number(3), 3.0)
        self.assertEqual(control._number(2.5), 2.5)
        self.assertIsNone(control._number(True))
        self.assertIsNone(control._number(False))
        self.assertIsNone(control._number("5"))
        self.assertIsNone(control._number(float("nan")))
        self.assertIsNone(control._number(None))

    def test_a_zero_or_negative_limit_is_full_as_soon_as_anything_is_spent(self):
        self.assertEqual(control._pct(5.0, 0.0), 100.0)
        self.assertEqual(control._pct(0.0, 0.0), 0.0)
        self.assertEqual(control._pct(1.0, -3.0), 100.0)
        self.assertEqual(control._pct(50.0, 100.0), 50.0)
        self.assertIsNone(control._pct(5.0, None))

    def test_a_task_id_must_match_the_plain_id_pattern(self):
        self.assertEqual(control._task_id(" P0.1 "), "P0.1")
        with self.assertRaises(RoadmapError) as ctx:
            control._task_id("bad id")
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("usage", EXIT_USAGE))


class ControlFileTests(ControlCase):
    def test_a_control_file_that_is_not_an_object_is_invalid_data_and_left_alone(self):
        path = control.control_path("demo")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("[1, 2]")
        with self.assertRaises(RoadmapError) as ctx:
            control.read_state("demo")
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("invalid_data", EXIT_INVALID_DATA))
        self.assertEqual(control.pickup_record("demo"), {})  # a broken file gives no pickup record
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "[1, 2]")

    def test_the_sentinel_says_stopped_by_user_then_names_the_stopped_tasks(self):
        self.assertEqual(control._sentinel_text({"stop": True, "block": None, "stopTasks": []}), "stopped by user")
        self.assertEqual(control._sentinel_text({"stop": False, "block": None, "stopTasks": ["P0.1", "P0.2"]}),
                         "stopped tasks: P0.1, P0.2")

    def test_the_sentinel_file_follows_a_project_stop_and_a_task_stop(self):
        control.stop("demo", now=MOMENT)
        with open(control.sentinel_path("demo"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "stopped by user\n")
        control.resume("demo", now=MOMENT)
        control.stop("demo", task="P0.2", now=MOMENT)
        with open(control.sentinel_path("demo"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "stopped tasks: P0.2\n")


class RecomputeWarningTests(ControlCase):
    def test_an_unreadable_budget_is_a_warning_and_the_recompute_still_saves(self):
        with open(os.path.join(self.docs, "budget.json"), "w", encoding="utf-8") as fh:
            fh.write("{broken")
        state = control.recompute("demo", now=MOMENT)
        self.assertTrue(any(w.startswith("budget unreadable: ") for w in state["warn"]), state["warn"])
        self.assertIsNone(state["block"])
        self.assertEqual(read_json(control.control_path("demo"))["project"], "demo")

    def test_a_phase_cap_reached_marks_each_task_of_the_phase_with_its_reason(self):
        self.set_budget(limits={"phases": {"P0": 10}}, spent={"P0.2": {"haiku": 12}})
        state = control.recompute("demo", now=MOMENT)
        self.assertEqual(state["taskBlocks"]["P0.1"], "phase P0 cap reached")
        self.assertEqual(state["taskBlocks"]["P0.2"], "phase P0 cap reached")
        self.assertNotIn("P1.1", state["taskBlocks"])

    def test_a_task_cap_reached_records_the_task_reason(self):
        self.set_budget(spent={"P0.1": {"sonnet": 60}})
        state = control.recompute("demo", now=MOMENT)
        self.assertEqual(state["taskBlocks"], {"P0.1": "task P0.1 cap reached"})

    def test_a_model_over_its_cap_is_a_warning_only(self):
        self.set_budget(limits={"models": {"sonnet": 10}}, spent={"P0.2": {"sonnet": 12}})
        state = control.recompute("demo", now=MOMENT)
        self.assertIn("model sonnet over its cap (warning only)", state["warn"])
        self.assertIsNone(state["block"])
        self.assertEqual(state["stopTasks"], [])
        self.assertFalse(self.sentinel_exists())


class PickupRecordTests(ControlCase):
    def test_pickup_counts_restart_for_a_new_task_set_and_clear_empties_them(self):
        self.assertEqual(control.pickup_record("demo"), {})
        control.record_pickup("demo", "keyA", now=MOMENT)
        self.assertEqual(control.pickup_record("demo"), {"key": "keyA", "blocks": 1})
        control.record_pickup("demo", "keyA", now=MOMENT)
        self.assertEqual(control.pickup_record("demo"), {"key": "keyA", "blocks": 2})
        control.record_pickup("demo", "keyB", now=MOMENT)
        self.assertEqual(control.pickup_record("demo"), {"key": "keyB", "blocks": 1})
        state = control.clear_pickup("demo", now=MOMENT)
        self.assertEqual(state["pickup"], {})
        self.assertEqual(control.pickup_record("demo"), {})
        self.assertEqual(self.control()["pickup"], {})


if __name__ == "__main__":
    unittest.main()
