"""R10.10 C1: the supervisor tick on a JSON-store project folds asks through the JSON path and never creates or reads
docs/roadmap.db. Temp ROADMAP_HOME and temp docs folder only; nothing touches the real home or the network.
"""

import os

from roadmap.services import head as head_svc
from roadmap.services import supervisor
from roadmap.store import schema
from tests.unit.test_store_support import HomeCase


class SupervisorJsonTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.data = os.path.join(self.tmp, "docs")
        os.makedirs(self.data)
        self.db_path = os.path.join(self.data, "roadmap.db")

    def write_tasks(self, status):
        task = {"id": "R7.44", "phase": "R7", "title": "task R7.44", "status": status, "tokensK": 0,
                "model": "haiku", "thinking": "medium", "refs": ["commit:" + "a" * 40]}
        schema.write_data("tasks", os.path.join(self.data, "tasks.json"), {"phases": [], "tasks": [task]})

    def ask(self, text, task_ids):
        rec = head_svc.capture(self.data, text, src="cli", kind="ask")
        head_svc.update(self.data, rec["id"], by="person", links=["+task:" + t for t in task_ids])
        return rec["id"]

    def row(self, eid):
        return next(r for r in head_svc.rows(self.data) if r["id"] == eid)

    def test_json_project_tick_creates_no_db_and_folds_done_task_ask(self):
        self.write_tasks("doing")
        eid = self.ask("export and import the roadmap", ["R7.44"])
        self.write_tasks("done")
        report = supervisor.tick(self.data)
        self.assertFalse(os.path.exists(self.db_path))
        self.assertTrue(report["ran"])
        self.assertEqual(report["closed_asks"], [eid])
        self.assertEqual(self.row(eid)["status"], "done")
        with open(os.path.join(self.data, "head.jsonl"), encoding="utf-8") as fh:
            self.assertIn("auto: R7.44 " + "a" * 7, fh.read())
        self.assertEqual(supervisor.tick(self.data)["closed_asks"], [])
        self.assertFalse(os.path.exists(self.db_path))

    def test_json_project_tick_leaves_ask_open_while_task_is_not_done(self):
        self.write_tasks("doing")
        eid = self.ask("keep the export open", ["R7.44"])
        report = supervisor.tick(self.data)
        self.assertEqual(report["closed_asks"], [])
        self.assertNotEqual(self.row(eid)["status"], "done")
        self.assertFalse(os.path.exists(self.db_path))


if __name__ == "__main__":
    import unittest
    unittest.main()
