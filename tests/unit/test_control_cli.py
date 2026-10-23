"""The CLI of WP22: stop, resume, override, limit, phase and rules, with their exit codes, JSON and agent refusals."""

import json
import os
from unittest import mock

from roadmap.services import control, limits_v2
from tests.unit.test_control_support import ControlCase, read_json
from tests.unit.test_jobs_support import run_cli

AGENT = {"CLAUDECODE": "1"}


class ControlCliTests(ControlCase):
    def envelope(self, argv):
        code, out, err = run_cli(argv + ["--json"])
        return code, json.loads(out) if out.strip() else None, err

    def test_stop_task_and_resume_with_json(self):
        code, body, _ = self.envelope(["stop", "--task", "P0.2"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["stopTasks"], ["P0.2"])
        self.assertFalse(body["data"]["stop"])
        code, body, _ = self.envelope(["resume"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["stopTasks"], [])

    def test_plain_stop_prints_one_line_and_resume_is_refused_from_an_agent(self):
        code, out, _ = run_cli(["stop"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("stopped by user at "))
        with mock.patch.dict(os.environ, AGENT):
            code, out, err = run_cli(["resume"])
        self.assertEqual(code, 4)
        self.assertIn('next: roadmap ask "<question>"', err)
        self.assertTrue(self.sentinel_exists())

    def test_override_hours_out_of_range_is_a_usage_error(self):
        code, _, err = run_cli(["override", "--hours", "9"])
        self.assertEqual(code, 2)
        code, body, _ = self.envelope(["override", "--hours", "2"])
        self.assertEqual(code, 0)
        self.assertIsNotNone(body["data"]["overrideUntil"])

    def test_limit_set_and_budget_commands(self):
        code, out, _ = run_cli(["limit", "set", "90"])
        self.assertEqual((code, out.strip()), (0, "weekly stop at 90%"))
        self.assertNotIn("stopAtPercent", read_json(os.path.join(self.docs, "autonomy.json"))["limit"])
        self.assertEqual(limits_v2.load()["week"]["value"], 90)
        code, body, _ = self.envelope(["limit", "budget", "task", "P0.2", "40"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["limit"], "task P0.2")
        self.assertEqual(read_json(os.path.join(self.docs, "budget.json"))["limits"]["tasks"], {"P0.2": 40.0})
        code, _, err = run_cli(["limit", "budget", "phase", "P0", "x"])
        self.assertEqual(code, 2)
        code, _, err = run_cli(["limit", "budget", "team", "P0", "3"])
        self.assertEqual(code, 2)

    def test_agent_cannot_raise_a_budget_or_set_the_weekly_limit(self):
        run_cli(["limit", "budget", "project", "100"])
        with mock.patch.dict(os.environ, AGENT):
            code, _, err = run_cli(["limit", "budget", "project", "200"])
            self.assertEqual(code, 4)
            code, _, _ = run_cli(["limit", "set", "50"])
            self.assertEqual(code, 4)
            code, _, _ = run_cli(["limit", "budget", "project", "40"])
            self.assertEqual(code, 0)

    def test_phase_approve_once(self):
        code, body, _ = self.envelope(["phase", "approve", "P1"])
        self.assertEqual(code, 0)
        self.assertTrue(body["data"]["changed"])
        code, out, _ = run_cli(["phase", "approve", "P1"])
        self.assertIn("already approved", out)
        code, _, err = run_cli(["phase", "approve", "P9"])
        self.assertEqual(code, 3)

    def test_hook_command_prints_the_deny_reply_on_stdin(self):
        run_cli(["stop"])
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": self.project})
        code, out, _ = run_cli(["hook", "pre"], stdin_text=payload)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        code, out, _ = run_cli(["hook"], stdin_text=json.dumps({"hook_event_name": "PostToolUse"}))
        self.assertEqual((code, out), (0, ""))

    def test_control_summary_is_available_for_status(self):
        run_cli(["stop", "--task", "P0.1"])
        self.assertEqual(control.summary_line("demo"), "running (stopped tasks: P0.1)")


class RulesCliTests(ControlCase):
    def test_add_show_check_and_sync_from_the_shell(self):
        code, out, _ = run_cli(["rules", "add", "haiku", "budget", "Stop at 60k on one task", "--budget", "60"])
        self.assertEqual((code, out.strip()), (0, "R1 haiku budget 60 | Stop at 60k on one task"))
        run_cli(["rules", "add", "all", "do", "Run the tests before a commit"])
        code, out, _ = run_cli(["rules", "show", "--for", "P0.1", "--model", "haiku", "--role", "worker"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["R1 haiku budget 60 | Stop at 60k on one task",
                                            "R2 all do | Run the tests before a commit"])
        code, out, _ = run_cli(["rules", "check"])
        self.assertEqual(out.strip(), "ok: 2 rules")
        code, out, _ = run_cli(["rules", "sync", "--dry-run"])
        self.assertEqual(out.strip(), "+1 ~0 -0 (dry run)")

    def test_budget_rule_needs_a_number_and_show_says_when_nothing_applies(self):
        code, _, _ = run_cli(["rules", "add", "all", "budget", "No number"])
        self.assertEqual(code, 2)
        code, out, _ = run_cli(["rules", "show"])
        self.assertEqual(out.strip(), "no rules apply")

    def test_rules_writes_are_refused_from_an_agent_and_rm_is_a_write(self):
        run_cli(["rules", "add", "all", "do", "One"])
        with mock.patch.dict(os.environ, AGENT):
            code, _, err = run_cli(["rules", "add", "all", "do", "Two"])
            self.assertEqual(code, 4)
            code, _, _ = run_cli(["rules", "rm", "R1"])
            self.assertEqual(code, 4)
            code, _, _ = run_cli(["rules", "sync"])
            self.assertEqual(code, 4)
            code, out, _ = run_cli(["rules", "show"])
            self.assertEqual(code, 0)
        code, out, _ = run_cli(["rules", "rm", "R1"])
        self.assertEqual(out.strip(), "removed R1")
