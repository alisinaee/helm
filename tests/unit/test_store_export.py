"""Tests for roadmap/store/export.py: JSON -> db (migrate) -> JSON (export) round trip, determinism, atomic writes.

Temp dirs only; the real docs/ is never written."""

import json
import os
import tempfile
import unittest

from roadmap.store import db
from roadmap.store import export
from roadmap.store import migrate

TASKS = {
    "schemaVersion": 1,
    "phases": [
        {"id": "P1", "name": "Phase one", "status": "partial"},
        {"id": "P2", "name": "Phase two", "status": "todo"},
    ],
    "tasks": [
        {"id": "P1.1", "phase": "P1", "title": "first", "status": "done", "tokensK": 70, "feats": ["F1"]},
        {"id": "P1.2", "phase": "P1", "title": "second", "status": "todo", "needsUser": True},
        {"id": "P2.1", "phase": "P2", "title": "third", "status": "partial", "verify": "commit"},
    ],
}
JOBS = {
    "schemaVersion": 1,
    "jobs": [
        {"id": "j1", "task": "P1.1", "title": "job one", "model": "haiku", "status": "done",
         "started": "2026-10-13T10:00:00Z", "ended": "2026-10-13T10:05:00Z", "tokensK": 111.1},
        {"id": "j2", "task": "P2.1", "title": "job two", "model": "sonnet", "status": "running",
         "started": "2026-10-14T09:00:00Z", "ended": "2026-10-14T09:30:00Z", "files": ["a.py"]},
    ],
}
HEAD = [
    {"v": 1, "t": "e", "ts": "2026-10-15T06:00:00Z", "src": "import", "kind": "rule", "sum": "R", "id": "H1"},
    {"v": 1, "t": "u", "ts": "2026-10-15T06:01:00Z", "by": "me", "set": {"x": 1, "ünï": "é"}, "id": "H1"},
]


def _write_source(docs):
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "tasks.json"), "w", encoding="utf-8") as fh:
        json.dump(TASKS, fh, indent=4)
    with open(os.path.join(docs, "jobs.json"), "w", encoding="utf-8") as fh:
        json.dump(JOBS, fh)
    with open(os.path.join(docs, "head.jsonl"), "w", encoding="utf-8") as fh:
        for line in HEAD:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


class ExportRoundTripTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.src = os.path.join(self.root, "src")
        self.out = os.path.join(self.root, "out")
        _write_source(self.src)
        self.conn = db.connect(os.path.join(self.root, "board.db"))
        migrate.migrate(self.conn, self.src)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_round_trip_matches_source_shapes(self):
        export.export(self.conn, self.out)
        self.assertEqual(_read_json(os.path.join(self.out, "tasks.json")), TASKS)
        self.assertEqual(_read_json(os.path.join(self.out, "jobs.json")), JOBS)
        with open(os.path.join(self.out, "head.jsonl"), "r", encoding="utf-8") as fh:
            lines = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(lines, HEAD)

    def test_export_is_byte_identical_twice(self):
        export.export(self.conn, self.out)
        first = {n: _read_bytes(os.path.join(self.out, n)) for n in export.FILES_ALL}
        export.export(self.conn, self.out)
        second = {n: _read_bytes(os.path.join(self.out, n)) for n in export.FILES_ALL}
        self.assertEqual(first, second)

    def test_output_format_sorted_keys_and_trailing_newline(self):
        export.export(self.conn, self.out)
        for name in export.FILES_ALL:
            data = _read_bytes(os.path.join(self.out, name))
            self.assertTrue(data.endswith(b"\n"), name)
            self.assertFalse(data.endswith(b"\n\n"), name)
        tasks_text = _read_bytes(os.path.join(self.out, "tasks.json")).decode("utf-8")
        self.assertEqual(tasks_text, json.dumps(TASKS, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
        head_text = _read_bytes(os.path.join(self.out, "head.jsonl")).decode("utf-8")
        for line in head_text.splitlines():
            self.assertEqual(line, json.dumps(json.loads(line), sort_keys=True, ensure_ascii=False,
                                              separators=(",", ":")))

    def test_edit_in_db_changes_output_and_leaves_no_temp_files(self):
        export.export(self.conn, self.out)
        with db.txn(self.conn):
            self.conn.execute("UPDATE tasks SET status = 'done' WHERE id = 'P1.2'")
        export.export(self.conn, self.out)
        tasks = _read_json(os.path.join(self.out, "tasks.json"))
        self.assertEqual([t["status"] for t in tasks["tasks"] if t["id"] == "P1.2"], ["done"])
        self.assertEqual(sorted(os.listdir(self.out)), sorted(export.FILES_ALL))


if __name__ == "__main__":
    unittest.main()
