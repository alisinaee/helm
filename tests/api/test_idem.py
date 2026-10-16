"""POST /api/v1/cmd with an Idempotency-Key header (V3 Q2), sqlite switch on: the same key and body replays the first
reply and writes nothing again; the same key with a changed body or op is 409 conflict; a malformed key is 422.
Runs against a real server in a temp ROADMAP_HOME (the split-net fixture)."""

import os
from unittest import mock

from roadmap.store import db as store_db
from tests.api.test_cmd_route import CmdCase


class IdemTests(CmdCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"ROADMAP_STORE": "sqlite"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def keyed(self, key, body):
        return self.post(body, headers=self.write_headers(**{"Idempotency-Key": key}))

    def activity_count(self):
        conn = store_db.open_project(self.data_dir)
        try:
            return conn.execute("SELECT COUNT(*) FROM events WHERE kind = 'activity'").fetchone()[0]
        finally:
            conn.close()

    def test_same_key_and_body_replays_first_reply(self):
        body = {"op": "task.status", "args": {"id": "P1.1", "status": "done"}}
        first = self.keyed("key-same-1", body)
        self.assertEqual(first.status, 200, first.body[:300])
        self.assertEqual(self.status_of("P1.1"), "done")
        second = self.keyed("key-same-1", body)
        self.assertEqual(second.status, 200, second.body[:300])
        self.assertTrue(second.json().get("replayed"))
        self.assertEqual(second.json()["activity"], first.json()["activity"])
        self.assertEqual(second.json()["data"], first.json()["data"])
        self.assertEqual(self.activity_count(), 1)

    def test_changed_body_with_same_key_is_409_and_writes_nothing(self):
        self.keyed("key-conflict-1", {"op": "task.status", "args": {"id": "P1.1", "status": "done"}})
        res = self.keyed("key-conflict-1", {"op": "task.status", "args": {"id": "P1.1", "status": "todo"}})
        self.assertEqual(res.status, 409, res.body[:300])
        self.assertEqual(res.json()["error"]["code"], "conflict")
        self.assertEqual(self.status_of("P1.1"), "done")
        self.assertEqual(self.activity_count(), 1)

    def test_same_key_with_another_op_is_409(self):
        self.keyed("key-op-1", {"op": "task.status", "args": {"id": "P1.1", "status": "done"}})
        res = self.keyed("key-op-1", {"op": "task.rename", "args": {"id": "P1.1", "title": "Other"}})
        self.assertEqual(res.status, 409, res.body[:300])

    def test_new_key_applies_again(self):
        self.keyed("key-new-a", {"op": "task.status", "args": {"id": "P1.1", "status": "done"}})
        res = self.keyed("key-new-b", {"op": "task.status", "args": {"id": "P1.1", "status": "todo"}})
        self.assertEqual(res.status, 200, res.body[:300])
        self.assertFalse(res.json().get("replayed"))
        self.assertEqual(self.status_of("P1.1"), "todo")
        self.assertEqual(self.activity_count(), 2)

    def test_malformed_key_is_422(self):
        body = {"op": "task.status", "args": {"id": "P1.1", "status": "done"}}
        for bad in ("has space", "x" * 129, "tab\tkey"):
            res = self.keyed(bad, body)
            self.assertEqual(res.status, 422, bad)
        self.assertEqual(self.status_of("P1.1"), self.start_status)

    def test_no_key_behaves_as_before(self):
        body = {"op": "task.status", "args": {"id": "P1.1", "status": "done"}}
        self.assertEqual(self.post(body).status, 200)
        self.assertEqual(self.status_of("P1.1"), "done")


if __name__ == "__main__":
    import unittest
    unittest.main()
