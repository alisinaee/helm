"""HEAD-SPEC H7: the head key of the snapshot and the ask ref kind. Pure: records are built by hand, no file or network.
Checks: the key appears only when records are given, the counts and rows follow the fold, the key fits 3 KB with 40+
rows, no `text` key anywhere in the snapshot, sessions give now and prev, and rb:<project>/ask/<id> parses."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from roadmap.core import refs
from roadmap.core.snapshot import (HEAD_BYTES_MAX, HEAD_LINKS_MAX, HEAD_SUM_MAX, build_snapshot, head_link_state,
                                   head_row)

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def stamp(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def entry(eid, minutes_ago, sum_text, kind="ask?", src="hook", sid="abc12345"):
    return {"v": 1, "t": "e", "id": eid, "ts": stamp(minutes_ago), "src": src, "sid": sid, "kind": kind,
            "sum": sum_text, "len": len(sum_text), "h": "sha1:000000000000"}


def update(eid, minutes_ago, by="head", sets=None, links=None):
    rec = {"v": 1, "t": "u", "id": eid, "ts": stamp(minutes_ago), "by": by}
    if sets:
        rec["set"] = sets
    if links:
        rec["link"] = links
    return rec


def session(ev, minutes_ago, model, acct, sid="s1s1s1s1", usage=None):
    rec = {"v": 1, "t": "s", "ts": stamp(minutes_ago), "sid": sid, "acct": acct, "model": model, "ev": ev}
    if usage:
        rec["usage"] = usage
    return rec


def snap(records, **extra):
    return build_snapshot({}, {}, NOW, head_records=records, **extra)


def walk_keys(value):
    """Every dict key in a nested value."""
    if isinstance(value, dict):
        for key, sub in value.items():
            yield key
            yield from walk_keys(sub)
    elif isinstance(value, list):
        for sub in value:
            yield from walk_keys(sub)


class HeadKeyPresence(unittest.TestCase):
    def test_no_head_key_without_records(self):
        self.assertNotIn("head", build_snapshot({}, {}, NOW))

    def test_empty_records_give_an_empty_head(self):
        head = snap([])["head"]
        self.assertEqual(head["counts"], {"open": 0, "unhandled": 0, "doing": 0, "needs": 0, "doneUnacc": 0})
        self.assertEqual(head["rows"], [])
        self.assertEqual(head["prev"], [])
        self.assertEqual(head["now"]["usage"], None)


class HeadCountsAndRows(unittest.TestCase):
    def setUp(self):
        self.records = [
            entry("H1", 10, "Fix the broken export", kind="bug?"),
            entry("H2", 200, "Always use the staging host"),
            entry("H3", 5, "Please check the audit"),
            entry("H4", 90, "Ship the notes page", sid="zzz99999"),
            update("H3", 4, sets={"kind": "review", "sum": "Check the audit"}),
            update("H4", 3, by="person", sets={"status": "needs-you"}),
            update("H2", 2, by="person", sets={"status": "done"}),
        ]

    def test_counts_follow_the_fold(self):
        head = snap(self.records)["head"]
        self.assertEqual(head["counts"], {"open": 3, "unhandled": 2, "doing": 0, "needs": 1, "doneUnacc": 1})

    def test_open_rows_oldest_first_then_done(self):
        rows = snap(self.records)["head"]["rows"]
        self.assertEqual([row["id"] for row in rows], ["H4", "H1", "H3", "H2"])
        self.assertEqual(rows[-1]["status"], "done")

    def test_row_shape_strips_the_question_mark_and_counts_minutes(self):
        row = next(r for r in snap(self.records)["head"]["rows"] if r["id"] == "H1")
        self.assertEqual(row, {"id": "H1", "kind": "bug", "sum": "Fix the broken export", "status": "new", "age": 10})

    def test_stale_flag_after_two_hours_unhandled(self):
        head = snap([entry("H9", 200, "Old ask"), entry("H10", 20, "New ask")])["head"]
        by_id = {row["id"]: row for row in head["rows"]}
        self.assertIs(by_id["H9"]["stale"], True)
        self.assertNotIn("stale", by_id["H10"])

    def test_done_rows_capped_to_the_newest_five(self):
        records = [entry("H%d" % i, 100 - i, "Done ask %d" % i) for i in range(1, 9)]
        records += [update("H%d" % i, 1, by="person", sets={"status": "done"}) for i in range(1, 9)]
        rows = snap(records)["head"]["rows"]
        self.assertEqual([r["id"] for r in rows], ["H4", "H5", "H6", "H7", "H8"])


class HeadRowShape(unittest.TestCase):
    def test_flags_and_links_are_left_out_when_empty(self):
        folded = {"id": "H7", "kind": "task?", "sum": "x", "status": "bound", "ts": stamp(0), "stale": False,
                  "carried": False, "links": [], "dup": None}
        self.assertEqual(head_row(folded, NOW), {"id": "H7", "kind": "task", "sum": "x", "status": "bound", "age": 0})

    def test_links_capped_with_a_more_count_and_summary_cut(self):
        links = ["task:R%d" % i for i in range(5)]
        folded = {"id": "H8", "kind": "ask?", "sum": "s" * 200, "status": "doing", "ts": stamp(0), "links": links,
                  "carried": True, "stale": True, "dup": {"id": "H2", "score": 0.7}}
        row = head_row(folded, NOW)
        self.assertEqual(row["links"], links[:HEAD_LINKS_MAX])
        self.assertEqual(row["more"], 5 - HEAD_LINKS_MAX)
        self.assertEqual(len(row["sum"]), HEAD_SUM_MAX)
        self.assertEqual(row["dup"], "H2")
        self.assertIs(row["carried"], True)

    def test_link_state_maps_tasks_and_jobs(self):
        state = head_link_state([{"id": "R7.31", "state": "partial"}, {"id": "R1", "state": "done"}],
                                [{"id": "j1", "status": "running"}, {"id": "j2", "status": "failed"},
                                 {"id": "j3", "status": "done"}])
        self.assertEqual(state, {"task:R7.31": "partial", "task:R1": "done", "job:j1": "running",
                                 "job:j2": "open", "job:j3": "done"})


class HeadSizeAndPrivacy(unittest.TestCase):
    def test_forty_long_rows_fit_three_kilobytes_and_carry_no_text(self):
        records = [entry("H%d" % i, 30 + i, "Long summary text that keeps going " * 4 + str(i)) for i in range(1, 41)]
        records += [entry("H%d" % (41 + i), 500 + i, "Done " + "word " * 30) for i in range(5)]
        records += [update("H%d" % (41 + i), 1, by="person", sets={"status": "done"}) for i in range(5)]
        full = snap(records)
        head = full["head"]
        raw = json.dumps(head, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(raw), HEAD_BYTES_MAX)
        self.assertEqual(head["counts"]["open"], 40)
        self.assertLess(len(head["rows"]), 45)
        self.assertNotIn("text", set(walk_keys(full)))

    def test_no_text_key_anywhere_when_the_records_have_one(self):
        records = [entry("H1", 3, "Fix the export")]
        records[0]["text"] = "the verbatim words"
        full = snap(records)
        self.assertNotIn("text", set(walk_keys(full)))
        self.assertNotIn("verbatim", json.dumps(full))


class HeadSessions(unittest.TestCase):
    def test_now_and_prev_from_claims_and_starts(self):
        records = [session("claim", 300, "Opus", "A", sid="s1s1s1s1"),
                   session("start", 240, "Opus", "B", sid="s2s2s2s2", usage={"h5": 41, "wk": 63, "x": 1}),
                   session("end", 230, "Opus", "B", sid="s2s2s2s2")]
        head = snap(records)["head"]
        self.assertEqual(head["now"]["acct"], "B")
        self.assertEqual(head["now"]["model"], "Opus")
        self.assertEqual(head["now"]["usage"], {"h5": 41, "wk": 63})
        self.assertEqual(len(head["prev"]), 1)
        self.assertEqual(head["prev"][0]["acct"], "A")
        self.assertEqual(head["prev"][0]["until"], stamp(240))


class RefKindAsk(unittest.TestCase):
    def test_ask_refs_parse_and_format(self):
        self.assertIn("ask", refs.KINDS)
        self.assertEqual(refs.parse("rb:roadmap-board/ask/H12"), ("roadmap-board", "ask", "H12"))
        self.assertEqual(refs.format_ref("roadmap-board", "ask", "H12"), "rb:roadmap-board/ask/H12")

    def test_ask_record_rows(self):
        item = head_row({"id": "H12", "kind": "bug?", "sum": "Export broken", "status": "doing", "ts": stamp(20),
                         "links": ["task:R7.31"]}, NOW)
        rows, next_cmd = refs.build({}, "roadmap-board", "ask", "H12", item=item)
        self.assertEqual(rows[0], [("title", "Export broken")])
        self.assertIn(("age", "20m"), rows[1])
        self.assertEqual(rows[2], [("bound", "task:R7.31")])
        self.assertEqual(next_cmd, "roadmap head list")


if __name__ == "__main__":
    unittest.main()
