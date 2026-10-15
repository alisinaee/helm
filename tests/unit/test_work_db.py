"""Tests for store v4 (work_items, agent tasks with work_id) and roadmap/store/work_db.py. Temp dirs only."""

import os
import sqlite3
import tempfile
import unittest

from roadmap.errors import RoadmapError
from roadmap.store import db, events, tasks_db, work_db


class WorkDbTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name
        self.conn = db.open_project(self.data_dir)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _txn_add(self, title, **kw):
        with db.txn(self.conn):
            return work_db.add(self.conn, title, **kw)

    def _kinds(self):
        return [e["kind"] for e in events.since(self.conn, 0, limit=1000)]

    def test_v4_migrate_twice_same(self):
        self.assertEqual(db.schema_version(self.conn), 4)
        self._txn_add("First item")
        before = db.table_checksums(self.conn)
        self.conn.close()
        self.conn = db.open_project(self.data_dir)
        self.assertEqual(db.schema_version(self.conn), 4)
        self.assertEqual(db.table_checksums(self.conn), before)
        self.assertIn("work_items", before)

    def test_v3_database_migrates_and_keeps_agent_tasks(self):
        path = os.path.join(self.data_dir, "old.db")
        self.conn.close()
        raw = sqlite3.connect(path, isolation_level=None)
        for version in (1, 2, 3):
            for stmt in db.MIGRATIONS[version]:
                raw.execute(stmt)
        raw.execute("PRAGMA user_version = 3")
        raw.execute("INSERT INTO tasks (id, phase, title, status) VALUES ('R7.1', NULL, 'old row', 'todo')")
        raw.close()
        conn = db.connect(path)
        try:
            self.assertEqual(db.schema_version(conn), 4)
            row = conn.execute("SELECT title, work_id FROM tasks WHERE id = 'R7.1'").fetchone()
            self.assertEqual((row["title"], row["work_id"]), ("old row", None))
            first = db.table_checksums(conn)
        finally:
            conn.close()
        conn = db.connect(path)
        try:
            self.assertEqual(db.table_checksums(conn), first)
        finally:
            conn.close()

    def test_agent_task_without_work_id_refused(self):
        with db.txn(self.conn):
            with self.assertRaises(RoadmapError) as cm:
                tasks_db.insert_agent_task(self.conn, "R7.9", "orphan", "todo", None)
        self.assertEqual(cm.exception.code, "invalid_data")
        with db.txn(self.conn):
            with self.assertRaises(RoadmapError):
                work_db.add_agent_task(self.conn, "R7.10", "empty", "")
        with db.txn(self.conn):
            with self.assertRaises(RoadmapError) as cm:
                work_db.add_agent_task(self.conn, "R7.11", "no such item", "W99")
        self.assertEqual(cm.exception.code, "not_found")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)

    def test_link_and_list_per_work_item(self):
        w1 = self._txn_add("Ledger of asks")
        w2 = self._txn_add("Same screens", kind="issue", prio="P0")
        self.assertEqual((w1["id"], w2["id"]), ("W1", "W2"))
        self.assertEqual(w2["prio"], "P0")
        with db.txn(self.conn):
            work_db.add_agent_task(self.conn, "R7.31", "ask ledger", w1["id"])
            work_db.add_agent_task(self.conn, "R7.32", "ask bind", w1["id"])
            work_db.add_agent_task(self.conn, "R7.40", "screens", w2["id"], status="done")
        with db.txn(self.conn):
            moved = work_db.link(self.conn, "R7.32", w2["id"])
        self.assertEqual(moved["work_id"], "W2")
        self.assertEqual([t["id"] for t in work_db.agent_tasks(self.conn, "W1")], ["R7.31"])
        self.assertEqual([t["id"] for t in work_db.agent_tasks(self.conn, "W2")], ["R7.32", "R7.40"])
        self.assertEqual([i["id"] for i in work_db.list_items(self.conn)], ["W1", "W2"])
        self.assertEqual([i["id"] for i in work_db.list_items(self.conn, kind="issue")], ["W2"])
        with db.txn(self.conn):
            with self.assertRaises(RoadmapError):
                work_db.link(self.conn, "R7.31", "W404")
            with self.assertRaises(RoadmapError):
                work_db.link(self.conn, "R7.999", "W1")

    def test_status_roll_stamps_accept_and_reopen(self):
        item = self._txn_add("Accept me")
        with db.txn(self.conn):
            done = work_db.set_status(self.conn, item["id"], "Done")
        self.assertIsNotNone(done["accepted_at"])
        with db.txn(self.conn):
            reopened = work_db.set_status(self.conn, item["id"], "Doing")
        self.assertIsNone(reopened["accepted_at"])
        self.assertEqual(reopened["reopened"], 1)
        with db.txn(self.conn):
            with self.assertRaises(RoadmapError):
                work_db.set_status(self.conn, item["id"], "Shipped")

    def test_events_written_in_the_same_txn(self):
        item = self._txn_add("Event check")
        with db.txn(self.conn):
            work_db.add_agent_task(self.conn, "R7.50", "task", item["id"])
        with db.txn(self.conn):
            work_db.set_status(self.conn, item["id"], "Doing")
        with db.txn(self.conn):
            work_db.set_status(self.conn, item["id"], "Doing")
        with db.txn(self.conn):
            w2 = work_db.add(self.conn, "Other")
            work_db.link(self.conn, "R7.50", w2["id"])
        kinds = self._kinds()
        self.assertEqual(kinds, ["work.add", "task.add", "work.status", "work.add", "task.link"])
        last = events.since(self.conn, 0, limit=1000)[-1]
        self.assertEqual((last["entity"], last["entity_id"]), ("agent_task", "R7.50"))
        self.assertEqual(last["payload"], {"from": item["id"], "to": w2["id"]})

    def test_failed_write_leaves_no_event(self):
        with self.assertRaises(RoadmapError):
            with db.txn(self.conn):
                work_db.add(self.conn, "Rolled back")
                raise RoadmapError("invalid_data", "boom", 5)
        self.assertEqual(work_db.list_items(self.conn), [])
        self.assertEqual(self._kinds(), [])


if __name__ == "__main__":
    unittest.main()
