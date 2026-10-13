"""Hook enforcement: the PreToolUse deny matrix, fail-open paths, the task mapping, SessionStart, the Stop pickup
caps, the installer with the new events, and the shim fast path (no Python while nothing is blocked)."""

import datetime
import itertools
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from roadmap.services import control, hooks, hooks_install, queue, questions
from tests.unit.test_control_support import ControlCase, read_json, write_json

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHIM = os.path.join(REPO, "bin", "roadmap")
MOMENT = datetime.datetime(2026, 10, 13, 14, 2, tzinfo=datetime.timezone.utc).astimezone()
TAIL = ". Run roadmap inbox, then end your turn."


class GateCase(ControlCase):
    def fire(self, tool="Edit", tool_input=None, now=None, clock=None, cwd=None, extra=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input or {},
                   "cwd": self.project if cwd is None else cwd}
        payload.update(extra or {})
        return hooks.run_hook(json.dumps(payload), now=(MOMENT.timestamp() if now is None else now), clock=clock)

    def deny_reason(self, reply):
        self.assertIsNotNone(reply)
        self.assertEqual(reply["hookSpecificOutput"]["permissionDecision"], "deny")
        return reply["hookSpecificOutput"]["permissionDecisionReason"]

    def log_text(self):
        path = os.path.join(os.environ["ROADMAP_HOME"], "logs", "hooks.log")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def write_hook_state(self, active):
        write_json(os.path.join(self.state_dir, "hooks-demo.json"), {"schemaVersion": 1, "project": "demo",
                                                                  "active": active})

    def write_jobs(self, jobs_list):
        write_json(os.path.join(self.docs, "jobs.json"), {"schemaVersion": 1, "jobs": jobs_list})


class DenyMatrixTests(GateCase):
    def test_stopped_project_denies_every_gated_tool(self):
        control.stop("demo", now=MOMENT)
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "Agent", "Task", "WebFetch", "WebSearch"):
            reason = self.deny_reason(self.fire(tool, {"command": "npm test"}))
            self.assertEqual(reason, "roadmap: stopped by user at " + MOMENT.strftime("%H:%M") + " (A1)" + TAIL)
            self.assertNotIn("\n", reason)

    def test_read_grep_and_glob_are_never_blocked(self):
        control.stop("demo", now=MOMENT)
        for tool in ("Read", "Grep", "Glob"):
            self.assertIsNone(self.fire(tool, {"file_path": "x"}))

    def test_roadmap_commands_pass_but_chained_ones_do_not(self):
        control.stop("demo", now=MOMENT)
        self.assertIsNone(self.fire("Bash", {"command": "roadmap status"}))
        self.assertIsNone(self.fire("Bash", {"command": "  roadmap inbox --json"}))
        self.deny_reason(self.fire("Bash", {"command": "npm test"}))
        self.deny_reason(self.fire("Bash", {"command": "roadmap status; rm -rf x"}))
        self.deny_reason(self.fire("Bash", {"command": "roadmap status && make"}))

    def test_resume_lets_the_same_calls_through(self):
        control.stop("demo", now=MOMENT)
        control.resume("demo", now=MOMENT)
        self.assertIsNone(self.fire("Edit"))

    def test_a_running_project_with_no_sentinel_is_not_read_at_all(self):
        write_json(os.path.join(self.state_dir, "control-demo.json"), ["garbage"])
        self.assertIsNone(self.fire("Edit"))

    def test_budget_block_names_the_limit_and_an_override_lets_it_through_until_it_expires(self):
        self.set_usage(120)
        control.recompute("demo", now=MOMENT)
        reason = self.deny_reason(self.fire("Edit"))
        self.assertEqual(reason, "roadmap: blocked: weekly usage 120% reached stopAtPercent 100%" + TAIL)
        control.override("demo", 1, now=MOMENT)
        self.assertIsNone(self.fire("Edit", now=MOMENT.timestamp() + 30 * 60))
        # two hours on, the usage reading is fresh again and still over the limit: the recompute denies once more
        later = MOMENT + datetime.timedelta(hours=2)
        self.set_usage(120, updated=later.isoformat())
        self.deny_reason(self.fire("Edit", now=later.timestamp()))

    def test_a_manual_stop_is_not_overridden(self):
        control.stop("demo", now=MOMENT)
        control.override("demo", 4, now=MOMENT)
        self.deny_reason(self.fire("Edit", now=MOMENT.timestamp() + 60))

    def test_task_stop_denies_only_the_subagent_running_that_task(self):
        control.stop("demo", task="P0.2", now=MOMENT)
        self.write_jobs([{"id": "j1", "title": "x", "model": "haiku", "task": "P0.2", "status": "running"},
                         {"id": "j2", "title": "y", "model": "haiku", "task": "P0.1", "status": "running"}])
        self.write_hook_state([{"job": "j1", "agent": "agent1234", "detector": "agent", "kind": "agent",
                                "watch": "", "started": 0},
                               {"job": "j2", "agent": "agent5678", "detector": "agent", "kind": "agent",
                                "watch": "", "started": 0}])
        reason = self.deny_reason(self.fire("Edit", extra={"agent_id": "agent1234"}))
        self.assertTrue(reason.startswith("roadmap: task P0.2 stopped by user at "))
        self.assertIsNone(self.fire("Edit", extra={"agent_id": "agent5678"}))
        self.assertIsNone(self.fire("Edit"))

    def test_denials_are_logged_at_most_once_a_minute(self):
        control.stop("demo", now=MOMENT)
        now = MOMENT.timestamp()
        self.fire("Edit", now=now)
        self.fire("Write", now=now + 10)
        self.assertEqual(self.log_text().count("denied demo"), 1)
        self.fire("Write", now=now + 61)
        self.assertEqual(self.log_text().count("denied demo"), 2)


class FailOpenTests(GateCase):
    def test_corrupt_control_file_lets_the_call_through(self):
        os.makedirs(self.state_dir, exist_ok=True)
        open(os.path.join(self.state_dir, "block-demo"), "w").close()
        with open(os.path.join(self.state_dir, "control-demo.json"), "w", encoding="utf-8") as fh:
            fh.write("{broken")
        self.assertIsNone(self.fire("Edit"))

    def test_unknown_project_lets_the_call_through(self):
        control.stop("demo", now=MOMENT)
        outside = tempfile.mkdtemp(prefix="rb-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        self._env("ROADMAP_PROJECT", None)
        self.assertIsNone(self.fire("Edit", cwd=outside))

    def test_an_exception_inside_the_gate_lets_the_call_through(self):
        control.stop("demo", now=MOMENT)
        with mock.patch("roadmap.services.control.read_state", side_effect=RuntimeError("boom")):
            self.assertIsNone(self.fire("Edit"))

    def test_a_slow_gate_lets_the_call_through(self):
        control.stop("demo", now=MOMENT)
        ticks = itertools.count(0, 0.2)  # every clock read is 0.2 s later: past the 300 ms cutoff at once
        self.assertIsNone(self.fire("Edit", clock=lambda: next(ticks)))

    def test_a_fast_gate_still_denies(self):
        control.stop("demo", now=MOMENT)
        ticks = itertools.count(0, 0.001)
        self.deny_reason(self.fire("Edit", clock=lambda: next(ticks)))

    def test_bad_json_on_stdin_is_silent(self):
        self.assertIsNone(hooks.run_hook("not json", now=MOMENT.timestamp()))
        self.assertIsNone(hooks.run_hook("[1]", now=MOMENT.timestamp()))


class SessionStartTests(GateCase):
    def start(self):
        return hooks.run_hook(json.dumps({"hook_event_name": "SessionStart", "cwd": self.project}),
                              now=MOMENT.timestamp())

    def test_at_most_three_inbox_lines_as_additional_context(self):
        queue.enqueue(self.docs, "P0.2", by="lead", now=MOMENT)
        queue.enqueue(self.docs, "P1.1", by="lead", now=MOMENT)
        questions.ask(self.docs, "P0.1", "Use plan A?", opts=["A", "B"], default="A", now=MOMENT)
        questions.ask(self.docs, "P0.1", "Second?", now=MOMENT)
        reply = self.start()
        context = reply["hookSpecificOutput"]["additionalContext"].split("\n")
        self.assertEqual(reply["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(len(context), 3)
        self.assertEqual(context[0], "queued: P0.2 (lead)")

    def test_a_stop_comes_first(self):
        control.stop("demo", now=MOMENT)
        context = self.start()["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(context.startswith("roadmap: stopped by user at "))

    def test_nothing_pending_is_silent(self):
        self.assertIsNone(self.start())


class StopPickupTests(GateCase):
    def stop_event(self, session="s1", active=False):
        return hooks.run_hook(json.dumps({"hook_event_name": "Stop", "cwd": self.project, "session_id": session,
                                          "stop_hook_active": active}), now=MOMENT.timestamp())

    def test_each_queued_request_is_surfaced_once_and_at_most_three_per_session(self):
        for task in ("P0.1", "P0.2", "P1.1"):
            queue.enqueue(self.docs, task, by="lead", now=MOMENT)
        first = self.stop_event()
        self.assertEqual(first["decision"], "block")
        self.assertIn("P0.1", first["reason"])
        self.assertEqual(self.stop_event()["reason"].count("P0.2"), 1)
        self.assertIn("P1.1", self.stop_event()["reason"])
        self.assertIsNone(self.stop_event())
        queue.dequeue(self.docs, "P0.1")
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT + datetime.timedelta(minutes=5))
        self.assertIsNone(self.stop_event())  # the session has had its three
        # the same queued task set has had its three blocks in total: a new session does not reset the count
        self.assertIsNone(self.stop_event(session="s2"))

    def test_stop_hook_active_never_blocks_again(self):
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        self.assertIsNone(self.stop_event(active=True))
        self.assertIsNone(self.stop_event(active="1"))  # any truthy value counts as already active

    def test_a_new_session_and_a_deleted_pickup_file_do_not_reset_the_count(self):
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        for i in range(3):
            self.assertEqual(self.stop_event(session="new%d" % i)["decision"], "block")
            queue.dequeue(self.docs, "P0.1")
            queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT + datetime.timedelta(minutes=i + 1))
            os.remove(os.path.join(self.state_dir, "pickup-demo.json"))
        self.assertIsNone(self.stop_event(session="fresh"))  # three blocks recorded: fail open

    def test_a_different_queued_task_set_gets_its_own_count(self):
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        for i in range(3):
            self.stop_event(session="x%d" % i)
            queue.dequeue(self.docs, "P0.1")
            queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT + datetime.timedelta(minutes=i + 1))
        queue.enqueue(self.docs, "P1.1", by="lead", now=MOMENT)
        self.assertEqual(self.stop_event(session="y")["decision"], "block")

    def test_pickup_off_in_the_project_config(self):
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        cfg = dict(read_json(os.path.join(self.docs, "roadmap.config.json")), pickupOnStop=False)
        write_json(os.path.join(self.docs, "roadmap.config.json"), cfg)
        self.assertIsNone(self.stop_event())

    def test_no_pickup_while_stopped(self):
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        control.stop("demo", now=MOMENT)
        self.assertIsNone(self.stop_event())


class InstallTests(GateCase):
    def bytes_of(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def test_install_adds_the_gate_and_session_start_and_is_idempotent(self):
        result = hooks_install.install("demo")
        self.assertTrue(result["changed"])
        settings = read_json(result["settings"])["hooks"]
        pre = settings["PreToolUse"][0]
        self.assertEqual(pre["matcher"], hooks_install.PRE_MATCHER)
        self.assertTrue(pre["hooks"][0]["command"].endswith(" hook pre"))
        self.assertTrue(settings["SessionStart"][0]["hooks"][0]["command"].endswith(" hook"))
        before = self.bytes_of(result["settings"])
        again = hooks_install.install("demo")
        self.assertFalse(again["changed"])
        self.assertEqual(self.bytes_of(result["settings"]), before)
        self.assertTrue(hooks_install.status("demo")["installed"])


class ShimTests(GateCase):
    def setUp(self):
        super().setUp()
        self.fakebin = os.path.join(self.tmp, "fakebin")
        os.makedirs(self.fakebin)
        self.marker = os.path.join(self.tmp, "python-started")
        fake = os.path.join(self.fakebin, "python3")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\ntouch '%s'\nexit 3\n" % self.marker)
        os.chmod(fake, 0o755)

    def run_shim(self, argv, stdin=""):
        env = {"PATH": self.fakebin + os.pathsep + "/usr/bin:/bin", "ROADMAP_HOME": os.environ["ROADMAP_HOME"],
               "HOME": os.environ["HOME"]}
        started = time.monotonic()
        proc = subprocess.run([SHIM] + argv, input=stdin, capture_output=True, text=True, env=env, timeout=30)
        return proc, time.monotonic() - started

    def test_without_a_sentinel_the_pre_gate_exits_0_without_python(self):
        proc, elapsed = self.run_shim(["hook", "pre"], '{"hook_event_name":"PreToolUse","tool_name":"Edit"}')
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))
        self.assertFalse(os.path.exists(self.marker))
        self.assertLess(elapsed, 1.0)

    def test_with_a_sentinel_the_pre_gate_runs_python(self):
        os.makedirs(self.state_dir, exist_ok=True)
        open(os.path.join(self.state_dir, "block-demo"), "w").close()
        proc, _ = self.run_shim(["hook", "pre"], "{}")
        self.assertTrue(os.path.exists(self.marker))
        self.assertEqual(proc.returncode, 3)

    def test_other_hook_events_always_run_python(self):
        proc, _ = self.run_shim(["hook"], "{}")
        self.assertTrue(os.path.exists(self.marker))

    def test_the_real_shim_runs_a_stopped_gate_end_to_end(self):
        control.stop("demo", now=MOMENT)
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": self.project})
        env = dict(os.environ)
        env.pop("CLAUDECODE", None)
        proc = subprocess.run([SHIM, "hook", "pre"], input=payload, capture_output=True, text=True, env=env,
                              timeout=60)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
