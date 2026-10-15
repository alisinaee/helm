"""Job history (R7.60): the paged read of the finished jobs (newest first, running jobs left out), the person-only
job.remove op with its Undo, and the refusals: an agent or the phone may not remove, and a running or unknown job
changes nothing. The paged route GET .../jobs is checked for its query rules and its reply shape.

Every test runs in a temp ROADMAP_HOME with the demo project (test_cmd_support). Nothing touches the real home.
"""

import json
import os
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.http import routes
from roadmap.services import agentguard, commands, jobs
from tests.unit.test_cmd_support import CmdCase


def job(jid, status, ended, **extra):
    row = {"id": jid, "title": "job " + jid, "model": "haiku", "status": status,
           "started": "2026-10-13T09:00:00Z", "ended": ended, "tokensK": 1}
    row.update(extra)
    return row


class HistoryCase(CmdCase):
    def write_jobs(self, rows):
        with open(os.path.join(self.data, "jobs.json"), "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 1, "jobs": rows}, fh)

    def job_ids(self):
        return [j["id"] for j in self.read_json("jobs.json")["jobs"]]

    def sample(self):
        self.write_jobs([job("j1", "done", "2026-10-13T09:01:00Z"),
                         job("j2", "failed", "2026-10-13T09:05:00Z"),
                         job("j3", "running", None),
                         job("j4", "done", "2026-10-13T09:03:00Z")])


class FinishedPageTests(HistoryCase):
    def test_finished_jobs_are_newest_first_and_running_ones_are_left_out(self):
        self.sample()
        rows, total = jobs.finished_page(self.data, 0, 10)
        self.assertEqual([r["id"] for r in rows], ["j2", "j4", "j1"])
        self.assertEqual(total, 3)

    def test_a_page_counts_from_its_offset(self):
        self.sample()
        rows, total = jobs.finished_page(self.data, 1, 1)
        self.assertEqual([r["id"] for r in rows], ["j4"])
        self.assertEqual(total, 3)

    def test_reading_the_history_writes_nothing(self):
        self.sample()
        before = self.read_json("jobs.json")
        jobs.finished_page(self.data, 0, 10)
        self.assertEqual(self.read_json("jobs.json"), before)


class RemoveJobsTests(HistoryCase):
    def test_only_the_listed_finished_jobs_are_removed(self):
        self.sample()
        removed = jobs.remove_jobs(self.data, ["j1"])
        self.assertEqual([r["id"] for r in removed], ["j1"])
        self.assertEqual(self.job_ids(), ["j2", "j3", "j4"])

    def test_a_running_or_unknown_id_removes_nothing(self):
        self.sample()
        with self.assertRaises(RoadmapError) as running:
            jobs.remove_jobs(self.data, ["j1", "j3"])
        self.assertEqual(running.exception.code, "conflict")
        with self.assertRaises(RoadmapError) as unknown:
            jobs.remove_jobs(self.data, ["j1", "j9"])
        self.assertEqual(unknown.exception.code, "not_found")
        self.assertEqual(self.job_ids(), ["j1", "j2", "j3", "j4"])

    def test_restore_puts_the_records_back_once(self):
        self.sample()
        removed = jobs.remove_jobs(self.data, ["j1"])
        self.assertEqual(jobs.restore_jobs(self.data, removed), 1)
        self.assertEqual(jobs.restore_jobs(self.data, removed), 0)
        self.assertEqual(sorted(self.job_ids()), ["j1", "j2", "j3", "j4"])


class JobRemoveOpTests(HistoryCase):
    def test_job_remove_is_a_public_op_and_its_inverse_is_not(self):
        public = commands.public_ops()
        self.assertIn("job.remove", public)
        self.assertNotIn("job.restore", public)

    def test_an_agent_or_the_phone_is_refused_and_nothing_changes(self):
        self.sample()
        for source in ("agent", "phone"):
            with self.assertRaises(RoadmapError) as refused:
                commands.run("job.remove", {"ids": ["j1"]}, source, self.data)
            self.assertEqual(refused.exception.code, "agent_refused")
        self.assertEqual(self.job_ids(), ["j1", "j2", "j3", "j4"])

    def test_bad_ids_are_refused_before_any_write(self):
        self.sample()
        for args in ({"ids": []}, {"ids": "j1"}, {"ids": ["x1"]}, {"ids": ["j1"] * 201}):
            with self.assertRaises(RoadmapError) as bad:
                commands.run("job.remove", args, "gui", self.data)
            self.assertEqual(bad.exception.code, "usage")
        self.assertEqual(self.job_ids(), ["j1", "j2", "j3", "j4"])

    def test_remove_by_the_person_can_be_undone(self):
        self.sample()
        # The person's browser call: a gui call with a browser proof on this thread, not an agent's shell.
        with mock.patch.object(agentguard, "gui_proven", return_value=True), \
                mock.patch.dict(os.environ, {agentguard.ENV: ""}):
            reply = commands.run("job.remove", {"ids": ["j1", "j2", "j1"]}, "gui", self.data)
            self.assertTrue(reply["undo"])
            self.assertEqual(reply["data"]["removed"], ["j1", "j2"])
            self.assertEqual(self.job_ids(), ["j3", "j4"])
            commands.run("undo", {"activity": reply["activity"]}, "gui", self.data)
        self.assertEqual(sorted(self.job_ids()), ["j1", "j2", "j3", "j4"])


class JobsRouteTests(HistoryCase):
    def fetch(self, query):
        match = mock.Mock()
        match.group.return_value = "demo"
        req = mock.Mock(query=query)
        with mock.patch.object(routes, "_cmd_project", return_value="demo"), \
                mock.patch.object(routes.task_service, "resolve", return_value=(None, self.data)):
            return routes.project_jobs(None, req, match)

    def test_the_page_query_has_bounds_and_defaults(self):
        self.assertEqual(routes._jobs_page_query(""), (0, 10))
        self.assertEqual(routes._jobs_page_query("offset=2&limit=5"), (2, 5))
        for query in ("limit=0", "limit=201", "offset=-1", "sort=x", "limit=5&limit=6"):
            with self.assertRaises(RoadmapError) as bad:
                routes._jobs_page_query(query)
            self.assertEqual(bad.exception.code, "invalid_input", query)

    def test_the_route_reads_one_page_newest_first(self):
        self.sample()
        reply = self.fetch("offset=0&limit=2")
        body = json.loads(reply.body.decode("utf-8"))
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["offset"], 0)
        self.assertEqual([r["id"] for r in body["rows"]], ["j2", "j4"])
        self.assertEqual(body["rows"][0]["elapsed_s"], 300.0)
        self.assertEqual(self.job_ids(), ["j1", "j2", "j3", "j4"])
