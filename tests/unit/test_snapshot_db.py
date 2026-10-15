"""R7.94 (W4): the snapshot read from the SQLite store behind the switch equals the JSON path.

Checks: with ROADMAP_STORE=sqlite the snapshot built from a migrated store equals the one built from the JSON files
(time fields left out); loader.revision is the store's integer rev and bumps after a write; a write that is still
open in another connection is not seen, and is seen whole once committed. Runs in a temp ROADMAP_HOME (ControlCase).
"""

import datetime
import json
import os
import unittest

from roadmap.services import loader
from roadmap.store import db, events, migrate
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
        self.dbp = os.path.join(self.docs, "head.db")
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


if __name__ == "__main__":
    unittest.main()
