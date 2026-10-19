"""Tests for roadmap/store/db.py and roadmap/store/migrate.py. Temp dirs only; real docs/ is read, never written."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

from roadmap.store import db
from roadmap.store import migrate

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REAL_DOCS = os.path.join(REPO, "docs")


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _write_fixture(docs):
    os.makedirs(docs, exist_ok=True)
    tasks = {
        "schemaVersion": 1,
        "phases": [{"id": "P1", "name": "Phase one", "status": "partial"}],
        "tasks": [
            {"id": "P1.1", "phase": "P1", "title": "first", "status": "done", "tokensK": 70, "feats": ["F1"]},
            {"id": "P1.2", "phase": "P1", "title": "second", "status": "todo", "needsUser": True},
        ],
    }
    jobs = {"schemaVersion": 1, "jobs": [
        {"id": "j1", "task": "P1.1", "title": "job one", "model": "haiku", "status": "done",
         "started": "2026-10-13T10:00:00Z", "ended": "2026-10-13T10:05:00Z", "tokensK": 111.1},
    ]}
    head = [
        {"v": 1, "t": "e", "ts": "2026-10-15T06:00:00Z", "src": "import", "kind": "rule", "sum": "R", "id": "H1"},
        {"v": 1, "t": "u", "ts": "2026-10-15T06:01:00Z", "by": "me", "set": {"x": 1}, "id": "H1"},
    ]
    with open(os.path.join(docs, "tasks.json"), "w", encoding="utf-8") as fh:
        json.dump(tasks, fh)
    with open(os.path.join(docs, "jobs.json"), "w", encoding="utf-8") as fh:
        json.dump(jobs, fh)
    with open(os.path.join(docs, "head.jsonl"), "w", encoding="utf-8") as fh:
        for line in head:
            fh.write(json.dumps(line) + "\n")


class DbTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.path = os.path.join(self.dir, "board.db")

    def tearDown(self):
        self._tmp.cleanup()

    def _insert_task(self, conn, tid):
        conn.execute("INSERT INTO tasks (id, phase, title, status) VALUES (?, NULL, ?, 'todo')", (tid, tid))

    def test_wal_mode_and_pragmas_on(self):
        conn = db.connect(self.path)
        try:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], db.BUSY_TIMEOUT_MS)
            self.assertEqual(db.schema_version(conn), db.SCHEMA_VERSION)
        finally:
            conn.close()

    def test_two_writes_in_one_txn_roll_back_together(self):
        conn = db.connect(self.path)
        try:
            with self.assertRaises(RuntimeError):
                with db.txn(conn):
                    self._insert_task(conn, "A")
                    conn.execute("INSERT INTO meta (key, value) VALUES ('k', 'v')")
                    raise RuntimeError("boom")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0], 0)
            with db.txn(conn):
                self._insert_task(conn, "A")
                conn.execute("INSERT INTO meta (key, value) VALUES ('k', 'v')")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0], 1)
        finally:
            conn.close()

    def test_events_are_append_only(self):
        conn = db.connect(self.path)
        try:
            with db.txn(conn):
                conn.execute("INSERT INTO events (ts, kind) VALUES ('t', 'k')")
            with self.assertRaises(Exception):
                conn.execute("UPDATE events SET kind = 'x'")
            with self.assertRaises(Exception):
                conn.execute("DELETE FROM events")
        finally:
            conn.close()

    def test_schema_is_not_recreated_on_reconnect(self):
        db.connect(self.path).close()
        conn = db.connect(self.path)
        try:
            self.assertEqual(db.schema_version(conn), db.SCHEMA_VERSION)
        finally:
            conn.close()

    def test_newer_schema_is_refused(self):
        conn = db.connect(self.path)
        conn.execute("PRAGMA user_version = %d" % (db.SCHEMA_VERSION + 1))
        conn.close()
        with self.assertRaises(RuntimeError):
            db.connect(self.path)

    def test_other_process_write_lock_one_wins_other_retries(self):
        conn = db.connect(self.path)
        conn.close()
        child_code = (
            "import sys, time\n"
            "sys.path.insert(0, %r)\n"
            "from roadmap.store import db\n"
            "c = db.connect(%r)\n"
            "c.execute('BEGIN IMMEDIATE')\n"
            "c.execute(\"INSERT INTO tasks (id, title, status) VALUES ('CHILD', 'child', 'todo')\")\n"
            "print('locked', flush=True)\n"
            "time.sleep(1.0)\n"
            "c.execute('COMMIT')\n"
            "c.close()\n"
        ) % (REPO, self.path)
        mine = db.connect(self.path, busy_timeout_ms=50)  # before the child can hold the write lock
        child = subprocess.Popen([sys.executable, "-c", child_code], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "locked")
            try:
                def write_once():
                    with db.txn(mine):
                        self._insert_task(mine, "PARENT")

                with self.assertRaises(Exception) as ctx:
                    write_once()
                self.assertTrue(db.is_locked_error(ctx.exception))
                db.retry_locked(write_once, attempts=10, base_delay=0.1)
            finally:
                mine.close()
            self.assertEqual(child.wait(timeout=10), 0, child.stderr.read())
        finally:
            if child.poll() is None:
                child.kill()
            child.stdout.close()
            child.stderr.close()
        check = db.connect(self.path)
        try:
            ids = sorted(r[0] for r in check.execute("SELECT id FROM tasks"))
            self.assertEqual(ids, ["CHILD", "PARENT"])
            self.assertEqual(check.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            check.close()


class MigrateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.docs = os.path.join(self.dir, "docs")
        self.path = os.path.join(self.dir, "board.db")
        _write_fixture(self.docs)

    def tearDown(self):
        self._tmp.cleanup()

    def test_migrate_twice_gives_same_counts_and_checksums(self):
        sources = [os.path.join(self.docs, n) for n in ("tasks.json", "jobs.json", "head.jsonl")]
        before = [_sha(p) for p in sources]
        first = migrate.migrate_project(self.path, self.docs)
        second = migrate.migrate_project(self.path, self.docs)
        self.assertEqual(first["checksums"], second["checksums"])
        self.assertEqual(second["checksums"]["tasks"]["rows"], 2)
        self.assertEqual(second["checksums"]["phases"]["rows"], 1)
        self.assertEqual(second["checksums"]["jobs"]["rows"], 1)
        self.assertEqual(second["checksums"]["asks"]["rows"], 2)
        self.assertEqual(second["pruned"], {"tasks": 0, "jobs": 0, "asks": 0, "phases": 0})
        self.assertEqual([_sha(p) for p in sources], before)

    def test_migrate_keeps_extra_fields_and_prunes_removed_rows(self):
        migrate.migrate_project(self.path, self.docs)
        with open(os.path.join(self.docs, "tasks.json"), "w", encoding="utf-8") as fh:
            json.dump({"phases": [{"id": "P1", "name": "Phase one", "status": "partial"}],
                       "tasks": [{"id": "P1.1", "phase": "P1", "title": "first", "status": "done"}]}, fh)
        summary = migrate.migrate_project(self.path, self.docs)
        self.assertEqual(summary["pruned"]["tasks"], 1)
        conn = db.connect(self.path)
        try:
            row = conn.execute("SELECT title, status, data FROM tasks WHERE id = 'P1.1'").fetchone()
            self.assertEqual((row["title"], row["status"]), ("first", "done"))
            self.assertEqual(json.loads(row["data"]), {})
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
        finally:
            conn.close()

    def test_migrate_missing_files_is_empty_not_error(self):
        summary = migrate.migrate_project(self.path, os.path.join(self.dir, "nothing"))
        self.assertEqual(summary["checksums"]["tasks"]["rows"], 0)
        self.assertIsNone(summary["sources"]["tasks.json"])

    @unittest.skipUnless(os.path.exists(os.path.join(REAL_DOCS, "tasks.json")),
                         "board data is local and git-ignored")
    def test_smoke_real_docs_read_only(self):
        real_before = _sha(os.path.join(REAL_DOCS, "tasks.json"))
        summary = migrate.migrate_project(self.path, REAL_DOCS)
        with open(os.path.join(REAL_DOCS, "tasks.json"), encoding="utf-8") as fh:
            expected = len(json.load(fh)["tasks"])
        self.assertEqual(summary["checksums"]["tasks"]["rows"], expected)
        self.assertEqual(_sha(os.path.join(REAL_DOCS, "tasks.json")), real_before)


if __name__ == "__main__":
    unittest.main()
