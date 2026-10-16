"""R10.10 C5: running and claimed jobs are always visible.

A claimed job (picked by the supervisor, not yet run) counts as in flight: it shows in agents.running, in the phase
running list, in the head link state of its task, and in the status running line. A job that is queued or done does
not. roadmap status names every running or claimed job id: the run: lines cover running jobs, and the running line
covers the claimed ones.
"""

import json
import unittest
from datetime import datetime, timezone

from roadmap.commands.status import running_line
from roadmap.core.snapshot import build_snapshot, head_link_state

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def task(tid, phase, status):
    return {"id": tid, "phase": phase, "title": tid, "status": status, "tokensK": 10.0, "model": "haiku",
            "check": "sonnet", "checkK": 0, "needsUser": False}


def job(jid, status, tid="P1.1", started="2026-10-15T11:50:00+00:00"):
    return {"id": jid, "title": jid, "model": "haiku", "task": tid, "status": status, "started": started,
            "ended": None, "tokensK": 1.0}


def build(jobs):
    tasks = json.dumps({"updated": "2026-10-15", "phases": [{"id": "P1", "name": "Core", "status": "todo"}],
                        "tasks": [task("P1.1", "P1", "todo")]})
    files = {"tasks.json": tasks, "jobs.json": json.dumps({"jobs": jobs})}
    return build_snapshot(files, {}, NOW)


class SnapshotRunningTests(unittest.TestCase):
    def setUp(self):
        self.snap = build([job("j1", "running"), job("j2", "claimed"), job("j3", "queued"),
                           job("j4", "done")])

    def test_claimed_job_is_in_agents_running(self):
        ids = [row["id"] for row in self.snap["agents"]["running"]]
        self.assertEqual(ids, ["j1", "j2"])

    def test_claimed_job_keeps_its_status_and_elapsed_time(self):
        rows = {row["id"]: row for row in self.snap["agents"]["running"]}
        self.assertEqual(rows["j2"]["elapsed_s"], 600.0)
        self.assertEqual(self.snap["summary"]["running_count"], 2)

    def test_claimed_job_counts_in_its_phase_running_list(self):
        phase = {p["id"]: p for p in self.snap["phases"]}["P1"]
        self.assertEqual(phase["running"], ["j1", "j2"])

    def test_claimed_job_makes_its_task_read_as_running(self):
        state = head_link_state([{"id": "P1.1", "state": "todo"}], [job("j2", "claimed")])
        self.assertEqual(state["task:P1.1"], "running")
        self.assertEqual(state["job:j2"], "running")

    def test_queued_and_done_jobs_are_not_running(self):
        ids = [row["id"] for row in self.snap["agents"]["running"]]
        self.assertNotIn("j3", ids)
        self.assertNotIn("j4", ids)

    def test_running_line_lists_every_running_or_claimed_id(self):
        jobs = [job("j1", "running"), job("j2", "claimed"), job("j3", "queued"), job("j4", "done")]
        self.assertEqual(running_line(jobs), "running 2: j1,j2")

    def test_running_line_is_none_for_one_or_two_running_jobs(self):
        self.assertIsNone(running_line([job("j1", "running"), job("j2", "running")]))

    def test_running_line_shows_a_lone_claimed_job(self):
        self.assertEqual(running_line([job("j2", "claimed")]), "running 1: j2")

    def test_running_line_is_none_when_nothing_is_in_flight(self):
        self.assertIsNone(running_line([job("j3", "queued"), job("j4", "done")]))


if __name__ == "__main__":
    unittest.main()
