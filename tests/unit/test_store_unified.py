"""One project store file (docs/roadmap.db) shared by jobs, head, tasks and the loader (R7.96).

Temp dirs only. Checks: every module opens the same file; one transaction writing a job, a head entry and a task
commits together or rolls back together; the snapshot reads the store at one integer rev.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.services import loader
from roadmap.store import db, events, head_db, jobs_db, paths, tasks_db


class UnifiedStoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="store-unified-test-")
        self.data = os.path.join(self.tmp, "docs")
        os.makedirs(self.data)
        self.env = mock.patch.dict(os.environ, {paths.ENV_HOME: os.path.join(self.tmp, "home"),
                                                "ROADMAP_STORE": "sqlite"})
        self.env.start()
        loader._CACHE.clear()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def conn(self):
        return db.open_project(self.data)

    def write_all(self, conn, text):
        """One transaction: a job row, a head entry (asks row) and a task row, each with its event."""
        jobs_db._save(conn, {"id": "j1", "title": text, "model": "m", "status": "running", "task": "P1.1"})
        conn.execute("INSERT INTO asks (t, id, ts, kind, data) VALUES ('e', 'H1', '2026-10-15T00:00:00Z', 'info', ?)",
                     (json.dumps({"fp": "x", "len": 1, "sum": text, "text": text}),))
        conn.execute("INSERT INTO tasks (id, phase, title, status, data) VALUES ('P1.1', NULL, ?, 'todo', '{}')",
                     (text,))
        events.append(conn, "job.started", "job", "j1", {"title": text})


class SameFileTests(UnifiedStoreCase):
    def test_every_module_opens_the_same_file(self):
        path = db.db_path(self.data)
        self.assertEqual(os.path.basename(path), "roadmap.db")
        jobs_db.start(self.data, "first job", "sonnet")
        head_db.log(os.path.join(self.data, "head.db"), "Ship the store", "info", "ship")
        conn = tasks_db.open_store(self.data)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asks WHERE t = 'e'").fetchone()[0], 1)
        finally:
            conn.close()
        self.assertEqual(jobs_db.db_path(self.data), path)
        self.assertIn("roadmap.db", os.listdir(self.data))
        self.assertFalse(os.path.exists(os.path.join(self.data, "head.db")))
        self.assertFalse(os.path.exists(os.path.join(self.data, "roadmap.sqlite")))

    def test_loader_path_is_the_shared_file(self):
        self.assertEqual(loader._store_path(self.data), db.db_path(self.data))
        with mock.patch.dict(os.environ, {"ROADMAP_STORE": ""}):
            self.assertIsNone(loader._store_path(self.data))


class TransactionTests(UnifiedStoreCase):
    def test_job_head_and_task_commit_together(self):
        conn = self.conn()
        try:
            with db.txn(conn):
                self.write_all(conn, "committed")
        finally:
            conn.close()
        conn = self.conn()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM asks").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
            self.assertEqual(events.current_rev(conn), 1)
        finally:
            conn.close()

    def test_failure_rolls_all_three_back(self):
        conn = self.conn()
        try:
            with self.assertRaises(RuntimeError):
                with db.txn(conn):
                    self.write_all(conn, "rolled back")
                    raise RuntimeError("injected")
            for table in ("jobs", "asks", "tasks", "events"):
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0], 0, table)
        finally:
            conn.close()


class SnapshotTests(UnifiedStoreCase):
    def test_snapshot_reads_all_three_at_one_rev(self):
        conn = self.conn()
        try:
            with db.txn(conn):
                self.write_all(conn, "snap")
        finally:
            conn.close()
        dbp = db.db_path(self.data)
        store = loader._read_store(dbp)
        self.assertEqual(store["rev"], loader._store_rev(dbp))
        self.assertEqual(store["rev"], 1)
        jobs_doc = json.loads(store["files"]["jobs.json"])["jobs"]
        tasks_doc = json.loads(store["files"]["tasks.json"])["tasks"]
        self.assertEqual([j["id"] for j in jobs_doc], ["j1"])
        self.assertEqual([t["id"] for t in tasks_doc], ["P1.1"])
        self.assertEqual(len(store["head"]), 0)  # the raw asks row is not a v-tagged head record


if __name__ == "__main__":
    unittest.main()
