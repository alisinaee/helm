"""The WP23 registry ops (roadmap/services/cmdops.py) run through commands.run: source rules (gui skips the agent
guard, cli and agent keep it, phone never runs a loosening op), one activity line per op, undo, and the budget fed
once from task tokens."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import agentguard, budget, commands, limits_v2, tasks
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID


class OpsCase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-ops-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def run_op(self, op, args=None, source="gui", agent=False):
        saved = os.environ.get("CLAUDECODE")
        if agent:
            os.environ["CLAUDECODE"] = "1"
        try:
            with commands.context(source, PROJECT_ID):
                return commands.run(op, args or {}, source, self.data_dir)
        finally:
            if saved is None:
                os.environ.pop("CLAUDECODE", None)
            else:
                os.environ["CLAUDECODE"] = saved

    def activity(self):
        return commands.activity.recent(self.data_dir, 100)


class SourceRules(OpsCase):
    def test_gui_loosening_op_runs_inside_an_agent_shell_when_the_browser_is_proven(self):
        os.environ["CLAUDECODE"] = "1"
        with agentguard.browser_proven(True):
            reply = self.run_op("control.stop", {}, source="gui")
        self.assertTrue(reply["ok"])
        self.assertEqual(os.environ.get("CLAUDECODE"), "1")  # the environment is never changed

    def test_gui_loosening_op_is_refused_inside_an_agent_shell_without_a_browser_proof(self):
        os.environ["CLAUDECODE"] = "1"
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("control.resume", {}, source="gui")
        self.assertEqual(ctx.exception.code, "agent_refused")

    def test_cli_resume_is_refused_inside_an_agent_shell(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("control.resume", {}, source="cli", agent=True)
        self.assertEqual(ctx.exception.code, "agent_refused")

    def test_phone_may_not_run_loosening_ops(self):
        for op, args in (("control.resume", {}), ("limit.set", {"pct": 40}),
                         ("budget.set", {"scope": "project", "value": 9}), ("rules.rm", {"id": "R1"})):
            with self.assertRaises(RoadmapError) as ctx:
                self.run_op(op, args, source="phone")
            self.assertEqual(ctx.exception.code, "forbidden", op)

    def test_phone_stop_is_allowed(self):
        self.assertTrue(self.run_op("control.stop", {}, source="phone")["ok"])


class ActivityAndUndo(OpsCase):
    def test_a_control_op_writes_one_activity_line_not_two(self):
        before = len(self.activity())
        reply = self.run_op("control.stop", {})
        lines = self.activity()
        self.assertEqual(len(lines), before + 1)
        self.assertEqual(lines[-1]["id"], reply["activity"])
        self.assertEqual(lines[-1]["op"], "control.stop")
        self.assertTrue(reply["undo"])

    def test_undo_of_control_stop_resumes(self):
        stop = self.run_op("control.stop", {})
        self.run_op("undo", {"activity": stop["activity"]})
        from roadmap.services import control
        self.assertFalse(control.read_state(PROJECT_ID).get("stop"))

    def test_budget_set_undo_restores_the_prior_limit(self):
        self.run_op("budget.set", {"scope": "project", "value": 50})
        second = self.run_op("budget.set", {"scope": "project", "value": 80})
        self.assertEqual(budget.get(self.data_dir)["limits"]["project"], 80)
        self.run_op("undo", {"activity": second["activity"]})
        self.assertEqual(budget.get(self.data_dir)["limits"]["project"], 50)

    def test_limit_set_undo_restores_the_prior_weekly_percent(self):
        self.run_op("limit.set", {"pct": 40})
        second = self.run_op("limit.set", {"pct": 60})
        self.assertTrue(second["undo"])
        self.run_op("undo", {"activity": second["activity"]})
        import json
        with open(os.path.join(self.data_dir, "autonomy.json"), encoding="utf-8") as fh:
            self.assertNotIn("stopAtPercent", json.load(fh)["limit"])
        self.assertEqual(limits_v2.load()["week"]["value"], 40)

    def test_rules_add_then_undo_removes_the_rule(self):
        added = self.run_op("rules.add", {"scope": "all", "kind": "do", "text": "run tests first"})
        rule_id = added["data"]["id"]
        self.assertTrue(added["undo"])
        self.run_op("undo", {"activity": added["activity"]})
        from roadmap.services import rules
        self.assertNotIn(rule_id, [r["id"] for r in rules.read(self.data_dir)[1]])


class BudgetFedOnce(OpsCase):
    def test_task_status_tokens_feed_the_budget_exactly_once(self):
        first = self.run_op("task.status", {"id": "P1.1", "status": "done", "tokensK": 18})
        second = self.run_op("task.status", {"id": "P1.1", "status": "done", "tokensK": 18})
        self.assertTrue(first["data"]["budgetFed"])
        self.assertFalse(second["data"]["budgetFed"])
        spent = budget.get(self.data_dir)["spent"]["P1.1"]
        self.assertEqual(sum(spent.values()), 18.0)
        self.assertEqual(tasks.get(self.data_dir, "P1.1")["status"], "done")

    def test_task_status_undo_restores_status_and_note(self):
        before = tasks.get(self.data_dir, "P1.1")
        reply = self.run_op("task.status", {"id": "P1.1", "status": "done", "note": "shipped"})
        self.run_op("undo", {"activity": reply["activity"]})
        after = tasks.get(self.data_dir, "P1.1")
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after.get("note") or "", before.get("note") or "")

    def test_non_whole_tokens_are_refused_by_the_registry(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("task.status", {"id": "P1.1", "status": "done", "tokensK": 2.5})
        self.assertEqual(ctx.exception.code, "usage")


class CheckErrors(OpsCase):
    def test_bad_budget_scope_is_a_usage_error(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("budget.set", {"scope": "galaxy", "value": 3})
        self.assertEqual(ctx.exception.code, "usage")

    def test_bad_limit_pct_is_a_usage_error(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("limit.set", {"pct": 0})
        self.assertEqual(ctx.exception.code, "usage")


if __name__ == "__main__":
    unittest.main()
