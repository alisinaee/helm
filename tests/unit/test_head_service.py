"""HEAD-SPEC H3: the head store service. Append under the lock, spool adoption, ids unique under two threads, caps,
redaction before write, and the brief of at most 15 lines. Runs in a temp ROADMAP_HOME with a temp data folder."""

import json
import os
import shutil
import stat
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from roadmap.core import head
from roadmap.errors import RoadmapError
from roadmap.services import head as svc
from roadmap.store import lock

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


class HeadServiceCase(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.root = tempfile.mkdtemp(prefix="head-h3-")
        os.environ["ROADMAP_HOME"] = os.path.join(self.root, "home")
        self.data = os.path.join(self.root, "docs")
        os.makedirs(self.data)

    def tearDown(self):
        if self._saved_home is None:
            os.environ.pop("ROADMAP_HOME", None)
        else:
            os.environ["ROADMAP_HOME"] = self._saved_home
        shutil.rmtree(self.root, ignore_errors=True)

    def lines(self, name):
        path = os.path.join(self.data, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh.read().splitlines() if x.strip()]

    def raw(self, name):
        with open(os.path.join(self.data, name), encoding="utf-8") as fh:
            return fh.read()

    def entry_ids(self):
        return [r["id"] for r in self.lines(svc.FILE) if r.get("t") == "e"]


class AppendUnderLock(HeadServiceCase):
    def test_capture_appends_entry_and_text_with_ids_in_order(self):
        first = svc.capture(self.data, "Please fix the export button", session_id="sess-1", acct="B", now=NOW)
        second = svc.capture(self.data, "Never push to main", session_id="sess-1", acct="B", now=NOW)
        self.assertEqual((first["id"], second["id"]), ("H1", "H2"))
        self.assertEqual(first["status"], "logged")
        self.assertEqual(self.entry_ids(), ["H1", "H2"])
        texts = self.lines(svc.TEXT_FILE)
        self.assertEqual([t["id"] for t in texts], ["H1", "H2"])
        self.assertEqual(texts[0]["text"], "Please fix the export button")

    def test_entry_fields_follow_the_record_shape(self):
        svc.capture(self.data, "Never push to main", session_id="sess-1", acct="B", now=NOW)
        rec = self.lines(svc.FILE)[0]
        self.assertEqual(rec["v"], 1)
        self.assertEqual(rec["t"], "e")
        self.assertEqual(rec["ts"], "2026-10-15T12:00:00Z")
        self.assertEqual(rec["src"], "hook")
        self.assertEqual(rec["acct"], "B")
        self.assertEqual(rec["kind"], "rule?")
        self.assertEqual(rec["len"], len("Never push to main"))
        self.assertTrue(rec["h"].startswith("sha1:") and len(rec["h"]) == 17)
        self.assertEqual(len(rec["sid"]), 8)
        self.assertNotIn("sess-1", json.dumps(rec))

    def test_secrets_are_masked_before_any_write(self):
        svc.capture(self.data, "deploy with password=hunter2 and mail ali@example.com", session_id="s", now=NOW)
        raw = self.raw(svc.FILE)
        raw_text = self.raw(svc.TEXT_FILE)
        for blob in (raw, raw_text):
            self.assertNotIn("hunter2", blob)
            self.assertNotIn("ali@example.com", blob)
        self.assertIn("[secret]", raw_text)
        self.assertIn("[email]", raw_text)

    def test_busy_lock_spools_then_next_writer_adopts_in_order(self):
        with lock.locked(self.data):
            spooled = svc.capture(self.data, "first while busy", session_id="s", timeout=0.05, now=NOW)
            self.assertEqual(spooled["status"], "spooled")
            self.assertIsNone(spooled["id"])
            with self.assertRaises(RoadmapError) as raised:
                with lock.locked(self.data, 0.01):
                    pass
            self.assertEqual(raised.exception.code, "locked")
        self.assertTrue(os.path.exists(os.path.join(self.data, svc.SPOOL_FILE)))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.data, svc.SPOOL_FILE)).st_mode), 0o600)
        self.assertEqual(self.lines(svc.FILE), [])
        after = svc.capture(self.data, "second, lock free", session_id="s", now=NOW)
        self.assertEqual(after["id"], "H2")
        self.assertEqual(self.entry_ids(), ["H1", "H2"])
        self.assertEqual([t["text"] for t in self.lines(svc.TEXT_FILE)],
                         ["first while busy", "second, lock free"])
        self.assertEqual(self.raw(svc.SPOOL_FILE), "")

    def test_spool_survives_update_and_session_writers(self):
        with lock.locked(self.data):
            svc.capture(self.data, "spooled ask", session_id="s", timeout=0.05, now=NOW)
        svc.session(self.data, "claim", session_id="s", acct="B", model="Opus 5.5", now=NOW)
        self.assertEqual(self.entry_ids(), ["H1"])


class IdsUnderThreads(HeadServiceCase):
    def test_ids_are_unique_when_two_threads_capture(self):
        errors = []

        def worker(tag):
            try:
                for n in range(25):
                    svc.capture(self.data, "thread " + tag + " message " + str(n), session_id=tag, now=NOW)
            except Exception as exc:  # collected and asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        ids = self.entry_ids()
        self.assertEqual(len(ids), 50)
        self.assertEqual(len(set(ids)), 50)
        self.assertEqual(sorted(ids, key=lambda x: int(x[1:])), ["H%d" % n for n in range(1, 51)])


class Caps(HeadServiceCase):
    def test_verbatim_text_is_cut_at_8000_and_summary_at_100(self):
        long = "please fix the thing " * 600
        out = svc.capture(self.data, long, session_id="s", now=NOW)
        stored = svc.text_of(self.data, out["id"])
        self.assertEqual(len(stored), 8000)
        self.assertLessEqual(len(self.lines(svc.FILE)[0]["sum"]), 100)

    def test_control_characters_are_stripped(self):
        svc.capture(self.data, "fix\x00 the\x07 button", session_id="s", now=NOW)
        self.assertEqual(svc.text_of(self.data, "H1"), "fix the button")

    def test_entry_cap_refuses_new_entries(self):
        with mock.patch.object(svc, "MAX_ENTRIES", 2):
            svc.capture(self.data, "one two", session_id="s", now=NOW)
            svc.capture(self.data, "three four", session_id="s", now=NOW)
            with self.assertRaises(RoadmapError) as raised:
                svc.capture(self.data, "five six", session_id="s", now=NOW)
        self.assertEqual(raised.exception.code, "cap")
        self.assertEqual(self.entry_ids(), ["H1", "H2"])

    def test_update_note_cut_and_link_limits(self):
        svc.capture(self.data, "one two", session_id="s", now=NOW)
        rec = svc.update(self.data, "H1", by="head", sets={"kind": "bug"}, note="n" * 500, now=NOW)
        self.assertEqual(len(rec["note"]), 160)
        with self.assertRaises(RoadmapError):
            svc.update(self.data, "H1", by="head", links=["+task:R%d.1" % n for n in range(7)])
        with self.assertRaises(RoadmapError):
            svc.update(self.data, "H1", by="head", links=["task:R7.31"])
        with self.assertRaises(RoadmapError):
            svc.update(self.data, "H1", by="agent", sets={"text": "rewritten"})

    def test_update_rejects_unknown_entry_and_bad_status(self):
        svc.capture(self.data, "one two", session_id="s", now=NOW)
        with self.assertRaises(RoadmapError) as raised:
            svc.update(self.data, "H9", by="person", sets={"status": "done"})
        self.assertEqual(raised.exception.code, "not_found")
        with self.assertRaises(RoadmapError):
            svc.update(self.data, "H1", by="person", sets={"status": "doing"})


class FoldAndBrief(HeadServiceCase):
    def test_person_done_update_folds_into_rows(self):
        svc.capture(self.data, "one two", session_id="s", now=NOW)
        svc.update(self.data, "H1", by="person", sets={"status": "done"}, now=NOW)
        self.assertEqual(svc.rows(self.data, now=NOW)[0]["status"], "done")

    def test_unknown_version_lines_are_skipped(self):
        svc.capture(self.data, "one two", session_id="s", now=NOW)
        with open(os.path.join(self.data, svc.FILE), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"v": 2, "t": "e", "id": "H7", "ts": "2026-10-15T12:00:00Z"}) + "\n")
        self.assertEqual([r["id"] for r in svc.rows(self.data, now=NOW)], ["H1"])

    def test_brief_is_at_most_15_lines_with_many_entries(self):
        for n in range(40):
            svc.capture(self.data, "please do thing number %d now" % n, session_id="s", now=NOW)
        svc.capture(self.data, "we decided to go with the table layout", session_id="s", now=NOW)
        svc.update(self.data, "H41", by="head", sets={"kind": "decision", "sum": "table layout"}, now=NOW)
        svc.update(self.data, "H3", by="person", sets={"status": "needs-you"}, now=NOW)
        lines = svc.brief(self.data, now=NOW)
        self.assertLessEqual(len(lines), 15)
        self.assertTrue(lines[0].startswith("head: "))
        self.assertIn("needs you:", lines)

    def test_brief_on_empty_folder(self):
        lines = svc.brief(self.data, now=NOW)
        self.assertEqual(lines, ["head: 0 open, 0 unhandled, 0 doing, 0 needs-you"])

    def test_brief_shows_age_of_unhandled(self):
        old = NOW - timedelta(hours=3)
        svc.capture(self.data, "please do the old thing", session_id="s", now=old)
        lines = svc.brief(self.data, now=NOW)
        self.assertIn("(oldest 3h)", lines[0])

    def test_session_claim_is_written_with_usage(self):
        rec = svc.session(self.data, "claim", session_id="s", acct="B", model="Opus 5.5",
                          usage={"h5": 41, "wk": 63, "junk": 9}, now=NOW)
        self.assertEqual(rec["usage"], {"h5": 41, "wk": 63})
        self.assertEqual(self.lines(svc.FILE)[-1]["ev"], "claim")

    def test_bad_inputs_are_usage_errors(self):
        with self.assertRaises(RoadmapError):
            svc.capture(self.data, "   ", session_id="s", now=NOW)
        with self.assertRaises(RoadmapError):
            svc.capture(self.data, "hi there", src="phone", now=NOW)
        with self.assertRaises(RoadmapError):
            svc.session(self.data, "boot", session_id="s", now=NOW)


class Hashing(unittest.TestCase):
    def test_session_key_hides_the_raw_id(self):
        self.assertEqual(len(svc.session_key("abc")), 8)
        self.assertIsNone(svc.session_key(""))
        self.assertNotIn("abc", svc.session_key("abc"))

    def test_fold_kind_table_is_reachable(self):
        self.assertEqual(head.guess_kind("this is broken"), "bug?")


if __name__ == "__main__":
    unittest.main()
