"""Head ledger on the SQLite backend (roadmap/store/head_db.py) and the switch in services/head.py.

Runs in temp dirs only. The JSON backend stays the default: with no env and no project entry, capture writes head.jsonl
and no head.db appears.
"""

import datetime
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.services import head as store
from roadmap.store import db, head_db

NOW = datetime.datetime(2026, 10, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)


class HeadDbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="head-db-test-")
        self.data_dir = os.path.join(self.tmp, "docs")
        os.makedirs(self.data_dir)
        self.db_path = db.db_path(self.data_dir)
        self.env = mock.patch.dict(os.environ, {"ROADMAP_HOME": os.path.join(self.tmp, "home")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def events(self):
        conn = db.connect(self.db_path)
        try:
            return [dict(row) for row in conn.execute("SELECT rev, kind, entity_id, payload FROM events ORDER BY rev")]
        finally:
            conn.close()


class FingerprintTest(unittest.TestCase):
    def test_normalises_case_punctuation_and_whitespace(self):
        self.assertEqual(head_db.fingerprint("Ship  the API!"), head_db.fingerprint("ship the api"))
        self.assertNotEqual(head_db.fingerprint("ship the api"), head_db.fingerprint("ship the web"))


class LogTest(HeadDbCase):
    def test_same_text_twice_gives_one_hn(self):
        first = head_db.log(self.db_path, "Should we ship the API?", "question", "ship api?", now=NOW)
        again = head_db.log(self.db_path, "should we ship the API", "question", "ship api?",
                            now=NOW + datetime.timedelta(hours=1))
        self.assertEqual(first["id"], "H1")
        self.assertFalse(first["dup"])
        self.assertEqual(again["id"], "H1")
        self.assertTrue(again["dup"])

    def test_same_text_after_24h_is_a_new_entry(self):
        head_db.log(self.db_path, "Repeat me", "info", "repeat", now=NOW)
        later = head_db.log(self.db_path, "Repeat me", "info", "repeat", now=NOW + datetime.timedelta(hours=25))
        self.assertEqual(later["id"], "H2")
        self.assertFalse(later["dup"])

    def test_different_text_gives_two_hn(self):
        a = head_db.log(self.db_path, "first point", "info", "first", now=NOW)
        b = head_db.log(self.db_path, "second point", "info", "second", now=NOW)
        self.assertEqual((a["id"], b["id"]), ("H1", "H2"))

    def test_spool_roundtrip(self):
        head_db.spool_add(self.db_path, "hook line", src="hook", sid="abcd1234", now=NOW)
        pending = head_db.spool_pending(self.db_path)
        self.assertEqual([p["text"] for p in pending], ["hook line"])


class UpdateEventsTest(HeadDbCase):
    def test_triage_and_bind_append_events(self):
        head_db.log(self.db_path, "triage me", "info", "triage", now=NOW)
        head_db.update(self.db_path, "H1", by="head", sets={"status": "done"}, now=NOW)
        head_db.update(self.db_path, "H1", by="head", links=["+task:T1"], now=NOW)
        kinds = [e["kind"] for e in self.events()]
        self.assertEqual(kinds, ["head.triage", "head.bind"])
        self.assertEqual({e["entity_id"] for e in self.events()}, {"H1"})

    def test_update_of_missing_entry_is_refused_and_writes_nothing(self):
        with self.assertRaises(Exception) as ctx:
            head_db.update(self.db_path, "H9", by="head", sets={"status": "done"}, now=NOW)
        self.assertEqual(getattr(ctx.exception, "code", None), "not_found")
        self.assertEqual(self.events(), [])


class ServiceSwitchTest(HeadDbCase):
    def test_sqlite_switch_dedupes_capture(self):
        with mock.patch.dict(os.environ, {"ROADMAP_STORE": "sqlite"}):
            one = store.capture(self.data_dir, "Please check the deploy plan.", now=NOW)
            two = store.capture(self.data_dir, "please check the deploy plan", now=NOW)
        self.assertEqual(one["id"], two["id"])
        self.assertTrue(os.path.exists(self.db_path))

    def test_json_backend_is_the_default_and_untouched(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROADMAP_STORE", None)
            one = store.capture(self.data_dir, "same text", now=NOW)
            two = store.capture(self.data_dir, "same text", now=NOW)
        self.assertNotEqual(one["id"], two["id"])
        self.assertFalse(os.path.exists(self.db_path))
        with open(os.path.join(self.data_dir, store.FILE), encoding="utf-8") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(len([e for e in entries if e.get("t") == "e"]), 2)


if __name__ == "__main__":
    unittest.main()
