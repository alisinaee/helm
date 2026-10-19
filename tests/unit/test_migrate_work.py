"""Tests for the R7 Work item migration (roadmap/store/migrate.py, docs/work-map-R7.json).

Reads a frozen copy of the R7 board (tests/fixtures/board-r7: tasks.json, head.jsonl, work-map-R7.json) and copies
it into a temp dir. The repo board was emptied on 2026-10-19; the fixture keeps the data these tests were written for.
"""

import json
import os
import re
import shutil
import tempfile
import unittest

from roadmap.store import db, migrate

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REAL_DOCS = os.path.join(REPO, "tests", "fixtures", "board-r7")
FIXTURES = os.path.join(REPO, "tests", "fixtures")
SOURCES = ("tasks.json", "jobs.json", "head.jsonl", "work-map-R7.json")


def _load(name):
    with open(os.path.join(REAL_DOCS, name), encoding="utf-8") as fh:
        return json.load(fh)


class MigrateWorkTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.docs = os.path.join(self._tmp.name, "docs")
        os.makedirs(self.docs)
        for name in SOURCES:
            src = os.path.join(REAL_DOCS, name)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(self.docs, name))
        self.map = _load("work-map-R7.json")
        self.tasks = _load("tasks.json")["tasks"]
        self.conn = db.open_project(self._tmp.name)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def _migrate(self):
        return migrate.migrate(self.conn, self.docs)

    def _r7_ids(self):
        """The R7 ids the map was built against (a fixture snapshot, so later live rows do not break this test)."""
        with open(os.path.join(FIXTURES, "r7_work_map_ids.json"), encoding="utf-8") as fh:
            return set(json.load(fh)["ids"])

    def test_every_r7_row_mapped(self):
        self.assertEqual(set(self.map["tasks"]), self._r7_ids())
        self.assertEqual(len(self._r7_ids()), len(self.map["tasks"]))
        live = {t["id"] for t in self.tasks if t["id"].startswith("R7.")}
        self.assertLessEqual(self._r7_ids(), live, "map references an R7 row that no longer exists")
        for tid, wid in self.map["tasks"].items():
            self.assertIn(wid, self.map["items"], tid)
        self.assertEqual(len(self.map["items"]), 15)
        for wid, item in self.map["items"].items():
            self.assertLessEqual(len(item["title"]), 60, wid)
            self.assertTrue(item.get("outcome"), wid)

    def test_agent_tasks_carry_work_id(self):
        self._migrate()
        rows = dict(self.conn.execute("SELECT id, work_id FROM tasks").fetchall())
        for tid, wid in self.map["tasks"].items():
            self.assertEqual(rows[tid], wid, tid)

    def test_work_items_created_and_refs_resolve(self):
        self._migrate()
        items = {r[0]: r[1] for r in self.conn.execute("SELECT id, title FROM work_items")}
        self.assertEqual(set(items), set(self.map["items"]))
        for wid, item in self.map["items"].items():
            self.assertEqual(items[wid], item["title"])
        dangling = self.conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE work_id IS NOT NULL AND work_id NOT IN (SELECT id FROM work_items)"
        ).fetchone()[0]
        self.assertEqual(dangling, 0)

    def test_binds_lifted_and_task_ref_kept(self):
        summary = self._migrate()
        bind = re.compile(r"^([+-]?)task:(R7\.\d+)$")
        expected = 0
        with open(os.path.join(self.docs, "head.jsonl"), encoding="utf-8") as fh:
            lines = [json.loads(x) for x in fh if x.strip()]
        for line in lines:
            # one work ref per Work item per row, however many of its tasks the row binds
            works = {self.map["tasks"][m.group(2)] for m in
                     (bind.match(e) for e in line.get("link") or []) if m and m.group(2) in self.map["tasks"]}
            expected += len(works)
        self.assertGreater(expected, 0)
        self.assertEqual(summary["work"]["binds_lifted"], expected)
        lifted = 0
        for (data,) in self.conn.execute("SELECT data FROM asks"):
            links = json.loads(data).get("link") or []
            for wid in {self.map["tasks"][m.group(2)] for m in
                        (bind.match(e) for e in links) if m and m.group(2) in self.map["tasks"]}:
                refs = [e for e in links if e.endswith("work:" + wid)]
                self.assertEqual(len(refs), 1, wid)
                self.assertIn(wid, self.map["items"])  # the work ref resolves to a Work item
                lifted += 1
        self.assertEqual(lifted, expected)

    def test_legacy_all_done_items_start_done(self):
        self._migrate()
        state = {t["id"]: t["status"] for t in self.tasks}
        status = dict(self.conn.execute("SELECT id, status FROM work_items").fetchall())
        accepted = dict(self.conn.execute("SELECT id, accepted_at FROM work_items").fetchall())
        for wid in self.map["items"]:
            tids = [t for t, w in self.map["tasks"].items() if w == wid]
            if all(state[t] == "done" for t in tids):
                self.assertEqual(status[wid], "Done", wid)
                self.assertEqual(accepted[wid], "migrate", wid)
            else:
                self.assertIn(status[wid], ("Todo", "Doing"), wid)
                self.assertIsNone(accepted[wid], wid)

    def test_migrate_twice_same(self):
        self._migrate()
        first = (db.table_checksums(self.conn),
                 self.conn.execute("SELECT * FROM work_items ORDER BY id").fetchall(),
                 self.conn.execute("SELECT id, work_id FROM tasks ORDER BY id").fetchall())
        self._migrate()
        second = (db.table_checksums(self.conn),
                  self.conn.execute("SELECT * FROM work_items ORDER BY id").fetchall(),
                  self.conn.execute("SELECT id, work_id FROM tasks ORDER BY id").fetchall())
        self.assertEqual([tuple(r) for r in first[1]], [tuple(r) for r in second[1]])
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[2], second[2])

    def test_person_accept_survives_rerun(self):
        self._migrate()
        self.conn.execute("UPDATE work_items SET status = 'Done', accepted_at = '2026-10-16T09:00:00Z'"
                          " WHERE id = 'W5'")
        self._migrate()
        row = self.conn.execute("SELECT accepted_at FROM work_items WHERE id = 'W5'").fetchone()
        self.assertEqual(row[0], "2026-10-16T09:00:00Z")

    def test_refuses_map_with_unknown_task(self):
        bad = dict(self.map, tasks=dict(self.map["tasks"], **{"R7.999": "W1"}))
        with open(os.path.join(self.docs, "work-map-R7.json"), "w", encoding="utf-8") as fh:
            json.dump(bad, fh)
        from roadmap.errors import RoadmapError
        with self.assertRaises(RoadmapError):
            self._migrate()


if __name__ == "__main__":
    unittest.main()
