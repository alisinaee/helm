"""Head priority P0..P3 (HEAD-V3-PLAN section 4, queue Q3): the phrase table set in core/head.py, the one-level raise
on a repeat, the fold that carries the priority on an entry, and the service side (capture, update, head set prio).
The pure cases touch no file; the service cases run in a temp ROADMAP_HOME with a temp data folder."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from roadmap.core import head
from roadmap.errors import RoadmapError
from roadmap.services import head as svc
from roadmap.services import headops

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def entry(eid, sum_text, prio=None):
    rec = {"v": 1, "t": "e", "id": eid, "ts": "2026-10-16T11:59:00Z", "src": "cli", "sid": None,
           "kind": "ask?", "sum": sum_text}
    if prio is not None:
        rec["prio"] = prio
    return rec


class GuessPrioTest(unittest.TestCase):
    def test_phrase_table_gives_p0(self):
        for text in ("this is urgent", "ASAP please", "it is a blocker", "the build is broken", "do this first",
                     "make it top priority"):
            self.assertEqual(head.guess_prio(text), 0, text)

    def test_phrase_table_gives_p1(self):
        for text in ("fix it today", "work on this session", "do the next thing"):
            self.assertEqual(head.guess_prio(text), 1, text)

    def test_phrase_table_gives_p3(self):
        for text in ("do it later", "someday maybe", "add to the backlog", "a nice to have", "maybe later"):
            self.assertEqual(head.guess_prio(text), 3, text)

    def test_no_phrase_gives_p2(self):
        self.assertEqual(head.guess_prio("add a footer link"), head.PRIO_DEFAULT)
        self.assertEqual(head.PRIO_DEFAULT, 2)
        self.assertEqual(head.guess_prio(""), 2)
        self.assertEqual(head.guess_prio(None), 2)

    def test_whole_words_only(self):
        # "nowhere" and "nextdoor" must not match "now" and "next"
        self.assertEqual(head.guess_prio("nowhere to go"), 2)
        self.assertEqual(head.guess_prio("nextdoor neighbour"), 2)

    def test_first_matching_row_wins(self):
        # P0 is checked before P3, so an urgent later item is P0
        self.assertEqual(head.guess_prio("urgent, but maybe later"), 0)


class BumpPrioTest(unittest.TestCase):
    def test_repeat_raises_one_level(self):
        self.assertEqual(head.bump_prio(3), 2)
        self.assertEqual(head.bump_prio(2), 1)
        self.assertEqual(head.bump_prio(1), 0)

    def test_p0_stays_p0(self):
        self.assertEqual(head.bump_prio(0), 0)

    def test_invalid_prio_is_refused(self):
        for bad in (4, -1, True, "2", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                head.bump_prio(bad)


class ValidPrioTest(unittest.TestCase):
    def test_bool_is_not_a_priority(self):
        self.assertFalse(head.valid_prio(True))
        self.assertFalse(head.valid_prio(False))
        self.assertTrue(head.valid_prio(0))
        self.assertFalse(head.valid_prio(4))


class FoldPrioTest(unittest.TestCase):
    def test_fold_guesses_from_summary_when_no_prio_stored(self):
        row = head.fold([entry("H1", "urgent fix the login")], now=NOW)[0]
        self.assertEqual(row["prio"], 0)

    def test_fold_uses_a_stored_valid_prio(self):
        row = head.fold([entry("H1", "urgent fix", prio=3)], now=NOW)[0]
        self.assertEqual(row["prio"], 3)

    def test_fold_ignores_an_invalid_stored_prio(self):
        row = head.fold([entry("H1", "do the report", prio=9)], now=NOW)[0]
        self.assertEqual(row["prio"], head.PRIO_DEFAULT)

    def test_set_update_changes_prio_and_keeps_it(self):
        recs = [entry("H1", "add a footer link"),
                {"v": 1, "t": "u", "id": "H1", "ts": "2026-10-16T11:59:30Z", "by": "person",
                 "set": {"prio": 0}}]
        row = head.fold(recs, now=NOW)[0]
        self.assertEqual(row["prio"], 0)

    def test_set_update_with_invalid_prio_is_ignored(self):
        recs = [entry("H1", "add a footer link"),
                {"v": 1, "t": "u", "id": "H1", "ts": "2026-10-16T11:59:30Z", "by": "person",
                 "set": {"prio": True}}]
        row = head.fold(recs, now=NOW)[0]
        self.assertEqual(row["prio"], head.PRIO_DEFAULT)


class ServicePrioCase(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.root = tempfile.mkdtemp(prefix="head-prio-")
        os.environ["ROADMAP_HOME"] = os.path.join(self.root, "home")
        self.data = os.path.join(self.root, "docs")
        os.makedirs(self.data)

    def tearDown(self):
        if self._saved_home is None:
            os.environ.pop("ROADMAP_HOME", None)
        else:
            os.environ["ROADMAP_HOME"] = self._saved_home
        shutil.rmtree(self.root, ignore_errors=True)

    def entries(self):
        with open(os.path.join(self.data, svc.FILE), encoding="utf-8") as fh:
            objs = [json.loads(x) for x in fh.read().splitlines() if x.strip()]
        return [o for o in objs if o.get("t") == "e"]

    def prio_of(self, eid):
        return next(r["prio"] for r in svc.rows(self.data, now=NOW) if r["id"] == eid)


class CapturePrioTest(ServicePrioCase):
    def test_capture_stores_the_phrase_table_prio(self):
        out = svc.capture(self.data, "this is urgent, fix the export", session_id="s", now=NOW)
        self.assertEqual(out["status"], "logged")
        self.assertEqual(self.entries()[0]["prio"], 0)
        self.assertEqual(self.prio_of(out["id"]), 0)

    def test_repeat_capture_raises_existing_entry_one_level(self):
        first = svc.capture(self.data, "add a footer link", session_id="s", now=NOW)
        self.assertEqual(self.prio_of(first["id"]), 2)
        again = svc.capture(self.data, "add a footer link", session_id="s", now=NOW)
        self.assertEqual((again["status"], again["id"]), ("bumped", first["id"]))
        self.assertEqual(again["prio"], 1)
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(self.prio_of(first["id"]), 1)

    def test_repeats_stop_at_p0(self):
        svc.capture(self.data, "add a footer link", session_id="s", now=NOW)
        for _ in range(4):
            out = svc.capture(self.data, "add a footer link", session_id="s", now=NOW)
        self.assertEqual(out["prio"], 0)
        self.assertEqual(len(self.entries()), 1)

    def test_a_different_text_is_a_new_entry(self):
        svc.capture(self.data, "add a footer link", session_id="s", now=NOW)
        out = svc.capture(self.data, "add a header link", session_id="s", now=NOW)
        self.assertEqual(out["status"], "logged")
        self.assertEqual(len(self.entries()), 2)


class UpdatePrioTest(ServicePrioCase):
    def test_update_sets_prio_from_zero_to_three(self):
        eid = svc.capture(self.data, "add a footer link", session_id="s", now=NOW)["id"]
        for level in (0, 1, 2, 3):
            svc.update(self.data, eid, by="person", sets={"prio": level}, now=NOW)
            self.assertEqual(self.prio_of(eid), level)

    def test_update_refuses_a_bad_prio(self):
        eid = svc.capture(self.data, "add a footer link", session_id="s", now=NOW)["id"]
        for bad in (4, -1, True, "P1"):
            with self.assertRaises(RoadmapError, msg=repr(bad)):
                svc.update(self.data, eid, by="person", sets={"prio": bad}, now=NOW)
        self.assertEqual(self.prio_of(eid), 2)


class SetPrioArgTest(unittest.TestCase):
    def test_prio_words_map_to_levels(self):
        for word, level in (("P0", 0), ("p1", 1), ("P2", 2), ("P3", 3)):
            self.assertEqual(headops._prio_arg({"prio": word}), level, word)
        self.assertIsNone(headops._prio_arg({"prio": ""}))
        self.assertIsNone(headops._prio_arg({}))

    def test_other_prio_words_are_refused(self):
        for bad in ("P4", "2", "high", "P-1"):
            with self.assertRaises(RoadmapError, msg=bad):
                headops._prio_arg({"prio": bad})


if __name__ == "__main__":
    unittest.main()
