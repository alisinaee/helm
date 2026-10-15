"""R7.40 (server half): the ETag of GET /api/v1/projects and of the project snapshot.

Checks: GET projects sends an ETag and answers 304 to a matching If-None-Match with no body; the snapshot ETag stays
the same while only clock-driven keys (elapsed_s of a running job, server_time) move on, so the poll gets a 304;
the keys stay in the 200 body; a real change (a job ending) gives a new ETag. Runs on an ephemeral port in a temp
ROADMAP_HOME (ServerCase)."""

import json
import os
import time
import unittest

from roadmap.http import routes
from tests.api.support import PROJECT_ID, ServerCase

RUNNING_JOBS = {"jobs": [{"id": "j1", "title": "etag probe", "model": "m", "status": "running",
                          "started": "2020-01-01T00:00:00+00:00", "ended": None}]}
ENDED_JOBS = {"jobs": [{"id": "j1", "title": "etag probe", "model": "m", "status": "done",
                        "started": "2020-01-01T00:00:00+00:00", "ended": "2020-01-01T00:10:00+00:00"}]}


class ContentEtag(unittest.TestCase):
    def test_clock_keys_do_not_change_the_etag(self):
        a = {"server_time": "2026-10-15T10:00:00+00:00", "jobs": [{"id": "j", "elapsed_s": 12.5, "age": 3}]}
        b = {"server_time": "2026-10-15T10:05:00+00:00", "jobs": [{"id": "j", "elapsed_s": 312.5, "age": 8}]}
        self.assertEqual(routes.content_etag(a), routes.content_etag(b))

    def test_a_real_field_still_changes_the_etag(self):
        a = {"jobs": [{"id": "j", "status": "running", "elapsed_s": 1.0}]}
        b = {"jobs": [{"id": "j", "status": "done", "elapsed_s": 1.0}]}
        self.assertNotEqual(routes.content_etag(a), routes.content_etag(b))

    def test_the_input_is_not_changed(self):
        body = {"server_time": "x", "elapsed_s": 1.0, "keep": 2}
        routes.content_etag(body)
        self.assertEqual(body, {"server_time": "x", "elapsed_s": 1.0, "keep": 2})


class EtagRoutes(ServerCase):
    def setUp(self):
        super().setUp()
        self.jobs_path = os.path.join(self.project_root, "docs", "jobs.json")
        self._set_jobs(RUNNING_JOBS)

    def _set_jobs(self, data):
        with open(self.jobs_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def projects(self, headers=None):
        return self.request("GET", "/api/v1/projects", headers=headers)

    def snapshot(self, headers=None):
        return self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID, headers=headers)

    def test_projects_sends_an_etag_and_answers_304(self):
        first = self.projects()
        self.assertEqual(first.status, 200)
        etag = first.header("ETag")
        self.assertTrue(etag)
        again = self.projects({"If-None-Match": etag})
        self.assertEqual(again.status, 304)
        self.assertEqual(again.body, b"")

    def test_projects_etag_changes_with_the_summary(self):
        etag = self.projects().header("ETag")
        self._set_jobs(ENDED_JOBS)
        after = self.projects({"If-None-Match": etag})
        self.assertEqual(after.status, 200)
        self.assertNotEqual(after.header("ETag"), etag)

    def test_snapshot_with_a_running_job_gives_304_while_elapsed_moves(self):
        first = self.snapshot()
        self.assertEqual(first.status, 200)
        etag = first.header("ETag")
        time.sleep(0.25)
        second = self.snapshot({"If-None-Match": etag})
        self.assertEqual(second.status, 304)

    def test_snapshot_body_keeps_elapsed_and_server_time(self):
        body = self.snapshot().json()
        self.assertIn("server_time", body)
        running = [job for job in body["jobs"] if job.get("status") == "running"]
        self.assertTrue(running)
        self.assertIn("elapsed_s", running[0])
        self.assertGreater(running[0]["elapsed_s"], 0)

    def test_snapshot_etag_changes_when_a_job_ends(self):
        etag = self.snapshot().header("ETag")
        self._set_jobs(ENDED_JOBS)
        after = self.snapshot({"If-None-Match": etag})
        self.assertEqual(after.status, 200)
        self.assertNotEqual(after.header("ETag"), etag)


if __name__ == "__main__":
    unittest.main()
