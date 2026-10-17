"""R11.4: roadmap/services/history.py merges the project's files into one normalized, paged feed (read only)."""

import json
import os
import shutil
import tempfile
import unittest

from roadmap.errors import RoadmapError
from roadmap.services import history


def write(path, obj=None, lines=None):
    with open(path, "w", encoding="utf-8") as fh:
        if lines is not None:
            fh.write("".join(json.dumps(line) + "\n" for line in lines))
        else:
            json.dump(obj, fh)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        d = self.dir
        write(os.path.join(d, "activity.jsonl"), lines=[
            {"id": "A1", "at": "2026-10-17T10:00:00+00:00", "src": "gui", "op": "task.status", "sum": "R1.2 done",
             "undo": True},
            {"id": "A2", "at": "2026-10-17T10:05:02+00:00", "src": "agent", "op": "head.set",
             "sum": "H5 set status", "undo": True},
            {"id": "A3", "at": "2026-10-17T10:06:01+00:00", "src": "gui", "op": "question.answer",
             "sum": "Q1 answered Yes", "undo": True},
            {"id": "A4", "at": "2026-10-17T10:07:00+00:00", "src": "gui", "op": "limit.set", "sum": "weekly 40%",
             "undo": True},
        ])
        write(os.path.join(d, "head.jsonl"), lines=[
            {"v": 1, "t": "e", "id": "H5", "ts": "2026-10-17T10:01:00Z", "src": "hook", "kind": "ask",
             "sum": "please add a history"},
            {"v": 1, "t": "u", "id": "H5", "ts": "2026-10-17T10:05:00Z", "by": "head", "set": {"status": "done"},
             "note": "shipped"},
            {"v": 1, "t": "s", "ts": "2026-10-17T09:00:00Z", "model": "Sonnet 5.5", "ev": "claim"},
        ])
        write(os.path.join(d, "head-text.jsonl"), lines=[{"id": "H5", "text": "please add a full history"},
                                                          {"id": "H5", "reply": "done in R1.2"}])
        write(os.path.join(d, "jobs.json"), {"jobs": [
            {"id": "j1", "title": "haiku: R1.2 history", "model": "haiku", "task": "R1.2", "status": "done",
             "started": "2026-10-17T10:02:00+00:00", "ended": "2026-10-17T10:04:00+00:00", "tokensK": 42.5},
            {"id": "j2", "title": "sonnet: R1.3", "model": "sonnet", "task": "R1.3", "status": "running",
             "started": "2026-10-17T10:08:00+00:00", "ended": None}]})
        write(os.path.join(d, "questions.json"), {"questions": [
            {"id": "Q1", "task": "R1.2", "text": "Ship it?", "opts": ["Yes", "No"], "status": "answered",
             "answer": "Yes", "asked": "2026-10-17T09:30:00+00:00", "answered": "2026-10-17T10:06:00+00:00"}]})
        self.events = history.collect(d, None, {"recent": [[1792231200, 20.0, 1.0], [1792231260, 20.0, 1.0]],
                                                "days": {}})

    def tearDown(self):
        shutil.rmtree(self.dir)

    def by_id(self, ident):
        return next(e for e in self.events if e["id"] == ident)

    def test_every_event_has_the_normalized_shape(self):
        keys = {"id", "ts", "ms", "kind", "verb", "actor", "subject", "summary", "link", "model", "tokensK", "src",
                "undo", "activity", "detail"}
        for event in self.events:
            self.assertEqual(set(event), keys)
            self.assertIn(event["kind"], history.KINDS)
            self.assertIn(event["actor"], history.ACTORS)

    def test_sources_map_to_kinds_and_actors(self):
        self.assertEqual(self.by_id("activity:A1")["kind"], "task")
        self.assertEqual(self.by_id("activity:A1")["actor"], "user")
        self.assertEqual(self.by_id("activity:A1")["link"], "work/i/R1.2")
        self.assertEqual(self.by_id("activity:A4")["kind"], "setting")
        new = self.by_id("head:H5.e0")
        self.assertEqual((new["kind"], new["actor"]), ("head", "user"))
        self.assertEqual(new["detail"]["text"], "please add a full history")
        self.assertEqual(new["detail"]["reply"], "done in R1.2")
        done = self.by_id("jobs:j1.e")
        self.assertEqual((done["kind"], done["actor"], done["model"], done["tokensK"]), ("job", "agent", "haiku", 42.5))
        self.assertEqual(done["detail"]["durationS"], 120)
        self.assertEqual(self.by_id("head:s2")["kind"], "session")

    def test_a_write_logged_twice_shows_once_and_keeps_its_undo(self):
        ids = {e["id"] for e in self.events}
        self.assertNotIn("activity:A2", ids)  # absorbed by the head update
        self.assertNotIn("activity:A3", ids)  # absorbed by the question answer
        update = self.by_id("head:H5.u1")
        self.assertEqual((update["undo"], update["activity"], update["actor"]), (True, "A2", "head"))
        answer = self.by_id("questions:Q1.r")
        self.assertEqual((answer["actor"], answer["activity"]), ("user", "A3"))
        self.assertIn("Yes", answer["summary"])

    def test_unchanged_usage_readings_collapse(self):
        usage = [e for e in self.events if e["kind"] == "usage"]
        self.assertEqual(len(usage), 1)

    def test_paging_is_newest_first_with_a_stable_cursor(self):
        first = history.page(self.events, history.parse_query([("limit", "3")]))
        self.assertEqual(len(first["events"]), 3)
        ms = [e["ms"] for e in first["events"]]
        self.assertEqual(ms, sorted(ms, reverse=True))
        self.assertIn("hist", first)
        seen = [e["id"] for e in first["events"]]
        cursor = first["next"]
        while cursor:
            page = history.page(self.events, history.parse_query([("limit", "3"), ("before", cursor)]))
            self.assertNotIn("hist", page)
            seen += [e["id"] for e in page["events"]]
            cursor = page["next"]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(seen), len(self.events))

    def test_filters_and_counts(self):
        page = history.page(self.events, history.parse_query([("kind", "job,question"), ("actor", "agent")]))
        self.assertTrue(page["events"])
        self.assertTrue(all(e["kind"] == "job" for e in page["events"]))
        self.assertEqual(page["counts"]["job"], 3)
        self.assertEqual(page["counts"]["session"], 1)  # counts ignore the kind filter, so chips show what is there
        found = history.page(self.events, history.parse_query([("q", "full history")]))
        self.assertEqual(found["total"], 0)
        found = history.page(self.events, history.parse_query([("q", "add history")]))
        self.assertEqual([e["id"] for e in found["events"]], ["head:H5.e0"])
        ranged = history.page(self.events, history.parse_query([("from", "2026-10-17T10:03:00Z"),
                                                                ("to", "2026-10-17T10:05:30Z")]))
        self.assertEqual({e["id"] for e in ranged["events"]}, {"jobs:j1.e", "head:H5.u1"})

    def test_histogram_buckets_by_hour_for_a_short_span(self):
        hist = history.histogram(self.events, None)
        self.assertEqual(hist["unit"], "hour")
        self.assertEqual(sum(hist["counts"]), len(self.events))

    def test_timeline_bins_span_the_whole_range(self):
        events = [{"ms": 1000 + i * 1000, "kind": "task" if i % 2 else "head", "actor": "user", "id": "e%d" % i,
                   "summary": "x"} for i in range(1000)]
        tl = history.timeline_bins(events, None, None, 2000000)
        self.assertEqual((tl["t0"], tl["t1"], tl["first"]), (1000, 1980000, 1000))
        self.assertEqual(sum(sum(v) for v in tl["kinds"].values()), 1000)
        self.assertEqual(len(tl["kinds"]["task"]), tl["n"])

    def test_bad_queries_are_refused(self):
        for pairs in ([("kind", "nope")], [("actor", "robot")], [("limit", "0")], [("before", "x")],
                      [("from", "yesterday")], [("q", "a"), ("q", "b")], [("other", "1")]):
            with self.subTest(pairs=pairs):
                with self.assertRaises(RoadmapError):
                    history.parse_query(pairs)

    def test_without_full_the_text_is_left_out(self):
        events = history.collect(self.dir, None, None, full=False)
        new = next(e for e in events if e["id"] == "head:H5.e0")
        self.assertNotIn("text", new["detail"])

    def test_missing_files_give_an_empty_feed(self):
        empty = tempfile.mkdtemp()
        try:
            self.assertEqual(history.collect(empty, None, None), [])
        finally:
            shutil.rmtree(empty)


if __name__ == "__main__":
    unittest.main()
