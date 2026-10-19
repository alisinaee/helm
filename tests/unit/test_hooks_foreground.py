"""R11.159: a foreground Agent call must not leave a ghost "running" job. Payload shapes are captured from Claude Code
transcripts: a foreground call returns status "completed" (after its SubagentStop), a background call returns
"async_launched" with outputFile. Jobs are matched by agentId, never by description."""

import json
import os
import unittest

from roadmap.services import hooks
from tests.unit.test_hooks import HookTestCase

NOW = 1_800_000_000.0
AGENT = "a457df42172b46499"
OTHER = "a763928565394741d"

COMPLETED = {"status": "completed", "agentId": AGENT, "agentType": "general-purpose", "content": [{"type": "text",
             "text": "done"}], "totalDurationMs": 41000, "totalTokens": 12000, "totalToolUseCount": 3,
             "usage": {"input_tokens": 10, "output_tokens": 20}, "prompt": "do it"}


def launched(agent_id, out):
    return {"status": "async_launched", "agentId": agent_id, "description": "P0.8 parser", "prompt": "go",
            "isAsync": True, "outputFile": out, "canReadOutputFile": True, "canContinueAgent": True}


class ForegroundTests(HookTestCase):
    def post(self, response, description="P0.8 parser", agent_id=AGENT, now=NOW, **extra):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Agent", "cwd": self.project,
                   "tool_input": {"description": description, "prompt": "go", "model": "haiku"},
                   "tool_response": dict(response, agentId=agent_id)}
        payload.update(extra)
        hooks.run_hook(json.dumps(payload), now=now)

    def stop(self, agent_id=AGENT, now=NOW):
        hooks.run_hook(json.dumps({"hook_event_name": "SubagentStop", "cwd": self.project, "agent_id": agent_id}),
                       now=now)

    def statuses(self):
        return {j["title"] + "|" + str(j.get("status")) for j in self.read_jobs()}

    def test_foreground_call_stop_first_then_post_closes_the_job_once(self):
        self.stop()  # SubagentStop arrives before the PostToolUse that registers the job
        self.post(COMPLETED)
        jobs_now = self.read_jobs()
        self.assertEqual([j["status"] for j in jobs_now], ["done"])
        self.assertEqual(self.state_active(), [])
        self.stop()  # a second stop for the same agent changes nothing
        self.assertEqual([j["status"] for j in self.read_jobs()], ["done"])

    def test_foreground_completed_response_alone_closes_the_job(self):
        self.post(COMPLETED)
        self.assertEqual([j["status"] for j in self.read_jobs()], ["done"])
        self.assertEqual(self.state_active(), [])

    def test_background_launch_stays_running_until_its_stop(self):
        self.post(launched(AGENT, "/nonexistent/agent.output"))
        self.assertEqual([j["status"] for j in self.read_jobs()], ["running"])
        self.assertEqual(self.state_active()[0]["watch"], "/nonexistent/agent.output")
        self.stop()
        self.assertEqual([j["status"] for j in self.read_jobs()], ["done"])
        self.assertEqual(self.state_active(), [])
        self.stop()
        self.assertEqual([j["status"] for j in self.read_jobs()], ["done"])

    def test_the_stop_matches_by_agent_id_not_by_description(self):
        self.post(launched(AGENT, "/nonexistent/a.output"), description="P0.8 same text", agent_id=AGENT)
        self.post(launched(OTHER, "/nonexistent/b.output"), description="P0.8 same text", agent_id=OTHER)
        self.stop(OTHER)
        by_agent = {e["agent"]: e["job"] for e in self.state_active()}
        self.assertEqual(list(by_agent), [AGENT])
        self.assertEqual(sorted(j["status"] for j in self.read_jobs()), ["done", "running"])

    def test_send_message_resume_of_a_finished_agent_is_closed_by_its_stop(self):
        self.post(COMPLETED)  # the first run, foreground: done
        hooks.run_hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "SendMessage", "cwd": self.project,
                                   "tool_input": {"to": AGENT, "message": "more"}, "tool_response": {}}), now=NOW + 5)
        self.assertEqual(sorted(j["status"] for j in self.read_jobs()), ["done", "running"])
        self.stop(AGENT, now=NOW + 20)
        self.assertEqual([j["status"] for j in self.read_jobs()], ["done", "done"])
        self.assertEqual(self.state_active(), [])

    def test_send_message_whose_stop_came_first_is_closed_at_once(self):
        self.post(COMPLETED)
        self.stop(AGENT, now=NOW + 10)  # the resumed run ended before the SendMessage call returned
        hooks.run_hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "SendMessage", "cwd": self.project,
                                   "tool_input": {"to": AGENT, "message": "more"}, "tool_response": {}}), now=NOW + 12)
        self.assertEqual([j["status"] for j in self.read_jobs()], ["done", "done"])

    def test_a_quiet_agent_job_is_swept_as_stale_not_done(self):
        session = os.path.join(self.project, "session.jsonl")
        sub = os.path.join(self.project, "session", "subagents")
        os.makedirs(sub)
        transcript = os.path.join(sub, "agent-" + AGENT + ".jsonl")
        with open(transcript, "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        os.utime(transcript, (NOW, NOW))
        self.post(launched(AGENT, "/nonexistent/a.output"), transcript_path=session)
        self.assertEqual(self.state_active()[0]["transcript"], transcript)
        later = NOW + hooks.AGENT_STALE_S + 60
        hooks.run_hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": self.project,
                                   "tool_input": {"command": "ls"}, "tool_response": {"stdout": ""}}), now=later)
        job = self.read_jobs()[0]
        self.assertEqual(job["status"], "failed")
        self.assertTrue(job["reason"].startswith("stale:"))
        self.assertEqual(self.state_active(), [])

    def test_an_active_agent_job_is_not_swept(self):
        session = os.path.join(self.project, "session.jsonl")
        sub = os.path.join(self.project, "session", "subagents")
        os.makedirs(sub)
        transcript = os.path.join(sub, "agent-" + AGENT + ".jsonl")
        with open(transcript, "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        os.utime(transcript, (NOW + 500, NOW + 500))
        self.post(launched(AGENT, "/nonexistent/a.output"), transcript_path=session)
        hooks.run_hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": self.project,
                                   "tool_input": {"command": "ls"}, "tool_response": {"stdout": ""}}),
                       now=NOW + 500 + 60)
        self.assertEqual([j["status"] for j in self.read_jobs()], ["running"])


if __name__ == "__main__":
    unittest.main()
