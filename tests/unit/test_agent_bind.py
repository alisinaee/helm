"""Tests for A5: an Agent or Task job is always registered and bound to a task.

Order: the description, then the prompt, then the task of the newest running head job started in the last hour,
then AGENT_FALLBACK_TASK (with a warning in hooks.log). A job is never dropped for lack of a task id.
"""

import json
import os
import time
import unittest

from roadmap.services import hooks, jobs
from tests.unit.test_jobs_support import FixtureCase, TASKS, write_json

EXTRA_TASKS = [{"id": "R7.31", "phase": "R7", "title": "Head", "status": "todo"},
               {"id": "R7.40", "phase": "R7", "title": "Agent bind", "status": "todo"}]


class AgentBindTests(FixtureCase):
    def setUp(self):
        super().setUp()
        self.set_tasks(TASKS["tasks"] + EXTRA_TASKS)

    def set_tasks(self, tasks):
        write_json(os.path.join(self.docs, "tasks.json"), {"schemaVersion": 1, "tasks": tasks})

    def agent(self, description, prompt="do it", now=None, agent_id="a1b2c3d4e5"):
        payload = {"cwd": self.project, "hook_event_name": "PostToolUse", "tool_name": "Agent",
                   "tool_input": {"description": description, "prompt": prompt, "model": "sonnet"},
                   "tool_response": {"agentId": agent_id, "output_file": "/nonexistent/out.output"}}
        hooks.run_hook(json.dumps(payload), now=now)

    def head_job(self, task):
        return jobs.start_job(self.docs, "head: " + task, "head", task=task)

    def test_task_id_in_prompt_binds_the_job(self):
        self.agent("Opus review", prompt="Review R7.40 now")
        job = self.read_jobs()[0]
        self.assertEqual(job["task"], "R7.40")
        self.assertEqual(job["status"], "running")

    def test_description_id_wins_over_prompt(self):
        self.agent("Parser fix P0.8", prompt="also R7.40")
        self.assertEqual(self.read_jobs()[0]["task"], "P0.8")

    def test_no_id_binds_to_newest_running_head_job_in_the_hour(self):
        self.head_job("WP4")
        self.head_job("P0.8")  # the newest head job
        self.agent("Opus review", prompt="no id here")
        self.assertEqual(self.read_jobs()[-1]["task"], "P0.8")
        self.assertNotIn("warning", self.log_text())

    def test_head_job_older_than_an_hour_is_ignored(self):
        self.head_job("WP4")
        self.agent("Opus review", prompt="no id here", now=time.time() + 7200)
        self.assertEqual(self.read_jobs()[-1]["task"], "R7.31")
        self.assertIn("warning: agent job names no task; bound to fallback R7.31", self.log_text())

    def test_no_id_and_no_head_job_binds_to_fallback_with_warning(self):
        self.agent("Opus review", prompt="no id here")
        job = self.read_jobs()[0]
        self.assertEqual(job["task"], "R7.31")
        self.assertIn("warning: agent job names no task", self.log_text())

    def test_job_is_registered_even_when_fallback_task_is_missing(self):
        self.set_tasks(TASKS["tasks"])  # no R7.31 in tasks.json
        self.agent("Opus review", prompt="no id here")
        jobs_now = self.read_jobs()
        self.assertEqual(len(jobs_now), 1)
        self.assertNotIn("task", jobs_now[0])
        self.assertEqual(jobs_now[0]["status"], "running")

    def test_agent_adopts_manual_job_of_same_task(self):  # R11.144
        manual = jobs.start_job(self.docs, "R7.40: worker", "sonnet", task="R7.40", effort="low")
        self.agent("R7.40: worker", agent_id="a1b2c3d4e6")
        rows = self.read_jobs()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], manual["id"])
        hooks.run_hook(json.dumps({"cwd": self.project, "hook_event_name": "SubagentStop", "agent_id": "a1b2c3d4e6"}))
        self.assertEqual(self.read_jobs()[0]["status"], "done")

    def test_head_job_is_not_adopted(self):
        self.head_job("R7.40")
        self.agent("R7.40: worker")
        self.assertEqual(len(self.read_jobs()), 2)

    def test_stop_surfaces_orphan_manual_job(self):
        jobs.start_job(self.docs, "R7.40: never sent", "sonnet", task="R7.40")
        stop = {"cwd": self.project, "hook_event_name": "Stop", "session_id": "s1"}
        self.assertIsNone(hooks.run_hook(json.dumps(stop)))  # fresh: not yet an orphan
        reply = hooks.run_hook(json.dumps(stop), now=time.time() + 900)
        self.assertEqual(reply["decision"], "block")
        self.assertIn("no agent behind them", reply["reason"])
        self.assertIsNone(hooks.run_hook(json.dumps(dict(stop, stop_hook_active=True)), now=time.time() + 900))


if __name__ == "__main__":
    unittest.main()
