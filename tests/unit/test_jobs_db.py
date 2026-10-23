"""Tests for roadmap/services/jobs_db.py and the backend switch in roadmap/services/jobs.py (R7.91).

Single-flight claims (two connections race), files required for edit jobs, one event per write in the same
transaction, and the JSON backend left as the default. Every test runs in temp folders; nothing real is touched.
"""

import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import jobs
from roadmap.services import jobs_db
from roadmap.store import config, db, events, paths


class DbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jobsdb-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = os.path.join(self.tmp, "docs")
        os.makedirs(self.data)
        with open(os.path.join(self.data, "tasks.json"), "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 1, "tasks": [{"id": "P1.1", "status": "todo"},
                                                     {"id": "P1.2", "status": "todo"}]}, fh)
        patch = mock.patch.dict(os.environ, {paths.ENV_HOME: os.path.join(self.tmp, "home")})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("ROADMAP_STORE", None)

    def use_sqlite(self):
        os.environ["ROADMAP_STORE"] = "sqlite"

    def event_kinds(self):
        conn = db.connect(jobs_db.db_path(self.data))
        try:
            return [e["kind"] for e in events.since(conn, 0, limit=1000)]
        finally:
            conn.close()

    def job_rows(self):
        conn = db.connect(jobs_db.db_path(self.data))
        try:
            return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        finally:
            conn.close()


class SwitchTests(DbCase):
    def test_json_is_the_default_and_no_sqlite_file_appears(self):
        self.assertEqual(jobs.store_backend(self.data), "json")
        job = jobs.start_job(self.data, "first", "haiku")
        jobs.finish_job(self.data, job["id"], "done", tokens_k=2)
        self.assertTrue(os.path.exists(os.path.join(self.data, "jobs.json")))
        self.assertFalse(os.path.exists(jobs_db.db_path(self.data)))
        self.assertEqual(jobs.list_jobs(self.data)[0]["status"], "done")

    def test_env_switch_routes_start_finish_and_list_to_sqlite(self):
        self.use_sqlite()
        job = jobs.start_job(self.data, "first", "haiku")
        jobs.finish_job(self.data, job["id"], "done")
        self.assertFalse(os.path.exists(os.path.join(self.data, "jobs.json")))
        self.assertEqual([j["status"] for j in jobs.list_jobs(self.data)], ["done"])

    def test_project_store_key_routes_to_sqlite(self):
        config.add_project("Demo", self.tmp, project_id="demo", data_dir="docs")
        with open(paths.config_file(), encoding="utf-8") as fh:
            cfg = json.load(fh)
        cfg["projects"][0]["store"] = "sqlite"
        with open(paths.config_file(), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        self.assertEqual(jobs.store_backend(self.data), "sqlite")
        jobs.start_job(self.data, "first", "haiku")
        self.assertTrue(os.path.exists(jobs_db.db_path(self.data)))

    def test_claim_on_the_json_backend_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            jobs.claim_job(self.data, "P1.1", ["a.py"], "w1")
        self.assertEqual(ctx.exception.code, "usage")


class ClaimTests(DbCase):
    def setUp(self):
        super().setUp()
        self.use_sqlite()

    def test_second_claim_returns_the_running_job(self):
        job, created = jobs_db.claim(self.data, "P1.1", ["b.py", "a.py"], "w1")
        again, created_again = jobs_db.claim(self.data, "P1.1", ["c.py"], "w2")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(again["id"], job["id"])
        self.assertEqual(again["files"], ["a.py", "b.py"])

    def test_single_flight_under_two_connections(self):
        jobs_db.claim(self.data, "P1.2", ["seed.py"], "seed")  # create the schema once before the race
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def race(worker):
            try:
                barrier.wait()
                results.append(jobs_db.claim(self.data, "P1.1", ["x.py"], worker))
            except Exception as exc:  # collected and checked below
                errors.append(exc)

        threads = [threading.Thread(target=race, args=(name,)) for name in ("w1", "w2")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(created for _, created in results), [False, True])
        self.assertEqual(len({job["id"] for job, _ in results}), 1)
        self.assertEqual(self.job_rows(), 2)

    def test_second_connection_sees_the_claim_of_the_first(self):
        jobs_db.claim(self.data, "P1.1", ["x.py"], "w1")
        conn = db.connect(jobs_db.db_path(self.data))
        try:
            running = conn.execute("SELECT COUNT(*) FROM jobs WHERE task = 'P1.1' AND status = 'running'").fetchone()
            self.assertEqual(running[0], 1)
        finally:
            conn.close()

    def test_edit_claim_needs_files(self):
        for files in ([], None, ["  ", ""]):
            with self.assertRaises(RoadmapError) as ctx:
                jobs_db.claim(self.data, "P1.1", files, "w1")
            self.assertEqual(ctx.exception.code, "usage")
        self.assertEqual(self.job_rows(), 0)
        self.assertEqual(self.event_kinds(), [])

    def test_read_only_roles_may_claim_without_files(self):
        _, review_created = jobs_db.claim(self.data, "P1.1", [], "r1", kind="review")
        _, audit_created = jobs_db.claim(self.data, "P1.2", None, "a1", kind="audit")
        self.assertTrue(review_created)
        self.assertTrue(audit_created)

    def test_claim_needs_a_known_task_worker_and_kind(self):
        with self.assertRaises(RoadmapError) as missing:
            jobs_db.claim(self.data, "P9.9", ["x.py"], "w1")
        self.assertEqual(missing.exception.code, "not_found")
        with self.assertRaises(RoadmapError) as no_worker:
            jobs_db.claim(self.data, "P1.1", ["x.py"], " ")
        self.assertEqual(no_worker.exception.code, "usage")
        with self.assertRaises(RoadmapError) as bad_kind:
            jobs_db.claim(self.data, "P1.1", ["x.py"], "w1", kind="deploy")
        self.assertEqual(bad_kind.exception.code, "usage")


class EventTests(DbCase):
    def setUp(self):
        super().setUp()
        self.use_sqlite()

    def test_each_write_appends_one_event_and_a_no_op_claim_appends_none(self):
        job = jobs.start_job(self.data, "first", "haiku", task="P1.1")
        jobs.finish_job(self.data, job["id"], "done", tokens_k=3)
        jobs.claim_job(self.data, "P1.2", ["a.py"], "w1")
        jobs.claim_job(self.data, "P1.2", ["a.py"], "w2")
        self.assertEqual(self.event_kinds(), ["job.started", "job.finished", "job.claimed"])

    def test_refused_writes_append_no_event(self):
        job = jobs.start_job(self.data, "first", "haiku")
        jobs.finish_job(self.data, job["id"], "done")
        before = self.event_kinds()
        with self.assertRaises(RoadmapError):
            jobs.finish_job(self.data, job["id"], "done")
        with self.assertRaises(RoadmapError):
            jobs.finish_job(self.data, "j99", "done")
        self.assertEqual(self.event_kinds(), before)

    def test_done_and_failed_finishes_update_the_task_like_the_json_backend(self):
        job = jobs.start_job(self.data, "first", "haiku", task="P1.1")
        jobs.finish_job(self.data, job["id"], "done")
        with open(os.path.join(self.data, "tasks.json"), encoding="utf-8") as fh:
            task = json.load(fh)["tasks"][0]
        self.assertTrue(task.get("verify"))
        job = jobs.start_job(self.data, "second", "haiku", task="P1.2")
        jobs.finish_job(self.data, job["id"], "failed", reason="boom")
        with open(os.path.join(self.data, "tasks.json"), encoding="utf-8") as fh:
            task = json.load(fh)["tasks"][1]
        self.assertEqual(task["status"], "todo")


if __name__ == "__main__":
    unittest.main()
