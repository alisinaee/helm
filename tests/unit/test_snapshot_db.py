"""R7.94 (W4): the snapshot read from the SQLite store behind the switch equals the JSON path.

Checks: with ROADMAP_STORE=sqlite the snapshot built from a migrated store equals the one built from the JSON files
(time fields left out); loader.revision is the store's integer rev and bumps after a write; a write that is still
open in another connection is not seen, and is seen whole once committed. Runs in a temp ROADMAP_HOME (ControlCase).
"""

import datetime
import json
import os
import tempfile
import unittest

from roadmap.core.snapshot import build_snapshot
from roadmap.services import loader
from roadmap.store import db, events, export, migrate
from tests.unit.test_control_support import ControlCase, write_json

NOW = datetime.datetime(2026, 10, 13, 14, 2, tzinfo=datetime.timezone.utc)
IGNORED = ("server_time", "usage", "rev", "updated")

JOBS = {"schemaVersion": 1, "jobs": [
    {"id": "j1", "task": "P0.1", "title": "Parse", "model": "sonnet", "status": "done",
     "started": "2026-10-13T13:00:00Z", "ended": "2026-10-13T13:20:00Z", "tokensK": 12},
    {"id": "j2", "task": "P0.2", "title": "Write", "model": "haiku", "status": "running",
     "started": "2026-10-13T13:50:00Z", "ended": None},
]}
HEAD = [
    {"v": 1, "t": "e", "id": "H1", "ts": "2026-10-13T10:00:00Z", "src": "manual", "kind": "ask",
     "sum": "first ask", "text": "first ask text"},
    {"v": 1, "t": "e", "id": "H2", "ts": "2026-10-13T11:00:00Z", "src": "manual", "kind": "idea",
     "sum": "second", "text": "second text"},
]


def _strip(snap):
    return {k: v for k, v in snap.items() if k not in IGNORED}


class SnapshotDbCase(ControlCase):
    def setUp(self):
        super().setUp()
        self._env("ROADMAP_STORE", None)
        loader._CACHE.clear()
        write_json(os.path.join(self.docs, "jobs.json"), JOBS)
        with open(os.path.join(self.docs, "head.jsonl"), "w", encoding="utf-8") as fh:
            for rec in HEAD:
                fh.write(json.dumps(rec) + "\n")
        self.dbp = db.db_path(self.docs)
        migrate.migrate_project(self.dbp, self.docs)

    def json_snap(self):
        self._env("ROADMAP_STORE", None)
        return loader.load_snapshot("demo", now=NOW)

    def db_snap(self):
        self._env("ROADMAP_STORE", "sqlite")
        return loader.load_snapshot("demo", now=NOW)


class SnapshotEqualityTest(SnapshotDbCase):
    def test_db_snapshot_equals_json_snapshot(self):
        js = self.json_snap()
        ds = self.db_snap()
        self.assertEqual(_strip(js), _strip(ds))
        self.assertEqual(len(ds["jobs"]), 2)
        self.assertIn("head", ds)

    def test_switch_off_keeps_json_revision(self):
        self._env("ROADMAP_STORE", None)
        self.assertIsInstance(loader.revision(self.docs, "demo"), str)


class SnapshotRevisionTest(SnapshotDbCase):
    def test_revision_is_integer_and_bumps_after_write(self):
        self._env("ROADMAP_STORE", "sqlite")
        before = loader.revision(self.docs, "demo")
        self.assertIsInstance(before, int)
        conn = db.connect(self.dbp)
        try:
            with db.txn(conn):
                events.append(conn, "task.triage", "task", "P0.1", {"status": "done"})
        finally:
            conn.close()
        after = loader.revision(self.docs, "demo")
        self.assertGreater(after, before)
        self.assertEqual(loader.load_snapshot("demo")["rev"], after)


class SnapshotIsolationTest(SnapshotDbCase):
    def test_uncommitted_write_is_not_seen(self):
        self._env("ROADMAP_STORE", "sqlite")
        rev_before = loader.revision(self.docs, "demo")
        writer = db.connect(self.dbp)
        try:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("INSERT INTO tasks (id, phase, title, status, data) VALUES ('P1.9', 'P1', 'halfwritten',"
                           " 'todo', '{}')")
            events.append(writer, "task.add", "task", "P1.9", {})
            seen = loader.load_snapshot("demo", now=NOW)
            self.assertNotIn("halfwritten", json.dumps(seen))
            self.assertEqual(seen["rev"], rev_before)
            writer.execute("COMMIT")
        finally:
            writer.close()
        seen = loader.load_snapshot("demo", now=NOW)
        self.assertIn("halfwritten", json.dumps(seen))
        self.assertGreater(seen["rev"], rev_before)


WORK = {"schemaVersion": 1, "items": [
    {"id": "W1", "kind": "task", "title": "Board", "status": "Todo", "prio": 1, "accepted": None, "reopened": 0,
     "reopenDone": None},
    {"id": "W2", "kind": "task", "title": "Store", "status": "Todo", "prio": 2, "accepted": None, "reopened": 0,
     "reopenDone": None},
    {"id": "W3", "kind": "task", "title": "Shipped", "status": "Done", "prio": 0, "accepted": "2026-10-14T09:00:00Z",
     "reopened": 0, "reopenDone": None},
    {"id": "W4", "kind": "task", "title": "Dropped", "status": "Won't do", "prio": 3, "accepted": None,
     "reopened": 0, "reopenDone": None},
], "links": {"P1.1": "W1", "P1.2": "W1", "P2.1": "W2", "P2.2": "W3", "P3.9": "W2"}, "events": []}
WORK_TASKS = {"schemaVersion": 1, "phases": [{"id": "P1", "name": "one", "status": "todo"}], "tasks": [
    {"id": "P1.1", "phase": "P1", "title": "a", "status": "done"},
    {"id": "P1.2", "phase": "P1", "title": "b", "status": "todo"},
    {"id": "P2.1", "phase": "P1", "title": "c", "status": "done"},
    {"id": "P2.2", "phase": "P1", "title": "d", "status": "done"},
]}


def _work_snap(work_doc, tasks_doc=WORK_TASKS):
    files = {"tasks.json": json.dumps(tasks_doc)}
    if work_doc is not None:
        files["work.json"] = json.dumps(work_doc)
    return build_snapshot(files, {}, NOW)


class SnapshotWorkTest(unittest.TestCase):
    def test_work_key_rolls_up_status_and_progress(self):
        rows = {r["id"]: r for r in _work_snap(WORK)["work"]}
        self.assertEqual(rows["W1"]["status"], "Doing")                 # one done, one todo
        self.assertEqual(rows["W1"]["progress"], {"done": 1, "total": 2})
        self.assertEqual(rows["W1"]["prio"], "P1")
        self.assertEqual(rows["W2"]["status"], "Review")                 # all linked tasks done, not accepted
        self.assertEqual(rows["W2"]["progress"], {"done": 1, "total": 1})  # P3.9 is not in tasks.json: cancelled
        self.assertEqual(rows["W3"]["status"], "Done")                   # accepted by the person
        self.assertEqual(rows["W3"]["progress"], {"done": 1, "total": 1})
        self.assertEqual(rows["W4"]["status"], "Won't do")
        self.assertEqual(rows["W4"]["progress"], {"done": 0, "total": 0})

    def test_work_rows_keep_work_json_order(self):
        self.assertEqual([r["id"] for r in _work_snap(WORK)["work"]], ["W1", "W2", "W3", "W4"])

    def test_no_work_json_leaves_key_out(self):
        self.assertNotIn("work", _work_snap(None))

    def test_bad_work_json_is_an_error_entry_not_a_crash(self):
        files = {"tasks.json": json.dumps(WORK_TASKS), "work.json": "[1, 2"}
        snap = build_snapshot(files, {}, NOW)
        self.assertNotIn("work", snap)
        self.assertTrue(any(e["file"] == "work.json" for e in snap["errors"]))


class ExportWorkTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.conn = db.connect(os.path.join(self.root, "board.db"))
        with db.txn(self.conn):
            self.conn.execute("INSERT INTO phases (id, name, status, position, data) VALUES ('P1', 'one', 'todo', 1,"
                              " '{}')")
            for wid, title in (("W2", "second"), ("W10", "tenth"), ("W1", "first")):
                self.conn.execute("INSERT INTO work_items (id, kind, title, outcome, status, prio, owner, phase,"
                                  " created, updated, accepted_at, reopened, data) VALUES (?, 'task', ?, '', 'Todo',"
                                  " 1, 'you', NULL, '2026-10-14T09:00:00Z', '2026-10-14T09:00:00Z', NULL, 0, '{}')",
                                  (wid, title))
            self.conn.execute("INSERT INTO tasks (id, phase, title, status, data, work_id) VALUES ('P1.1', 'P1', 'a',"
                              " 'todo', '{}', 'W1')")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_export_writes_work_json_with_items_and_links(self):
        out = os.path.join(self.root, "out")
        export.export(self.conn, out)
        with open(os.path.join(out, "work.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["schemaVersion"], 1)
        self.assertEqual([i["id"] for i in doc["items"]], ["W1", "W2", "W10"])   # numeric id order
        self.assertEqual(doc["items"][0]["prio"], 1)
        self.assertIsNone(doc["items"][0]["accepted"])
        self.assertEqual(doc["links"], {"P1.1": "W1"})
        self.assertEqual(doc["events"], [])
        self.assertIn("work.json", sorted(os.listdir(out)))

    def test_work_json_export_is_byte_identical_twice(self):
        out = os.path.join(self.root, "out")
        export.export(self.conn, out)
        with open(os.path.join(out, "work.json"), "rb") as fh:
            first = fh.read()
        export.export(self.conn, out)
        with open(os.path.join(out, "work.json"), "rb") as fh:
            self.assertEqual(first, fh.read())


if __name__ == "__main__":
    unittest.main()
