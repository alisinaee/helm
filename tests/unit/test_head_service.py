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

from roadmap.core import head, secrets
from roadmap.errors import RoadmapError
from roadmap.services import head as svc, tasks
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


class VerifiedGapTests(HeadServiceCase):
    """Test gaps confirmed in docs/reviews/agy-head-testgaps-core.md (rows for roadmap/services/head.py) and the
    scrub rows of docs/reviews/agy-head-testgaps-ops.md that the head store relies on."""

    def _link(self, name):
        os.symlink(os.path.join(self.root, name), os.path.join(self.data, name))

    def test_next_id_refuses_when_h9999_is_taken(self):
        with self.assertRaises(RoadmapError) as raised:
            svc._next_id([{"t": "e", "id": "H9999"}])
        self.assertEqual(raised.exception.code, "cap")
        self.assertEqual(str(raised.exception), "head ids are used up (H9999)")

    def test_spool_append_refuses_a_symlink_and_leaves_the_target(self):
        target = os.path.join(self.root, "elsewhere.txt")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("keep\n")
        os.symlink(target, os.path.join(self.data, svc.SPOOL_FILE))
        with self.assertRaises(RoadmapError) as raised:
            svc._spool_append(self.data, {"e": {}, "text": "x"})
        self.assertEqual(raised.exception.code, "invalid_data")
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep\n")

    def test_adopt_refuses_a_symlinked_spool(self):
        target = os.path.join(self.root, "spool-target.jsonl")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("")
        os.symlink(target, os.path.join(self.data, svc.SPOOL_FILE))
        with lock.locked(self.data):
            with self.assertRaises(RoadmapError) as raised:
                svc._adopt_locked(self.data)
        self.assertEqual(raised.exception.code, "invalid_data")

    def test_adopt_skips_corrupt_lines_and_keeps_the_valid_payload(self):
        entry = {"v": 1, "t": "e", "ts": "2026-10-15T12:00:00Z", "src": "hook", "sid": "abcd1234", "acct": None,
                 "kind": "ask?", "sum": "fix the export", "len": 16, "h": "sha1:0123456789ab"}
        lines = ["not json", "[1, 2]", json.dumps({"e": "not a dict", "text": "x"}),
                 json.dumps({"e": entry, "text": "fine text"})]
        with open(os.path.join(self.data, svc.SPOOL_FILE), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        with lock.locked(self.data):
            adopted = svc._adopt_locked(self.data)
        self.assertEqual(adopted, 1)
        self.assertEqual(self.entry_ids(), ["H1"])
        self.assertEqual(svc.text_of(self.data, "H1"), "fine text")

    def test_capture_stores_a_truncated_from_id(self):
        out = svc.capture(self.data, "split part one", session_id="s", from_id="H1234567890123", now=NOW)
        self.assertEqual(self.lines(svc.FILE)[0]["from"], "H12345678901")
        self.assertEqual(out["status"], "logged")

    def test_capture_uses_explicit_kind_and_summary(self):
        out = svc.capture(self.data, "Please fix the export button", session_id="s", kind="bug",
                          sum_text="Export button broken", now=NOW)
        self.assertEqual((out["kind"], out["sum"]), ("bug", "Export button broken"))
        rec = self.lines(svc.FILE)[0]
        self.assertEqual((rec["kind"], rec["sum"]), ("bug", "Export button broken"))

    def test_update_rejects_a_kind_outside_kinds(self):
        svc.capture(self.data, "one two", session_id="s", now=NOW)
        with self.assertRaises(RoadmapError) as raised:
            svc.update(self.data, "H1", by="head", sets={"kind": "nonsense"}, now=NOW)
        self.assertEqual(raised.exception.code, "usage")

    def test_update_rejects_a_bad_link_ref(self):
        svc.capture(self.data, "one two", session_id="s", now=NOW)
        for bad in ("+badkind:1", "+task:"):
            with self.assertRaises(RoadmapError) as raised:
                svc.update(self.data, "H1", by="head", links=[bad], now=NOW)
            self.assertEqual(raised.exception.code, "usage", bad)

    def test_update_note_is_scrubbed_before_it_is_written(self):
        svc.capture(self.data, "one two", session_id="s", now=NOW)
        rec = svc.update(self.data, "H1", by="person", note="token=hunter2 for the export", now=NOW)
        self.assertNotIn("hunter2", rec["note"])
        self.assertIn("[secret]", rec["note"])
        self.assertNotIn("hunter2", self.raw(svc.FILE))

    def test_session_drops_boolean_usage_and_keeps_numbers(self):
        rec = svc.session(self.data, "claim", session_id="s", usage={"h5": True, "wk": 50}, now=NOW)
        self.assertEqual(rec["usage"], {"wk": 50})

    def test_text_of_is_none_for_unknown_and_latest_line_wins(self):
        svc.capture(self.data, "first wording here", session_id="s", now=NOW)
        self.assertIsNone(svc.text_of(self.data, "H77"))
        with open(os.path.join(self.data, svc.TEXT_FILE), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": "H1", "text": "newer wording"}) + "\n")
        self.assertEqual(svc.text_of(self.data, "H1"), "newer wording")

    def test_age_text_units(self):
        self.assertEqual(svc._age_text(25), "25m")
        self.assertEqual(svc._age_text(90), "1h")
        self.assertEqual(svc._age_text(2880), "2d")

    def test_brief_lists_open_asks_oldest_first_and_skips_closed_and_needs_you(self):
        svc.capture(self.data, "please do beta thing", session_id="s", now=NOW - timedelta(hours=1))
        svc.capture(self.data, "please do alpha thing", session_id="s", now=NOW - timedelta(hours=3))
        svc.capture(self.data, "please do gamma thing", session_id="s", now=NOW - timedelta(hours=2))
        svc.capture(self.data, "please do delta thing", session_id="s", now=NOW - timedelta(hours=4))
        svc.update(self.data, "H3", by="person", sets={"status": "needs-you"}, now=NOW)
        svc.update(self.data, "H4", by="person", sets={"status": "done"}, now=NOW)
        lines = svc.brief(self.data, now=NOW)
        start = lines.index("open asks, oldest first:")
        asks = [line.split()[0] for line in lines[start + 1:] if line.startswith("  ")]
        self.assertEqual(asks, ["H2", "H1"])
        self.assertTrue(any(line.startswith("  H3 ") for line in lines))

    def test_brief_leaves_out_old_and_declined_decisions(self):
        svc.capture(self.data, "we decided to go with the table layout", session_id="s",
                    now=NOW - timedelta(days=10))
        svc.capture(self.data, "always run the tests before push", session_id="s", now=NOW - timedelta(days=1))
        svc.capture(self.data, "never commit secrets to git", session_id="s", now=NOW - timedelta(days=1))
        svc.update(self.data, "H2", by="person", sets={"status": "declined"}, now=NOW)
        lines = svc.brief(self.data, now=NOW)
        self.assertIn("decisions and rules, 7 days:", lines)
        self.assertFalse(any(line.startswith("  H1 ") for line in lines))
        self.assertFalse(any(line.startswith("  H2 ") for line in lines))
        self.assertTrue(any(line.startswith("  H3 ") for line in lines))


class BindToDoneTask(HeadServiceCase):
    """R10.27: an ask bound to a task that is already done stays open; a task done after the bind closes it."""

    def set_task(self, status):
        tasks.apply(self.data, [
            {"kind": "phase", "line": 1, "id": "R10", "name": "P", "status": None},
            {"kind": "task", "line": 2, "id": "R10.27", "phase": "R10", "title": "fix", "status": status,
             "tokensK": 0, "thinking": "medium", "model": "haiku", "needsUser": None, "check": None,
             "checkK": None, "note": None, "after": None, "feats": None},
        ])

    def row_status(self, eid):
        return next(r for r in svc.rows(self.data) if r["id"] == eid)["status"]

    def test_new_ask_bound_to_a_done_task_stays_open(self):
        self.set_task("done")
        eid = svc.capture(self.data, "a new ask bound to a done task", kind="ask")["id"]
        svc.update(self.data, eid, by="head", links=["+task:R10.27"])
        self.assertEqual(svc.fold_asks(self.data), [])
        self.assertEqual(self.row_status(eid), "bound")

    def test_ask_bound_to_a_task_that_finishes_later_closes(self):
        self.set_task("todo")
        eid = svc.capture(self.data, "an ask bound before the task is done", kind="ask")["id"]
        svc.update(self.data, eid, by="head", links=["+task:R10.27"])
        self.set_task("done")
        self.assertEqual(svc.fold_asks(self.data), [eid])
        self.assertEqual(self.row_status(eid), "done")


class ScrubVectors(unittest.TestCase):
    """Scrub rules whose vectors were missing from tests/unit/test_secrets_scrub.py (section 7 of HEAD-SPEC)."""

    def test_slack_and_github_token_prefixes_are_masked(self):
        for token in ("xoxp-1234567890-abcdefghij", "xoxa-1234567890-abcdefghij", "xoxs-1234567890-abcdefghij"):
            self.assertEqual(secrets.scrub("slack " + token + " ok"), "slack [secret] ok", token)
        for prefix in ("gho_", "ghs_", "ghu_", "ghr_"):
            self.assertEqual(secrets.scrub(prefix + "a" * 20), "[secret]", prefix)

    def test_keyed_assignments_for_passwd_pwd_access_key_and_apikey(self):
        cases = {
            "passwd=hunter2 ok": "passwd=[secret] ok",
            "pwd: abc123 ok": "pwd: [secret] ok",
            "access_key=abc123 ok": "access_key=[secret] ok",
            "access-key: xyz789 ok": "access-key: [secret] ok",
            "apikey=abcdef ok": "apikey=[secret] ok",
        }
        for text, want in cases.items():
            self.assertEqual(secrets.scrub(text), want, text)

    def test_hyphen_grouped_and_13_digit_card_numbers_are_masked(self):
        self.assertEqual(secrets.scrub("card 4111-1111-1111-1111 ok"), "card [number] ok")
        self.assertEqual(secrets.scrub("acct 1234567890123 ok"), "acct [number] ok")


if __name__ == "__main__":
    unittest.main()


class ReplyAndAssets(HeadServiceCase):
    """HEAD-SPEC section 13: assets are stored with the text, the reply is a text-file line that the last write wins,
    and details_of reads both back."""

    def test_assets_are_text_only_masked_unique_and_capped(self):
        names = ["a.png", "a.png", 7, "b\x01.pdf", "x" * 300] + ["f%d.txt" % i for i in range(30)]
        out = svc.clean_assets(names)
        self.assertEqual(out[:3], ["a.png", "b.pdf", "x" * 200])
        self.assertEqual(len(out), 20)
        self.assertEqual(svc.clean_assets("not a list"), [])

    def test_capture_stores_assets_and_details_reads_them_back(self):
        out = svc.capture(self.data, "Please check the board shot", session_id="s1", src="hook",
                          assets=["shot.png"], now=NOW)
        details = svc.details_of(self.data, out["id"])
        self.assertEqual(details, {"text": "Please check the board shot", "reply": None, "assets": ["shot.png"]})

    def test_set_reply_is_redacted_and_the_last_reply_wins(self):
        out = svc.capture(self.data, "Please check the board shot", session_id="s1", src="hook", now=NOW)
        svc.set_reply(self.data, out["id"], "First reply with key sk-abcdef1234567890XYZ")
        svc.set_reply(self.data, out["id"], "Second reply.")
        details = svc.details_of(self.data, out["id"])
        self.assertEqual(details["reply"], "Second reply.")
        self.assertEqual(details["text"], "Please check the board shot")
        self.assertNotIn("sk-abcdef", self.raw(svc.TEXT_FILE))

    def test_reply_is_capped_at_8000_characters(self):
        out = svc.capture(self.data, "Please check the board shot", session_id="s1", src="hook", now=NOW)
        self.assertEqual(svc.set_reply(self.data, out["id"], "r" * 9000), 8000)
        self.assertEqual(len(svc.details_of(self.data, out["id"])["reply"]), 8000)

    def test_set_reply_rejects_unknown_ids_and_empty_text(self):
        out = svc.capture(self.data, "Please check the board shot", session_id="s1", src="hook", now=NOW)
        with self.assertRaises(RoadmapError) as unknown:
            svc.set_reply(self.data, "H999", "Done.")
        self.assertEqual(unknown.exception.code, "not_found")
        with self.assertRaises(RoadmapError) as empty:
            svc.set_reply(self.data, out["id"], "   ")
        self.assertEqual(empty.exception.code, "usage")
        self.assertIsNone(svc.details_of(self.data, out["id"])["reply"])

    def test_latest_hook_entry_is_the_newest_hook_capture_of_the_session(self):
        svc.capture(self.data, "First prompt of the session", session_id="s1", src="hook", now=NOW)
        svc.capture(self.data, "Typed in the cli for s1", session_id="s1", src="cli", now=NOW)
        newest = svc.capture(self.data, "Second prompt of the session", session_id="s1", src="hook", now=NOW)
        self.assertEqual(svc.latest_hook_entry(self.data, "s1")["id"], newest["id"])
        self.assertIsNone(svc.latest_hook_entry(self.data, "other"))
        self.assertIsNone(svc.latest_hook_entry(self.data, None))

    def test_spooled_assets_survive_the_adopt(self):
        with mock.patch.object(svc.lock, "locked", side_effect=RoadmapError("locked", "busy", 4)):
            out = svc.capture(self.data, "Please check the board shot", session_id="s1", src="hook",
                              assets=["shot.png"], now=NOW, timeout=0)
        self.assertEqual(out["status"], "spooled")
        svc.session(self.data, "start", session_id="s1", now=NOW)
        eid = self.entry_ids()[0]
        self.assertEqual(svc.details_of(self.data, eid)["assets"], ["shot.png"])
