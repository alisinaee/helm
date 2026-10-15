"""Tests for the hook entry and driver: payload to job registration, closing, detectors, state and silence."""

import json
import os
import time
import unittest
from unittest import mock

from roadmap.services import hooks, presence
from roadmap.store import lock
from tests.unit.test_jobs_support import FixtureCase, ROADMAP_CONFIG, run_cli, write_json
from tests.unit.test_store_support import mode_of


class HookTestCase(FixtureCase):
    def fire(self, **payload):
        """Send one hook event through the driver with this project as its cwd."""
        payload.setdefault("cwd", self.project)
        hooks.run_hook(json.dumps(payload))

    def agent_start(self, description="Parser fix P0.8", model="sonnet", output="/nonexistent/out.output",
                    agent_id="a1b2c3d4e5", effort=None):
        tool_input = {"description": description, "prompt": "do it"}
        if model is not None:
            tool_input["model"] = model
        if effort is not None:
            tool_input["effort"] = effort
        self.fire(hook_event_name="PostToolUse", tool_name="Agent", tool_input=tool_input,
                  tool_response={"agentId": agent_id, "output_file": output})

    def state_active(self):
        path = os.path.join(os.environ["ROADMAP_HOME"], "state", "hooks-demo.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["active"]


class AgentDetectorTests(HookTestCase):
    def test_agent_payload_registers_job_with_task_and_model(self):
        self.agent_start()
        jobs_now = self.read_jobs()
        self.assertEqual(len(jobs_now), 1)
        job = jobs_now[0]
        self.assertEqual(job["task"], "P0.8")
        self.assertEqual(job["model"], "sonnet")
        self.assertEqual(job["status"], "running")
        self.assertEqual(job["title"], "sonnet: Parser fix P0.8")
        active = self.state_active()
        self.assertEqual(active[0]["agent"], "a1b2c3d4e5")
        self.assertEqual(active[0]["detector"], "agent")
        self.assertEqual(mode_of(os.path.join(os.environ["ROADMAP_HOME"], "state", "hooks-demo.json")), 0o600)

    def test_task_id_may_come_from_the_prompt(self):
        self.fire(hook_event_name="PostToolUse", tool_name="Task", model="claude-opus-5-5",
                  tool_input={"description": "review", "prompt": "Check WP4 now"},
                  tool_response={"agentId": "zz99887766"})
        job = self.read_jobs()[0]
        self.assertEqual(job["task"], "WP4")
        self.assertEqual(job["model"], "opus")  # no model given: the session model the hook knows

    def test_no_model_and_no_known_session_model_is_not_labelled_haiku(self):
        self.agent_start(model=None)
        jobs = self.read_jobs()
        self.assertEqual(len(jobs), 1)  # "unknown" is a valid job model: tracked, never labelled haiku
        self.assertEqual(jobs[0]["model"], "unknown")

    def test_agent_effort_is_recorded_when_the_call_carries_it(self):
        self.agent_start(effort="High")
        self.assertEqual(self.read_jobs()[0]["effort"], "high")

    def test_agent_effort_outside_the_levels_is_not_recorded(self):
        self.agent_start(effort="turbo")
        job = self.read_jobs()[0]
        self.assertNotIn("effort", job)
        self.assertEqual(job["model"], "sonnet")

    def test_payload_without_a_known_task_is_still_registered(self):
        # A5: no known id in description or prompt -> the job is always registered; with no head job in the last
        # hour and no R7.31 in tasks.json, it is registered with no task (never dropped).
        self.agent_start(description="refactor the parser P9.9 and nothing else")
        self.agent_start(description="no id at all", agent_id="b1b2c3d4e5")
        jobs_now = self.read_jobs()
        self.assertEqual(len(jobs_now), 2)
        self.assertTrue(all("task" not in j and j["status"] == "running" for j in jobs_now))
        self.assertEqual(len(self.state_active()), 2)
        self.assertIn("warning: agent job names no task", self.log_text())

    def test_unknown_model_registers_nothing_and_logs_why(self):
        self.agent_start(model="gpt-9")
        self.assertEqual(self.read_jobs(), [])
        self.assertIn("model must be one of", self.log_text())

    def test_subagent_stop_closes_the_matching_job(self):
        self.agent_start()
        self.fire(hook_event_name="SubagentStop", agent_id="a1b2c3d4e5")
        self.assertEqual(self.read_jobs()[0]["status"], "done")
        self.assertEqual(self.state_active(), [])

    def test_subagent_stop_for_another_agent_closes_nothing(self):
        self.agent_start()
        self.fire(hook_event_name="SubagentStop", agent_id="someoneelse")
        self.assertEqual(self.read_jobs()[0]["status"], "running")

    def test_stop_reaps_agent_whose_output_went_quiet(self):
        output = os.path.join(self.tmp, "agent.output")
        with open(output, "w", encoding="utf-8") as fh:
            fh.write("working\n")
        self.agent_start(output=output)
        self.assertEqual(self.read_jobs()[0]["status"], "running")
        old = time.time() - 200
        os.utime(output, (old, old))  # quiet for 200 s now
        self.fire(hook_event_name="Stop")
        self.assertEqual(self.read_jobs()[0]["status"], "done")

    def test_recent_output_keeps_the_agent_running(self):
        output = os.path.join(self.tmp, "fresh.output")
        with open(output, "w", encoding="utf-8") as fh:
            fh.write("working\n")
        self.agent_start(output=output)
        self.fire(hook_event_name="Stop")
        self.assertEqual(self.read_jobs()[0]["status"], "running")


class CommandDetectorTests(HookTestCase):
    def test_agy_registers_and_closes_when_the_result_file_appears(self):
        result = os.path.join(self.tmp, "r.result.md")
        command = 'node "/opt/agy-companion.mjs" task --prompt "Review P0.8 parser"'
        self.fire(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": command},
                  tool_response={"stdout": "started\nresult file: " + result})
        job = self.read_jobs()[0]
        self.assertEqual((job["model"], job["task"], job["status"]), ("agy", "P0.8", "running"))
        self.assertTrue(job["title"].startswith("agy task: "))
        self.fire(hook_event_name="Stop")
        self.assertEqual(self.read_jobs()[0]["status"], "running")  # result not written yet
        with open(result, "w", encoding="utf-8") as fh:
            fh.write("all good\n")
        self.fire(hook_event_name="Stop")
        self.assertEqual(self.read_jobs()[0]["status"], "done")
        self.assertEqual(self.state_active(), [])

    def test_agy_wait_or_cancel_registers_nothing(self):
        result = os.path.join(self.tmp, "w.result.md")
        command = 'node "/opt/agy-companion.mjs" wait --prompt "P0.8"'
        self.fire(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": command},
                  tool_response={"stdout": "result file: " + result})
        self.assertEqual(self.read_jobs(), [])

    def test_cursor_registers_and_fails_on_an_error_file(self):
        result = os.path.join(self.tmp, "cur.result.md")
        command = '/Users/x/tools/cursor-review2.sh ' + result + ' "review P0.8 parser"'
        self.fire(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": command},
                  tool_response={"stdout": ""})
        job = self.read_jobs()[0]
        self.assertEqual((job["model"], job["task"]), ("cursor", "P0.8"))
        with open(result, "w", encoding="utf-8") as fh:
            fh.write("error: the review did not start\n")
        self.fire(hook_event_name="Stop")
        self.assertEqual(self.read_jobs()[0]["status"], "failed")

    def test_plain_bash_commands_register_nothing(self):
        self.fire(hook_event_name="PostToolUse", tool_name="Bash",
                  tool_input={"command": "git status P0.8"}, tool_response={"stdout": "clean"})
        self.assertEqual(self.read_jobs(), [])


class DetectorSelectionTests(HookTestCase):
    def test_project_hook_detectors_limit_what_is_watched(self):
        write_json(os.path.join(self.docs, "roadmap.config.json"),
                   dict(ROADMAP_CONFIG, hookDetectors=["agy"]))
        self.agent_start()
        self.assertEqual(self.read_jobs(), [])
        result = os.path.join(self.tmp, "only.result.md")
        self.fire(hook_event_name="PostToolUse", tool_name="Bash",
                  tool_input={"command": 'node "/x/agy-companion.mjs" task --prompt "P0.8"'},
                  tool_response={"stdout": "result file: " + result})
        self.assertEqual(self.read_jobs()[0]["model"], "agy")

    def test_task_pattern_comes_from_the_project(self):
        write_json(os.path.join(self.docs, "roadmap.config.json"),
                   dict(ROADMAP_CONFIG, taskIdPattern=r"^WP[0-9]+$"))
        self.agent_start(description="P0.8 is not a task in this project")
        self.assertNotIn("task", self.read_jobs()[0])  # not a task here: registered with the fallback (none here)
        self.agent_start(description="WP4 is", agent_id="c1b2c3d4e5")
        self.assertEqual(self.read_jobs()[1]["task"], "WP4")
        self.assertEqual(len(self.read_jobs()), 2)

    def test_pattern_matching_is_unanchored_inside_text(self):
        regex = hooks.task_regex(r"^[A-Z]+[0-9]+(\.[0-9]+)?$")
        self.assertEqual(hooks.find_task("see (P0.8), done", regex, {"P0.8"}), "P0.8")
        self.assertIsNone(hooks.find_task("XP0.8x", regex, {"P0.8"}))


class ResilienceTests(HookTestCase):
    def test_malformed_stdin_exits_zero_and_prints_nothing(self):
        code, out, err = run_cli(["hook"], stdin_text="{not json")
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertIn("not valid JSON", self.log_text())

    def test_empty_stdin_exits_zero_and_prints_nothing(self):
        code, out, err = run_cli(["hook"], stdin_text="")
        self.assertEqual((code, out, err), (0, "", ""))

    def test_non_object_json_is_logged_and_ignored(self):
        code, out, _ = run_cli(["hook"], stdin_text="[1, 2]")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("not a JSON object", self.log_text())

    def test_stop_event_through_the_cli_exits_zero_silently(self):
        code, out, err = run_cli(["hook"], stdin_text=json.dumps({"hook_event_name": "Stop", "cwd": self.project}))
        self.assertEqual((code, out, err), (0, "", ""))

    def test_event_outside_any_registered_project_does_nothing(self):
        self._set_env("ROADMAP_PROJECT", None)
        hooks.run_hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Agent", "cwd": self.tmp,
                                   "tool_input": {"description": "P0.8"}, "tool_response": {}}))
        self.assertIn("no registered project", self.log_text())
        self.assertFalse(os.path.exists(os.path.join(os.environ["ROADMAP_HOME"], "state", "hooks-demo.json")))

    def test_corrupt_state_file_is_never_overwritten(self):
        state_dir = os.path.join(os.environ["ROADMAP_HOME"], "state")
        os.makedirs(state_dir, exist_ok=True)
        path = os.path.join(state_dir, "hooks-demo.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{broken")
        self.agent_start()
        self.assertEqual(self.read_jobs(), [])
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{broken")
        self.assertIn("left unchanged", self.log_text())

    def test_run_hook_never_raises_even_when_the_log_cannot_be_written(self):
        blocker = os.path.join(self.tmp, "blocker")
        with open(blocker, "w", encoding="utf-8") as fh:
            fh.write("x")
        saved = os.environ["ROADMAP_HOME"]
        os.environ["ROADMAP_HOME"] = os.path.join(blocker, "home")
        self.addCleanup(os.environ.__setitem__, "ROADMAP_HOME", saved)
        hooks.run_hook("{bad")  # must not raise


class CommandTitleAndBusyLockTests(HookTestCase):
    def test_cursor_title_comes_from_the_invocation_in_a_chained_command(self):
        command = ("sed -n 1,3p src.sh > tools/cursor-review2.sh && chmod +x tools/cursor-review2.sh && "
                   '(nohup tools/cursor-review2.sh /tmp/o.md "Review P0.8 parser" &)')
        self.fire(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": command},
                  tool_response={"stdout": ""})
        job = self.read_jobs()[0]
        self.assertEqual(job["title"], "Cursor Auto: Review P0.8 parser")
        self.assertEqual(self.state_active()[0]["watch"], "/tmp/o.md")

    def test_agy_title_stops_at_a_shell_operator(self):
        result = os.path.join(self.tmp, "chain.result.md")
        command = 'node "/opt/agy-companion.mjs" task --prompt "Review P0.8 parser" && rm -rf /tmp/x ; echo done'
        self.fire(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": command},
                  tool_response={"stdout": "result file: " + result})
        self.assertEqual(self.read_jobs()[0]["title"], "agy task: Review P0.8 parser")

    def test_busy_project_lock_returns_quickly_and_registers_nothing(self):
        start = time.monotonic()
        with lock.locked(self.docs, timeout=1):
            self.agent_start()
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(self.read_jobs(), [])
        self.assertIsNone(self.state_active())


class PresenceStampTests(HookTestCase):
    """R7.1 T3: hook events stamp the project's presence, and a presence failure never changes a hook's result."""

    def hook_stamp(self):
        with open(presence.file_for(self.docs), encoding="utf-8") as fh:
            return json.load(fh)["hook"]

    def test_session_start_stamps_presence(self):
        self.fire(hook_event_name="SessionStart")
        self.assertEqual(presence.state(self.docs), presence.OPEN)

    def test_stop_event_stamps_presence(self):
        self.fire(hook_event_name="Stop")
        self.assertEqual(presence.state(self.docs), presence.OPEN)

    def test_pre_tool_use_stamps_presence_for_the_project_of_the_cwd(self):
        hooks.run_hook(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": self.project,
                                   "tool_input": {"command": "ls"}}))
        self.assertEqual(presence.state(self.docs), presence.OPEN)

    def test_repeated_events_write_the_stamp_at_most_once_per_throttle(self):
        self.fire(hook_event_name="Stop")
        first = self.hook_stamp()
        self.fire(hook_event_name="Stop")
        self.assertEqual(self.hook_stamp(), first)

    def test_a_failing_presence_write_does_not_change_the_hook_reply(self):
        with mock.patch.object(presence, "touch_hook", side_effect=RuntimeError("disk gone")):
            code, out, err = run_cli(["hook"], stdin_text=json.dumps({"hook_event_name": "Stop",
                                                                      "cwd": self.project}))
            reply = hooks.run_hook(json.dumps({"hook_event_name": "SessionStart", "cwd": self.project}))
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertIsNone(reply)


if __name__ == "__main__":
    unittest.main()
