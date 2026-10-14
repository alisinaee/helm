"""Gap tests for the hook driver (services/hooks.py): the detector reap rules, the config and state readers, the
fail-open wrapper, the busy-lock close path, the task of an agent and the Stop pickup count clear.

Every test runs in a temp ROADMAP_HOME with its own project folder. Time is passed in (now=, entry started=), so no
test sleeps or reads the real clock. Nothing touches the real home, the running service or ~/.claude.
"""

import datetime
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, RoadmapError
from roadmap.services import control, hooks, jobs
from roadmap.store import config, paths, schema
from tests.unit.test_control_support import ControlCase
from tests.unit.test_jobs_support import FixtureCase, ROADMAP_CONFIG, write_json

NOW = 1_800_000_000.0
CONTROL_MOMENT = datetime.datetime(2026, 10, 13, 14, 2, tzinfo=datetime.timezone.utc).astimezone()


class ReapRuleTests(unittest.TestCase):
    """The reap verdicts of each detector, called directly with an injected now."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rb-hooks-gaps-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def entry(self, watch="", age=0.0):
        return {"job": "j1", "started": NOW - age, "watch": watch}

    def test_agent_without_a_watch_file_is_done_only_past_the_max_age(self):
        det = hooks.AgentDetector()
        self.assertIsNone(det.reap(self.entry(age=10), NOW))
        self.assertEqual(det.reap(self.entry(age=hooks.MAX_AGE_S + 1), NOW), "done")

    def test_agent_with_a_missing_watch_file_is_done_only_past_the_max_age(self):
        det = hooks.AgentDetector()
        gone = os.path.join(self.tmp, "no-such.output")
        self.assertIsNone(det.reap(self.entry(watch=gone, age=10), NOW))
        self.assertEqual(det.reap(self.entry(watch=gone, age=hooks.MAX_AGE_S + 1), NOW), "done")

    def test_agent_output_quiet_longer_than_idle_is_done(self):
        det = hooks.AgentDetector()
        out = os.path.join(self.tmp, "agent.output")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("working\n")
        os.utime(out, (NOW - hooks.IDLE_S - 5, NOW - hooks.IDLE_S - 5))
        self.assertEqual(det.reap(self.entry(watch=out, age=600), NOW), "done")
        os.utime(out, (NOW - 10, NOW - 10))
        self.assertIsNone(det.reap(self.entry(watch=out, age=600), NOW))

    def test_file_job_with_an_error_first_line_is_failed_and_clean_one_is_done(self):
        det = hooks.AgyDetector()
        result = os.path.join(self.tmp, "bad.result.md")
        with open(result, "w", encoding="utf-8") as fh:
            fh.write("error: the companion did not start\nmore\n")
        self.assertEqual(det.reap(self.entry(watch=result), NOW), "failed")
        with open(result, "w", encoding="utf-8") as fh:
            fh.write("all good\n")
        self.assertEqual(det.reap(self.entry(watch=result), NOW), "done")

    def test_file_job_with_no_result_is_failed_only_at_the_timeout(self):
        det = hooks.AgyDetector()
        missing = os.path.join(self.tmp, "never.result.md")
        self.assertIsNone(det.reap(self.entry(watch=missing, age=60), NOW))
        self.assertEqual(det.reap(self.entry(watch=missing, age=hooks.MAX_AGE_S + 1), NOW), "failed")

    def test_first_line_check_is_false_for_a_missing_file(self):
        self.assertFalse(hooks._first_line_has_error(os.path.join(self.tmp, "absent.md")))

    def test_first_line_check_only_reads_the_first_line(self):
        path = os.path.join(self.tmp, "second.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("fine\nerror on line two\n")
        self.assertFalse(hooks._first_line_has_error(path))

    def test_an_uncompilable_task_pattern_is_invalid_data(self):
        with self.assertRaises(RoadmapError) as ctx:
            hooks.task_regex("a(")
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("invalid_data", EXIT_INVALID_DATA))


class ProjectSettingsTests(FixtureCase):
    def config_path(self):
        return os.path.join(self.docs, "roadmap.config.json")

    def test_a_config_from_a_newer_build_is_newer_schema(self):
        write_json(self.config_path(), dict(ROADMAP_CONFIG, schemaVersion=schema.current_version("roadmap_config") + 7))
        with self.assertRaises(RoadmapError) as ctx:
            hooks.project_settings(self.docs)
        self.assertEqual((ctx.exception.code, ctx.exception.exit), ("newer_schema", EXIT_INVALID_DATA))

    def test_hook_detectors_that_is_not_a_list_is_invalid_data(self):
        write_json(self.config_path(), dict(ROADMAP_CONFIG, hookDetectors="agy"))
        with self.assertRaises(RoadmapError) as ctx:
            hooks.project_settings(self.docs)
        self.assertEqual(ctx.exception.code, "invalid_data")
        self.assertIn("hookDetectors must be a list", ctx.exception.message)

    def test_non_string_detector_names_are_dropped_and_the_pattern_defaults(self):
        write_json(self.config_path(), {"schemaVersion": 1, "id": "demo", "title": "Demo",
                                        "hookDetectors": ["agy", 3, None, "nope"]})
        pattern, names = hooks.project_settings(self.docs)
        self.assertEqual(pattern, hooks.DEFAULT_PATTERN)
        self.assertEqual(names, ["agy", "nope"])

    def test_a_project_without_detectors_key_watches_all_of_them(self):
        write_json(self.config_path(), {"schemaVersion": 1, "id": "demo", "title": "Demo"})
        self.assertEqual(hooks.project_settings(self.docs)[1], list(hooks.DEFAULT_DETECTORS))


class RunHookWrapperTests(FixtureCase):
    def test_an_unexpected_error_in_the_handler_is_logged_by_type_and_returns_none(self):
        with mock.patch.object(hooks, "_handle", side_effect=RuntimeError("boom")):
            self.assertIsNone(hooks.run_hook('{"hook_event_name": "Stop"}', now=NOW))
        self.assertIn("error RuntimeError: boom", self.log_text())

    def test_a_project_whose_data_folder_is_gone_is_skipped_and_logged(self):
        shutil.rmtree(self.docs)
        hooks.run_hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Agent", "cwd": self.project,
                                   "tool_input": {"description": "P0.8"}, "tool_response": {}}), now=NOW)
        self.assertIn("data folder missing for demo", self.log_text())
        self.assertFalse(os.path.exists(os.path.join(os.environ["ROADMAP_HOME"], "state", "hooks-demo.json")))

    def test_an_unknown_detector_name_is_logged_and_the_known_ones_still_run(self):
        write_json(os.path.join(self.docs, "roadmap.config.json"),
                   dict(ROADMAP_CONFIG, hookDetectors=["nope", "agent"]))
        hooks.run_hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Agent", "cwd": self.project,
                                   "tool_input": {"model": "haiku", "description": "P0.8 parser", "prompt": "go"},
                                   "tool_response": {"agentId": "d1d2d3d4e5"}}), now=NOW)
        self.assertIn("unknown detector 'nope' in demo", self.log_text())
        self.assertEqual(self.read_jobs()[0]["task"], "P0.8")


class TaskOfAgentTests(FixtureCase):
    def start_agent(self, agent_id):
        hooks.run_hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Agent", "cwd": self.project,
                                   "tool_input": {"model": "haiku", "description": "P0.8 parser", "prompt": "go"},
                                   "tool_response": {"agentId": agent_id}}), now=NOW)

    def test_an_agent_maps_to_the_task_of_its_job(self):
        self.start_agent("e1e2e3e4e5")
        project = config.get_project("demo")
        self.assertEqual(hooks._task_of_agent(project, "e1e2e3e4e5"), "P0.8")

    def test_an_unmapped_or_empty_agent_id_gives_none(self):
        self.start_agent("e1e2e3e4e5")
        project = config.get_project("demo")
        self.assertIsNone(hooks._task_of_agent(project, "ffffffff00"))
        self.assertIsNone(hooks._task_of_agent(project, ""))

    def test_no_hook_state_file_gives_none(self):
        self.assertIsNone(hooks._task_of_agent(config.get_project("demo"), "e1e2e3e4e5"))


class ReadStateTests(FixtureCase):
    def test_active_that_is_not_a_list_is_invalid_data_and_left_alone(self):
        path = paths.hooks_file("demo")
        write_json(path, {"schemaVersion": schema.current_version("hooks"), "project": "demo", "active": {}})
        with self.assertRaises(RoadmapError) as ctx:
            hooks._read_state(path)
        self.assertEqual(ctx.exception.code, "invalid_data")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["active"], {})


class CloseLockTests(FixtureCase):
    def test_a_busy_project_lock_keeps_the_entry_for_a_retry(self):
        busy = RoadmapError("locked", "busy", EXIT_CONFLICT)
        with mock.patch.object(jobs, "finish_job", side_effect=busy) as finish:
            self.assertFalse(hooks._close(self.docs, {"job": "j1"}, "done"))
        finish.assert_called_once()

    def test_a_busy_lock_stops_the_close_loop_at_the_first_entry(self):
        entries = [{"job": "j1", "watch": ""}, {"job": "j2", "watch": ""}]
        busy = RoadmapError("locked", "busy", EXIT_CONFLICT)
        with mock.patch.object(jobs, "finish_job", side_effect=busy) as finish:
            closed = hooks._close_some(self.docs, entries, lambda e: "done")
        self.assertEqual(closed, [])
        self.assertEqual(finish.call_count, 1)


class StopPickupClearTests(ControlCase):
    def stop_event(self):
        return hooks.run_hook(json.dumps({"hook_event_name": "Stop", "cwd": self.project, "session_id": "s1",
                                          "stop_hook_active": False}), now=CONTROL_MOMENT.timestamp())

    def test_an_empty_queue_clears_a_recorded_pickup_count(self):
        control.record_pickup("demo", "keyA", now=CONTROL_MOMENT)
        self.assertEqual(control.pickup_record("demo"), {"key": "keyA", "blocks": 1})
        self.assertIsNone(self.stop_event())
        self.assertEqual(control.pickup_record("demo"), {})

    def test_an_empty_queue_with_no_recorded_count_writes_nothing(self):
        self.assertIsNone(self.stop_event())
        self.assertIsNone(self.control())


if __name__ == "__main__":
    unittest.main()
