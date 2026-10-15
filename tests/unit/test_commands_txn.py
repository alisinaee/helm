"""Command layer with the sqlite switch on: data, activity line and undo commit in one db transaction, a failure
rolls all three back, and a repeated idempotency key applies once. Switch off keeps the JSON path."""

import os
import unittest
from unittest import mock

from roadmap.services import commands, tasks
from roadmap.store import db as store_db, events as store_events
from tests.unit.test_cmd_support import CmdCase


class TxnTests(CmdCase):
    def switch(self, value):
        patcher = mock.patch.dict(os.environ, {"ROADMAP_STORE": value})
        patcher.start()
        self.addCleanup(patcher.stop)

    def db(self):
        return store_db.connect(os.path.join(self.data, "head.db"))

    def count(self, kind):
        conn = self.db()
        try:
            return conn.execute("SELECT COUNT(*) FROM events WHERE kind = ?", (kind,)).fetchone()[0]
        finally:
            conn.close()

    def read_text(self, name):
        with open(os.path.join(self.data, name), encoding="utf-8") as fh:
            return fh.read()

    def test_switch_off_writes_no_db(self):
        self.switch("")
        reply = self.op("task.status", {"id": "P1.1", "status": "done"})
        self.assertTrue(reply["ok"])
        self.assertFalse(os.path.exists(os.path.join(self.data, "head.db")))
        self.assertEqual(len(self.read_lines("activity.jsonl")), 1)

    def test_switch_on_commits_data_activity_and_undo_together(self):
        self.switch("sqlite")
        reply = self.op("task.status", {"id": "P1.1", "status": "done"})
        self.assertTrue(reply["undo"])
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "done")
        self.assertEqual(self.count("activity"), 1)
        self.assertEqual(self.count("undo"), 1)

    def test_injected_failure_after_data_write_rolls_back_everything(self):
        self.switch("sqlite")
        self.op("task.status", {"id": "P1.3", "status": "done"})  # creates head.db and seeds the mirror
        before = {name: self.read_text(name) for name in ("tasks.json", "activity.jsonl", "undo.jsonl")}
        real_append = store_events.append

        def fail_on_undo(conn, kind, *args, **kwargs):
            if kind == "undo":
                raise RuntimeError("injected failure")
            return real_append(conn, kind, *args, **kwargs)

        with mock.patch.object(store_events, "append", side_effect=fail_on_undo):
            with self.assertRaises(RuntimeError):
                self.op("task.status", {"id": "P1.2", "status": "done"})
        self.assertEqual(tasks.get(self.data, "P1.2")["status"], "todo")
        for name, text in before.items():
            self.assertEqual(self.read_text(name), text, name)
        self.assertEqual(self.count("activity"), 1)
        self.assertEqual(self.count("undo"), 1)

    def test_same_idempotency_key_applies_once(self):
        self.switch("sqlite")
        args = {"id": "P1.1", "status": "done", "requestId": "req-1"}
        first = self.op("task.status", dict(args))
        second = self.op("task.status", dict(args))
        self.assertTrue(second.get("replayed"))
        self.assertEqual(first["activity"], second["activity"])
        self.assertEqual(len(self.read_lines("activity.jsonl")), 1)
        self.assertEqual(self.count("activity"), 1)

    def test_repeat_without_request_id_within_10s_replays(self):
        self.switch("sqlite")
        first = self.op("task.status", {"id": "P1.1", "status": "done"})
        second = self.op("task.status", {"id": "P1.1", "status": "done"})
        self.assertTrue(second.get("replayed"))
        self.assertEqual(first["activity"], second["activity"])
        self.assertEqual(len(self.read_lines("activity.jsonl")), 1)

    def test_done_todo_done_without_request_id_applies_all_three(self):
        self.switch("sqlite")
        self.op("task.status", {"id": "P1.1", "status": "done"})
        self.op("task.status", {"id": "P1.1", "status": "todo"})
        third = self.op("task.status", {"id": "P1.1", "status": "done"})
        self.assertNotIn("replayed", third)
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "done")
        self.assertEqual(len(self.read_lines("activity.jsonl")), 3)
        self.assertEqual(self.count("activity"), 3)

    def test_new_request_id_applies_again(self):
        self.switch("sqlite")
        self.op("task.status", {"id": "P1.1", "status": "done", "requestId": "req-1"})
        again = self.op("task.status", {"id": "P1.1", "status": "todo", "requestId": "req-2"})
        self.assertNotIn("replayed", again)
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "todo")
        self.assertEqual(len(self.read_lines("activity.jsonl")), 2)


if __name__ == "__main__":
    unittest.main()
