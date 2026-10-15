"""Tests for R7.89: a SendMessage follow-up to a known subagent is a job bound to that agent's task, the agents
map keeps the newest 200 agents, and the Stop gate names the idle state first when no job runs and tasks wait."""

import json
import os
import time
import unittest

from roadmap.services import hooks, jobs
from tests.unit.test_jobs_support import FixtureCase, write_json

AGENT = "a1b2c3d4e5"


class FollowupCase(FixtureCase):
    def setUp(self):
        super().setUp()
        path = os.path.join(self.docs, "roadmap.config.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["headCapture"] = True
        write_json(path, data)

    def fire(self, now=None, **payload):
        payload.setdefault("cwd", self.project)
        return hooks.run_hook(json.dumps(payload), now=now)

    def start_agent(self, task_text="Parser fix P0.8", agent_id=AGENT, model="sonnet", now=None):
        self.fire(now=now, hook_event_name="PostToolUse", tool_name="Agent",
                  tool_input={"description": task_text, "prompt": "do it", "model": model},
                  tool_response={"agentId": agent_id, "output_file": "/nonexistent/out.output"})

    def send(self, to, now=None):
        self.fire(now=now, hook_event_name="PostToolUse", tool_name="SendMessage",
                  tool_input={"to": to, "message": "more"}, tool_response={"success": True})

    def jobs_now(self):
        return jobs.list_jobs(self.docs)

    def agents_map(self):
        with open(os.path.join(self.docs, "agents-map.json"), encoding="utf-8") as fh:
            return json.load(fh)


class FollowupJobTests(FollowupCase):
    def test_agent_start_is_stored_in_agents_map(self):
        self.start_agent()
        info = self.agents_map()[AGENT]
        self.assertEqual(info["task"], "P0.8")
        self.assertEqual(info["model"], "sonnet")
        self.assertIn("P0.8", info["title"])

    def test_send_message_to_known_agent_starts_bound_follow_up(self):
        self.start_agent()
        self.send(AGENT)
        last = self.jobs_now()[-1]
        self.assertEqual(last["title"], "sonnet: P0.8 follow-up")
        self.assertEqual(last["task"], "P0.8")
        self.assertEqual(last["status"], "running")

    def test_send_message_to_unknown_target_starts_nothing(self):
        self.start_agent()
        self.send("zzzzzzzzzz")
        self.assertEqual(len(self.jobs_now()), 1)

    def test_subagent_stop_closes_the_follow_up(self):
        self.start_agent()
        self.send(AGENT)
        self.fire(hook_event_name="SubagentStop", agent_id=AGENT)
        self.assertEqual([j["status"] for j in self.jobs_now()], ["done", "done"])

    def test_follow_up_without_subagent_stop_is_done_after_thirty_minutes(self):
        start = time.time()
        self.start_agent(now=start)
        self.send(AGENT, now=start)
        self.fire(now=start + hooks.FOLLOWUP_MAX_S - 60, hook_event_name="PostToolUse", tool_name="Bash",
                  tool_input={"command": "ls"}, tool_response={})
        self.assertEqual(self.jobs_now()[-1]["status"], "running")
        self.fire(now=start + hooks.FOLLOWUP_MAX_S + 1, hook_event_name="PostToolUse", tool_name="Bash",
                  tool_input={"command": "ls"}, tool_response={})
        self.assertEqual(self.jobs_now()[-1]["status"], "done")

    def test_agents_map_keeps_the_newest_200(self):
        for n in range(205):
            hooks._remember_agent(self.docs, {"agent": "agent%03d" % n, "task": "P0.8", "title": "t",
                                              "model": "sonnet"})
        mapping = self.agents_map()
        self.assertEqual(len(mapping), hooks.AGENTS_MAP_MAX)
        self.assertNotIn("agent000", mapping)
        self.assertIn("agent204", mapping)


class IdleGateTests(FollowupCase):
    def stop(self):
        result = self.fire(hook_event_name="Stop", stop_hook_active=False)
        return (result or {}).get("reason", "")

    def test_idle_alert_comes_first_when_nothing_runs(self):
        reason = self.stop()
        self.assertTrue(reason.startswith("idle: 0 running, 2 free tasks; launch now: P0.8, WP4."), reason)

    def test_no_idle_alert_while_a_job_runs(self):
        jobs.start_job(self.docs, "sonnet: P0.8", "sonnet", "P0.8")
        self.assertNotIn("idle:", self.stop())


if __name__ == "__main__":
    unittest.main()
