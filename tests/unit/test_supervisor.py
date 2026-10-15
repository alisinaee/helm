"""Tests for roadmap/services/leases.py and roadmap/services/supervisor.py (R7.99, Wave 3 S1).

Lease conflicts, heartbeats, reap, retry with backoff up to needs-you, fold to done, two concurrent ticks doing the
work once, and queue order by priority. Temp dirs only; the store is the project file docs/roadmap.db inside them.
"""

import json
import os
import shutil
import tempfile
import threading
import unittest

from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import leases, supervisor
from roadmap.store import db, jobs_db


class SupervisorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="supervisor-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = os.path.join(self.tmp, "docs")
        os.makedirs(self.data)
        self.conn = db.open_project(self.data)
        self.addCleanup(self.conn.close)

    def add_job(self, jid, status, task=None, files=(), **extra):
        job = {"id": jid, "title": jid, "model": "m", "status": status, "task": task, "started": None,
               "ended": None, "kind": "edit", "files": sorted(files)}
        job.update(extra)
        with db.txn(self.conn):
            jobs_db._save(self.conn, job)

    def set_job(self, jid, **fields):
        with db.txn(self.conn):
            job = jobs_db._load(self.conn, jid)
            job.update(fields)
            jobs_db._save(self.conn, job)

    def add_task(self, tid, status="todo", refs=()):
        with db.txn(self.conn):
            self.conn.execute("INSERT INTO tasks (id, phase, title, status, data) VALUES (?, NULL, ?, ?, ?)",
                              (tid, tid, status, json.dumps({"refs": list(refs)})))

    def add_ask(self, eid, links):
        body = {"sum": eid, "links": list(links), "fp": eid}
        with db.txn(self.conn):
            self.conn.execute("INSERT INTO asks (t, id, ts, kind, data) VALUES ('e', ?, '2026-01-01T00:00:00Z',"
                              " 'ask', ?)", (eid, json.dumps(body, sort_keys=True)))

    def event_kinds(self, kind):
        return [e["kind"] for e in self.conn.execute("SELECT kind FROM events").fetchall() if e["kind"] == kind]

    def lease_files(self, jid):
        return [r["file"] for r in self.conn.execute("SELECT file FROM leases WHERE job_id = ? ORDER BY file",
                                                     (jid,))]


class LeaseTests(SupervisorCase):
    def test_lease_conflict_refused(self):
        self.add_job("j1", "running", "P1.1", ["a.py"])
        self.add_job("j2", "running", "P1.2", ["a.py", "b.py"])
        with db.txn(self.conn):
            self.assertTrue(leases.acquire(self.conn, "j1", ["a.py"], now=1000)["ok"])
        with db.txn(self.conn):
            refused = leases.acquire(self.conn, "j2", ["b.py", "a.py"], now=1000)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["job"], "j1")
        self.assertEqual(refused["files"], ["a.py"])
        self.assertEqual(self.lease_files("j2"), [])
        self.assertEqual(self.lease_files("j1"), ["a.py"])

    def test_expired_or_finished_lease_does_not_block(self):
        self.add_job("j1", "running", "P1.1", ["a.py"])
        self.add_job("j2", "running", "P1.2", ["a.py"])
        with db.txn(self.conn):
            leases.acquire(self.conn, "j1", ["a.py"], ttl_s=10, now=1000)
        with db.txn(self.conn):
            self.assertTrue(leases.acquire(self.conn, "j2", ["a.py"], now=1011)["ok"])


class HeartbeatTests(SupervisorCase):
    def test_heartbeat_keeps_job_alive(self):
        self.add_job("j1", "running", "P1.1", ["a.py"], heartbeat=1000.0)
        with db.txn(self.conn):
            leases.acquire(self.conn, "j1", ["a.py"], now=1000)
        supervisor.tick(self.data, now=1100)
        with db.txn(self.conn):
            self.assertEqual(leases.heartbeat(self.conn, "j1", now=1100), 1)
        report = supervisor.tick(self.data, now=1250)
        self.assertEqual(report["reaped"], [])
        self.assertEqual(self.lease_files("j1"), ["a.py"])
        self.assertEqual(supervisor.tick(self.data, now=1300)["reaped"], ["j1"])


class ReapTests(SupervisorCase):
    def test_stale_job_reaped_and_lease_freed(self):
        self.add_job("j1", "running", "P1.1", ["a.py"], heartbeat=1000.0)
        with db.txn(self.conn):
            leases.acquire(self.conn, "j1", ["a.py"], now=1000)
        report = supervisor.tick(self.data, now=1181)
        self.assertEqual(report["reaped"], ["j1"])
        job = jobs_db._load(self.conn, "j1")
        self.assertEqual((job["status"], job["reason"]), ("failed", "no heartbeat"))
        self.assertEqual(self.lease_files("j1"), [])
        self.assertIn("job.failed", self.event_kinds("job.failed"))
        self.assertEqual(supervisor.tick(self.data, now=1182)["reaped"], [])


class RetryTests(SupervisorCase):
    def test_retry_with_backoff_then_needs_you(self):
        self.add_task("P1.1", "partial")
        self.add_ask("H1", ["task:P1.1"])
        self.add_job("j1", "failed", "P1.1", ["a.py"], failed_at=1000.0, reason="no heartbeat")
        self.assertEqual(supervisor.tick(self.data, now=1000)["queued"], ["j2"])
        self.assertEqual(supervisor.tick(self.data, now=1000)["queued"], [])
        retry = jobs_db._load(self.conn, "j2")
        self.assertEqual((retry["status"], retry["task"], retry["not_before"]), ("queued", "P1.1", 1120.0))
        with db.txn(self.conn):
            self.assertEqual(supervisor.next_launches(self.conn, 5, now=1119), [])
            self.assertEqual([j["id"] for j in supervisor.next_launches(self.conn, 5, now=1120)], ["j2"])
        self.set_job("j2", status="failed", failed_at=1120.0, reason="no heartbeat")
        self.assertEqual(supervisor.tick(self.data, now=1120)["queued"], ["j3"])
        self.assertEqual(jobs_db._load(self.conn, "j3")["not_before"], 1720.0)
        self.set_job("j3", status="failed", failed_at=1720.0, reason="no heartbeat")
        report = supervisor.tick(self.data, now=1720)
        self.assertEqual((report["queued"], report["needs_you"]), ([], ["P1.1"]))
        self.assertEqual(json.loads(self.conn.execute("SELECT data FROM asks WHERE id = 'H1'").fetchone()["data"])
                         ["status"], "needs-you")
        self.assertTrue(json.loads(self.conn.execute("SELECT data FROM tasks WHERE id = 'P1.1'").fetchone()["data"])
                        ["needs_you"])


class FoldTests(SupervisorCase):
    def test_fold_to_done(self):
        self.add_task("P1.1", "partial", ["commit:abc1234def"])
        self.add_task("P1.2", "partial", [])
        self.add_job("j1", "done", "P1.1", refs=["commit:abc1234def"])
        self.add_job("j2", "done", "P1.2")
        self.add_ask("H1", ["task:P1.1"])
        report = supervisor.tick(self.data, now=2000)
        self.assertEqual(report["done_tasks"], ["P1.1"])
        self.assertEqual(report["closed_asks"], ["H1"])
        status = self.conn.execute("SELECT status FROM tasks WHERE id = 'P1.1'").fetchone()["status"]
        self.assertEqual(status, "done")
        self.assertEqual(self.conn.execute("SELECT status FROM tasks WHERE id = 'P1.2'").fetchone()["status"],
                         "partial")
        ask = json.loads(self.conn.execute("SELECT data FROM asks WHERE id = 'H1'").fetchone()["data"])
        self.assertEqual((ask["status"], ask["by"]), ("done", "auto"))
        self.assertIn("P1.1 abc1234", ask["note"])


class ConcurrencyTests(SupervisorCase):
    def test_two_concurrent_ticks_do_the_work_once(self):
        self.add_job("j1", "failed", "P1.1", ["a.py"], failed_at=1000.0, reason="no heartbeat")
        results, errors = [], []
        barrier = threading.Barrier(2)

        def run():
            try:
                barrier.wait()
                results.append(supervisor.tick(self.data, now=1000))
            except Exception as exc:  # reported by the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        queued = [q for r in results if r.get("ran") for q in r["queued"]]
        self.assertEqual(queued, ["j2"])
        retries = self.conn.execute("SELECT COUNT(*) FROM jobs WHERE data LIKE '%\"retry_of\": \"j1\"%'").fetchone()[0]
        self.assertEqual(retries, 1)
        self.assertEqual(self.event_kinds("job.queued"), ["job.queued"])


class QueueTests(SupervisorCase):
    def test_queue_order_by_priority(self):
        self.add_job("r", "running", "P9.1", ["c.py"])
        with db.txn(self.conn):
            leases.acquire(self.conn, "r", ["c.py"], now=100)
        self.add_job("a", "queued", "T.a", ["a.py"], prio="P2", queued_at=1.0)
        self.add_job("b", "queued", "T.b", ["b.py"], prio="P0", queued_at=5.0)
        self.add_job("c", "queued", "T.c", ["c.py"], prio="P2", queued_at=0.0)
        self.add_job("d", "queued", "T.d", ["d.py"], prio="P1", queued_at=2.0)
        self.add_job("e", "queued", "T.e", ["e.py"], queued_at=3.0)
        with db.txn(self.conn):
            ids = [j["id"] for j in supervisor.next_launches(self.conn, 2, now=100)]
        self.assertEqual(ids, ["b", "d"])
        with db.txn(self.conn):
            ids = [j["id"] for j in supervisor.next_launches(self.conn, 10, now=100)]
        self.assertEqual(ids, ["a", "e"])
        self.add_job("f", "queued", "T.f", ["a.py"], prio="P0", queued_at=9.0)
        with db.txn(self.conn):
            self.assertEqual(supervisor.next_launches(self.conn, 10, now=100), [])


class FindingTests(SupervisorCase):
    def test_fold_ignores_failed_job_retried_by_later_done(self):
        self.add_task("P1.1", "partial")
        self.add_job("j1", "failed", "P1.1", failed_at=1000.0, reason="no heartbeat", retried_by="j2")
        self.add_job("j2", "done", "P1.1", refs=["commit:abc1234def"])
        self.assertEqual(supervisor.tick(self.data, now=2000)["done_tasks"], ["P1.1"])

    def test_only_lost_or_unavailable_failures_retry(self):
        self.add_task("P1.1", "partial")
        self.add_ask("H1", ["task:P1.1"])
        self.add_job("j1", "failed", "P1.1", failed_at=1000.0, reason="boom")
        report = supervisor.tick(self.data, now=1000)
        self.assertEqual((report["queued"], report["needs_you"]), ([], ["P1.1"]))
        self.add_task("P1.2", "partial")
        self.add_job("j2", "failed", "P1.2", failed_at=1000.0, reason="Cannot connect to the engine")
        self.assertEqual(supervisor.tick(self.data, now=1000)["queued"], ["j3"])

    def test_claim_leases_in_its_txn_and_finish_releases(self):
        with open(os.path.join(self.data, "tasks.json"), "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 1, "tasks": [{"id": "P1.1", "status": "todo"},
                                                     {"id": "P1.2", "status": "todo"}]}, fh)
        job, created = jobs_db.claim(self.data, "P1.1", ["a.py"], "w1")
        self.assertTrue(created)
        self.assertEqual(self.lease_files(job["id"]), ["a.py"])
        with self.assertRaises(RoadmapError):
            jobs_db.claim(self.data, "P1.2", ["a.py"], "w2")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM jobs WHERE task = 'P1.2'").fetchone()[0], 0)
        self.add_job("q", "queued", "T.q", ["z.py"], queued_at=1.0)
        with db.txn(self.conn):
            self.assertEqual([j["id"] for j in supervisor.next_launches(self.conn, 5, now=100)], ["q"])
        with db.txn(self.conn):
            self.assertFalse(leases.acquire(self.conn, "other", ["z.py"], now=100)["ok"])
        jobs_db.finish(self.data, job["id"], "done")
        self.assertEqual(self.lease_files(job["id"]), [])

    def test_next_launches_reserves_what_it_returns(self):
        self.add_job("q1", "queued", "T.1", ["x.py"], queued_at=1.0)
        with db.txn(self.conn):
            first = supervisor.next_launches(self.conn, 5, now=100)
            again = supervisor.next_launches(self.conn, 5, now=100)
        self.assertEqual([j["id"] for j in first], ["q1"])
        self.assertEqual(again, [])
        self.assertEqual(jobs_db._load(self.conn, "q1")["status"], "claimed")
        self.assertEqual(self.lease_files("q1"), ["x.py"])

    def test_bad_heartbeat_is_logged_and_skipped(self):
        self.add_job("j1", "running", "P1.1", heartbeat="not a time")
        self.add_job("j2", "running", "P1.2", heartbeat=1000.0)
        with self.assertLogs("roadmap.services.supervisor", level="WARNING"):
            report = supervisor.tick(self.data, now=1181)
        self.assertEqual(report["reaped"], ["j2"])
        self.assertEqual(jobs_db._load(self.conn, "j1")["status"], "running")

    def test_pass_error_surfaces_and_releases_lock(self):
        with mock.patch.object(supervisor, "_fold_tasks", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                supervisor.tick(self.data, now=1000)
        lock = self.conn.execute("SELECT value FROM meta WHERE key = ?", (supervisor.LOCK_KEY,)).fetchone()
        self.assertIsNone(lock)
        self.assertTrue(supervisor.tick(self.data, now=1000)["ran"])

    def test_backoff_is_two_then_ten_minutes(self):
        self.assertEqual(supervisor.BACKOFF_S, (120.0, 600.0))
        self.add_job("j1", "failed", "P1.1", failed_at=1000.0, reason="no heartbeat")
        self.assertEqual(supervisor.tick(self.data, now=1000)["queued"], ["j2"])
        self.assertEqual(jobs_db._load(self.conn, "j2")["not_before"], 1120.0)
        self.set_job("j2", status="failed", failed_at=1120.0, reason="no heartbeat")
        self.assertEqual(supervisor.tick(self.data, now=1120)["queued"], ["j3"])
        self.assertEqual(jobs_db._load(self.conn, "j3")["not_before"], 1720.0)

    def test_lease_ttl_covers_heartbeat_window(self):
        self.assertGreaterEqual(leases.DEFAULT_TTL_S, supervisor.HEARTBEAT_TTL_S)

    def test_fold_needs_commit_on_its_own_done_job(self):
        self.add_task("P1.1", "partial", ["commit:abc1234def"])
        self.add_job("j0", "done", "P9.9", refs=["commit:abc1234def"])
        self.add_job("j1", "done", "P1.1")
        self.assertEqual(supervisor.tick(self.data, now=2000)["done_tasks"], [])

    def test_escalation_visible_to_sql(self):
        self.add_task("P1.1", "partial")
        self.add_job("j1", "failed", "P1.1", failed_at=1000.0, reason="boom")
        supervisor.tick(self.data, now=1000)
        self.assertEqual(supervisor.needs_you_tasks(self.conn), ["P1.1"])

    def test_orphan_lease_dropped_by_tick(self):
        with db.txn(self.conn):
            leases.acquire(self.conn, "ghost", ["a.py"], now=1000)
        report = supervisor.tick(self.data, now=1001)
        self.assertEqual(report["expired_leases"], ["a.py"])
        self.assertEqual(self.lease_files("ghost"), [])


if __name__ == "__main__":
    unittest.main()
