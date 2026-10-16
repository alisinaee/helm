"""Head ask answer choices (R9.31): --opt on head t stores 2..6 options as the entry's opts list (default []), the fold
carries them, the snapshot head row shows them only when set, and answering with one option is a head set status.
The pure cases touch no file; the service cases run in a temp ROADMAP_HOME with a temp data folder."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from roadmap.core import head
from roadmap.core.snapshot import head_row
from roadmap.errors import RoadmapError
from roadmap.services import head as svc
from roadmap.services import headops

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def entry(eid, sum_text="ship which footer?"):
    return {"v": 1, "t": "e", "id": eid, "ts": "2026-10-16T11:59:00Z", "src": "cli", "sid": None,
            "kind": "ask?", "sum": sum_text}


class CleanOptsTest(unittest.TestCase):
    def test_two_to_six_choices_are_kept_in_order(self):
        self.assertEqual(svc.clean_opts(["  red ", "blue"]), ["red", "blue"])
        self.assertEqual(len(svc.clean_opts(["a", "b", "c", "d", "e", "f"])), 6)

    def test_empty_list_clears(self):
        self.assertEqual(svc.clean_opts([]), [])

    def test_one_choice_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            svc.clean_opts(["only"])
        self.assertEqual(ctx.exception.code, "usage")

    def test_seven_choices_are_refused(self):
        with self.assertRaises(RoadmapError):
            svc.clean_opts(list("abcdefg"))

    def test_empty_option_is_refused(self):
        with self.assertRaises(RoadmapError):
            svc.clean_opts(["a", "   "])

    def test_repeats_collapse_and_long_text_is_cut(self):
        self.assertEqual(svc.clean_opts(["a", "a", "b"]), ["a", "b"])
        self.assertEqual(len(svc.clean_opts(["x" * 200, "y"])[0]), svc.OPT_MAX)

    def test_non_list_is_refused(self):
        with self.assertRaises(RoadmapError):
            svc.clean_opts("a,b")


class FoldOptsTest(unittest.TestCase):
    def test_missing_opts_folds_to_empty_list(self):
        rows = head.fold([entry("H1")], now=NOW)
        self.assertEqual(rows[0]["opts"], [])

    def test_update_sets_opts_and_empty_clears_them(self):
        recs = [entry("H1"), {"t": "u", "id": "H1", "by": "head", "set": {"opts": ["red", "blue"]}}]
        self.assertEqual(head.fold(recs, now=NOW)[0]["opts"], ["red", "blue"])
        recs.append({"t": "u", "id": "H1", "by": "head", "set": {"opts": []}})
        self.assertEqual(head.fold(recs, now=NOW)[0]["opts"], [])

    def test_non_list_opts_in_a_record_is_ignored(self):
        recs = [entry("H1"), {"t": "u", "id": "H1", "by": "head", "set": {"opts": "red"}}]
        self.assertEqual(head.fold(recs, now=NOW)[0]["opts"], [])


class SnapshotOptsTest(unittest.TestCase):
    def row(self, **extra):
        folded = dict(head.fold([entry("H1")], now=NOW)[0], **extra)
        return head_row(folded, NOW)

    def test_opts_row_field_only_when_non_empty(self):
        self.assertNotIn("opts", self.row())
        self.assertNotIn("opts", self.row(opts=[]))
        self.assertEqual(self.row(opts=["red", "blue"])["opts"], ["red", "blue"])


class TriageArgTest(unittest.TestCase):
    def test_check_triage_passes_opts_through_and_none_when_absent(self):
        base = {"id": "H1", "kind": "ask", "sum": "which?"}
        self.assertIsNone(headops._check_triage(base)["opts"])
        self.assertEqual(headops._check_triage(dict(base, opts=["a", "b"]))["opts"], ["a", "b"])

    def test_check_triage_refuses_one_option_as_usage(self):
        with self.assertRaises(RoadmapError) as ctx:
            headops._check_triage({"id": "H1", "kind": "ask", "sum": "which?", "opts": ["a"]})
        self.assertEqual(ctx.exception.code, "usage")


class ServiceOptsCase(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.root = tempfile.mkdtemp(prefix="head-opts-")
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

    def opts_of(self, eid):
        return next(r["opts"] for r in svc.rows(self.data, now=NOW) if r["id"] == eid)


class TriageOptsTest(ServiceOptsCase):
    def test_triage_with_opts_stores_them_and_the_row_shows_them(self):
        eid = svc.capture(self.data, "which footer style", session_id="s", now=NOW)["id"]
        headops._h_triage(self.data, headops._check_triage(
            {"id": eid, "kind": "ask", "sum": "which footer style?", "opts": ["a dark bar", "a plain line"]}), NOW)
        self.assertEqual(self.opts_of(eid), ["a dark bar", "a plain line"])
        folded = next(r for r in svc.rows(self.data, now=NOW) if r["id"] == eid)
        self.assertEqual(head_row(folded, NOW)["opts"], ["a dark bar", "a plain line"])

    def test_triage_without_opts_leaves_an_entry_without_them(self):
        eid = svc.capture(self.data, "plain question", session_id="s", now=NOW)["id"]
        headops._h_triage(self.data, headops._check_triage(
            {"id": eid, "kind": "question", "sum": "plain question?"}), NOW)
        self.assertEqual(self.opts_of(eid), [])
        self.assertNotIn("opts", self.entries()[0])

    def test_answering_with_one_option_sets_status_through_head_set(self):
        eid = svc.capture(self.data, "which footer style", session_id="s", now=NOW)["id"]
        headops._h_triage(self.data, headops._check_triage(
            {"id": eid, "kind": "ask", "sum": "which footer style?", "opts": ["a dark bar", "a plain line"]}), NOW)
        headops._h_set(self.data, headops._check_set({"id": eid, "status": "declined", "note": "b"}), NOW)
        folded = next(r for r in svc.rows(self.data, now=NOW) if r["id"] == eid)
        self.assertEqual(folded["status"], "declined")
        self.assertEqual(folded["opts"], ["a dark bar", "a plain line"])


if __name__ == "__main__":
    unittest.main()
