"""HEAD-SPEC H7: the head key of the snapshot and the ask ref kind. Pure: records are built by hand, no file or network.
Checks: the key appears only when records are given, the counts and rows follow the fold, the key fits 3 KB with 40+
rows, no `text` key anywhere in the snapshot, sessions give now and prev, and rb:<project>/ask/<id> parses."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from roadmap.core import head as head_rules
from roadmap.core import refs
from roadmap.core.snapshot import (HEAD_BYTES_MAX, HEAD_LINKED_MAX, HEAD_LINKS_MAX, HEAD_SUM_MAX, HEAD_TITLE_MAX,
                                   _head_size, _head_view, build_snapshot, head_link_state, head_row)

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
TRIM_CAP = 3072  # the old cap: forces the newest-first trim in the tests that need rows dropped


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


def snap_trimmed(records):
    with mock.patch("roadmap.core.snapshot.HEAD_BYTES_MAX", TRIM_CAP):
        return snap(records)


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
        self.assertEqual(head["counts"], {"open": 3, "unhandled": 2, "doing": 0, "needs": 1, "doneUnacc": 0})

    def test_open_rows_oldest_first_then_done(self):
        rows = snap(self.records)["head"]["rows"]
        self.assertEqual([row["id"] for row in rows], ["H3", "H1", "H4", "H2"])  # newest first by ts
        self.assertEqual(rows[-1]["status"], "done")

    def test_row_shape_strips_the_question_mark_and_counts_minutes(self):
        row = next(r for r in snap(self.records)["head"]["rows"] if r["id"] == "H1")
        self.assertEqual(row, {"id": "H1", "kind": "bug", "sum": "Fix the broken export", "status": "new", "age": 10,
                               "ts": stamp(10)})

    def test_stale_flag_after_two_hours_unhandled(self):
        head = snap([entry("H9", 200, "Old ask"), entry("H10", 20, "New ask")])["head"]
        by_id = {row["id"]: row for row in head["rows"]}
        self.assertIs(by_id["H9"]["stale"], True)
        self.assertNotIn("stale", by_id["H10"])

    def test_done_rows_capped_to_the_newest_five(self):
        records = [entry("H%d" % i, 100 - i, "Done ask %d" % i) for i in range(1, 9)]
        records += [update("H%d" % i, 1, by="person", sets={"status": "done"}) for i in range(1, 9)]
        rows = snap(records)["head"]["rows"]
        self.assertEqual([r["id"] for r in rows], ["H8", "H7", "H6", "H5", "H4"])


class HeadRowShape(unittest.TestCase):
    def test_flags_and_links_are_left_out_when_empty(self):
        folded = {"id": "H7", "kind": "task?", "sum": "x", "status": "bound", "ts": stamp(0), "stale": False,
                  "carried": False, "links": [], "dup": None}
        self.assertEqual(head_row(folded, NOW), {"id": "H7", "kind": "task", "sum": "x", "status": "bound", "age": 0,
                                                 "ts": stamp(0)})

    def test_links_capped_with_a_more_count_and_summary_cut(self):
        links = ["task:R%d" % i for i in range(5)]
        folded = {"id": "H8", "kind": "ask?", "sum": "s" * 200, "status": "doing", "ts": stamp(0), "links": links,
                  "carried": True, "stale": True, "dup": {"id": "H2", "score": 0.7}}
        row = head_row(folded, NOW)
        self.assertEqual(row["links"], links[:HEAD_LINKS_MAX])
        self.assertEqual(row["more"], 5 - HEAD_LINKS_MAX)
        self.assertEqual(len(row["sum"]), HEAD_SUM_MAX)
        self.assertEqual(row["dup"], {"id": "H2", "score": 0.7})
        self.assertIs(row["carried"], True)

    def test_link_state_maps_tasks_and_jobs(self):
        state = head_link_state([{"id": "R7.31", "state": "partial"}, {"id": "R1", "state": "done"}],
                                [{"id": "j1", "status": "running"}, {"id": "j2", "status": "failed"},
                                 {"id": "j3", "status": "done"}])
        self.assertEqual(state, {"task:R7.31": "partial", "task:R1": "done", "job:j1": "running",
                                 "job:j2": "failed", "job:j3": "done"})


class HeadSizeAndPrivacy(unittest.TestCase):
    def test_forty_long_rows_fit_three_kilobytes_and_carry_no_text(self):
        records = [entry("H%d" % i, 30 + i, "Long summary text that keeps going " * 4 + str(i)) for i in range(1, 41)]
        records += [entry("H%d" % (41 + i), 500 + i, "Done " + "word " * 30) for i in range(5)]
        records += [update("H%d" % (41 + i), 1, by="person", sets={"status": "done"}) for i in range(5)]
        full = snap_trimmed(records)
        head = full["head"]
        raw = json.dumps(head, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(raw), TRIM_CAP)
        self.assertEqual(head["counts"]["open"], sum(1 for r in head["rows"] if r["status"] != "done"))
        self.assertLess(len(head["rows"]), 45)
        self.assertNotIn("text", set(walk_keys(full)))

    def test_no_text_key_anywhere_when_the_records_have_one(self):
        records = [entry("H1", 3, "Fix the export")]
        records[0]["text"] = "the verbatim words"
        full = snap(records)
        self.assertNotIn("text", set(walk_keys(full)))
        self.assertNotIn("verbatim", json.dumps(full))


class HeadTrimKeepsNewest(unittest.TestCase):
    def test_forty_open_rows_keep_the_newest_and_respect_the_cap(self):
        records = [entry("H%d" % i, 40 - i, "Ask number %d about the export" % i) for i in range(1, 41)]
        full = snap_trimmed(records)
        head = full["head"]
        raw = json.dumps(head, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(raw), TRIM_CAP)
        kept = [row["id"] for row in head["rows"]]
        self.assertTrue(kept, "some rows must be kept")
        self.assertEqual(head["counts"]["open"], len(kept))
        self.assertEqual(kept, ["H%d" % i for i in range(40, 40 - len(kept), -1)])  # newest first, oldest dropped
        self.assertEqual(kept[0], "H40")
        self.assertNotIn("H1", kept)
        print("kept %d of 40 rows" % len(kept))

    def test_thirty_six_open_rows_keep_the_newest_thirty(self):
        records = [entry("H%d" % i, 41 - i, "Long ask number %d about the export button and the map view %s"
                         % (i, "x" * 60)) for i in range(1, 37)]
        head = snap(records)["head"]
        raw = json.dumps(head, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(raw), HEAD_BYTES_MAX)
        kept = [row["id"] for row in head["rows"]]
        self.assertTrue({"H%d" % i for i in range(7, 37)} <= set(kept))  # the newest 30 are always kept

    def test_open_rows_outrank_done_rows_when_trimmed(self):
        records = [entry("H%d" % i, 200 - i, "Done ask %d" % i) for i in range(1, 6)]
        records += [update("H%d" % i, 1, by="person", sets={"status": "done"}) for i in range(1, 6)]
        records += [entry("H%d" % i, 40 - i, "Ask number %d about the export" % i) for i in range(10, 50)]
        head = snap_trimmed(records)["head"]
        raw = json.dumps(head, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(raw), TRIM_CAP)
        self.assertTrue(all(row["status"] != "done" for row in head["rows"]))


class HeadAcceptAndAutoFlags(unittest.TestCase):
    def test_acc_only_when_the_person_last_set_done(self):
        records = [entry("H1", 30, "Done by the head"), update("H1", 20, sets={"status": "done"}),
                   entry("H2", 30, "Done by the person"), update("H2", 20, by="person", sets={"status": "done"}),
                   entry("H3", 30, "Confirmed then reopened"),
                   update("H3", 20, by="person", sets={"status": "done"}),
                   update("H3", 10, by="person", sets={"status": "open"})]
        rows = {row["id"]: row for row in snap(records)["head"]["rows"]}
        self.assertEqual(rows["H2"]["status"], "done")
        self.assertIs(rows["H2"]["acc"], True)
        self.assertNotIn("acc", rows["H1"])
        self.assertNotIn("acc", rows["H3"])

    def test_auto_when_every_link_is_done_and_not_yet_confirmed(self):
        records = [entry("H6", 5, "Linked ask"), update("H6", 4, links=["+task:R1.1"])]
        folded = head_rules.fold(records, link_state={"task:R1.1": "done"}, now=NOW)[0]
        row = head_row(folded, NOW)
        self.assertEqual(row["status"], "done")
        self.assertIs(row["auto"], True)
        self.assertNotIn("acc", row)
        self.assertNotIn("auto", head_row(dict(folded, auto_done=False), NOW))

    def test_acc_and_auto_are_left_out_unless_true(self):
        base = {"id": "H7", "kind": "ask", "sum": "x", "status": "done", "ts": stamp(0), "links": []}
        self.assertEqual(head_row(base, NOW), {"id": "H7", "kind": "ask", "sum": "x", "status": "done", "age": 0,
                                                "ts": stamp(0)})
        self.assertIs(head_row(base, NOW, accepted=True)["acc"], True)
        self.assertNotIn("acc", head_row(base, NOW, accepted=False))
        self.assertNotIn("auto", head_row(dict(base, auto_done=True, status="open"), NOW))


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


TASKS = [{"id": "R7.31", "title": "Head section design", "state": "todo"},
         {"id": "R7.40", "title": "Export button in the map view", "state": "todo"},
         {"id": "R2.1", "title": "Login page export", "state": "done"}]
ISSUES = [{"id": "I4", "title": "Export button fails", "status": "open"}]


class HeadSuggest(unittest.TestCase):
    def view(self, records, tasks=TASKS, issues=ISSUES):
        return _head_view(records, {}, NOW, tasks=tasks, issues=issues)

    def test_unbound_open_row_gets_suggest_from_open_tasks_and_issues(self):
        row = self.view([entry("H1", 5, "Please check R7.40 soon")])["rows"][0]
        self.assertEqual(row["suggest"], ["task:R7.40"])

    def test_title_overlap_suggests_open_task_and_issue_not_done_task(self):
        row = self.view([entry("H1", 5, "Fix the export button")])["rows"][0]
        self.assertEqual(row["suggest"], ["issue:I4", "task:R7.40"])

    def test_bound_row_gets_no_suggest(self):
        records = [entry("H1", 5, "Fix the export button"),
                   update("H1", 4, by="head", sets={"status": "bound"}, links=["+task:R7.31"])]
        self.assertNotIn("suggest", self.view(records)["rows"][0])

    def test_done_row_gets_no_suggest(self):
        records = [entry("H1", 5, "Check R7.31"), update("H1", 4, by="person", sets={"status": "done"})]
        self.assertNotIn("suggest", self.view(records)["rows"][0])

    def test_no_rows_to_suggest_from_means_no_key(self):
        self.assertNotIn("suggest", self.view([entry("H1", 5, "Check R7.31")], tasks=[], issues=[])["rows"][0])

    def test_row_carries_the_added_timestamp(self):
        records = [entry("H1", 5, "Check R7.31")]
        row = _head_view(records, {}, NOW, tasks=TASKS, issues=ISSUES)["rows"][0]
        self.assertEqual(row["ts"], stamp(5))

    def test_head_row_takes_suggest_argument(self):
        e = {"id": "H2", "ts": stamp(3), "kind": "ask?", "sum": "x", "status": "new", "links": []}
        self.assertEqual(head_row(e, NOW, suggest=["task:R7.31"])["suggest"], ["task:R7.31"])
        self.assertNotIn("suggest", head_row(e, NOW, suggest=None))

    def test_wiring_through_build_snapshot_reads_tasks_json(self):
        tasks_json = json.dumps({"updated": "2026-10-15", "phases": [{"id": "R7", "title": "P", "state": "todo"}],
                                 "tasks": [{"id": "R7.31", "title": "Head section design", "phase": "R7",
                                            "state": "todo"}]})
        result = build_snapshot({"tasks.json": tasks_json}, {}, NOW,
                                head_records=[entry("H1", 5, "Check R7.31 please")])
        self.assertNotIn("suggest", result["head"]["rows"][0])  # umbrella alone is not offered

    def test_suggest_keeps_the_block_under_three_kilobytes(self):
        tasks = [{"id": "R%d.%d" % (i, i), "title": "export map button %d" % i, "state": "todo"} for i in range(1, 60)]
        records = [entry("H%d" % i, 30 + i, "export map button long summary text %d" % i) for i in range(1, 41)]
        head_view = self.view(records, tasks=tasks, issues=[])
        head_view.pop("askOf", None)  # the caller takes askOf out of the head key
        raw = json.dumps(head_view, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(raw), HEAD_BYTES_MAX)
        self.assertEqual(head_view["counts"]["open"], 40)


LINK_TASKS = [{"id": "R7.31", "title": "Head section design", "state": "partial"},
              {"id": "R1", "title": "Done thing", "state": "done"},
              {"id": "R5", "title": "Todo thing", "state": "todo"}]
LINK_ISSUES = [{"id": "I4", "title": "Blocker", "status": "open"}, {"id": "I5", "title": "Closed", "status": "closed"}]
LINK_JOBS = [{"id": "j1", "title": "Build", "model": "Haiku", "task": "R7.31", "status": "running"},
             {"id": "j2", "title": "Old", "model": "Opus", "task": "R1", "status": "done"},
             {"id": "j5", "title": "Work", "model": "Sonnet", "task": "R5", "status": "running"}]


def linked_view(records, tasks=LINK_TASKS, issues=LINK_ISSUES, jobs=LINK_JOBS):
    link_state = head_link_state(tasks, jobs, issues)
    return _head_view(records, link_state, NOW, tasks=tasks, issues=issues, jobs=jobs)


class HeadLinkedProgAskOf(unittest.TestCase):
    def test_links_resolve_with_title_status_and_running_jobs_only(self):
        records = [entry("H1", 10, "Ask about head"),
                   update("H1", 9, links=["+task:R7.31", "+task:R1", "+issue:I4", "+job:j1"])]
        row = linked_view(records)["rows"][0]
        by_ref = {item["ref"]: item for item in row["linked"]}
        self.assertEqual(by_ref["task:R7.31"], {"ref": "task:R7.31", "title": "Head section design",
                                                "status": "partial",
                                                "jobs": [{"id": "j1", "model": "Haiku", "state": "running"}]})
        self.assertEqual(by_ref["task:R1"]["jobs"], [])
        self.assertEqual(by_ref["issue:I4"], {"ref": "issue:I4", "status": "open", "jobs": []})  # title only on the first
        self.assertEqual(by_ref["job:j1"]["jobs"], [{"id": "j1", "model": "Haiku", "state": "running"}])
        self.assertEqual(row["links"], ["task:R7.31", "task:R1", "issue:I4"])
        self.assertEqual(row["status"], "doing")

    def test_unresolved_refs_are_left_out_and_empty_linked_is_absent(self):
        row = linked_view([entry("H1", 10, "Ask"), update("H1", 9, links=["+task:R99"])])["rows"][0]
        self.assertNotIn("linked", row)
        self.assertNotIn("prog", row)
        self.assertEqual(row["links"], ["task:R99"])

    def test_link_title_is_cut_to_sixty_characters(self):
        tasks = [{"id": "R9", "title": "t" * 200, "state": "todo"}]
        row = linked_view([entry("H1", 10, "Ask"), update("H1", 9, links=["+task:R9"])], tasks=tasks,
                          jobs=[])["rows"][0]
        self.assertEqual(len(row["linked"][0]["title"]), HEAD_TITLE_MAX)

    def test_prog_counts_done_over_bound_task_links_only(self):
        records = [entry("H1", 10, "Ask"),
                   update("H1", 9, links=["+task:R7.31", "+task:R1", "+issue:I4", "+task:R99"])]
        row = linked_view(records)["rows"][0]
        self.assertEqual(row["prog"], {"done": 1, "total": 2})

    def test_task_with_a_running_job_makes_the_ask_doing(self):
        records = [entry("H1", 10, "Ask"), update("H1", 9, links=["+task:R5"])]
        row = linked_view(records)["rows"][0]
        self.assertEqual(row["status"], "doing")
        self.assertEqual(row["linked"][0]["jobs"], [{"id": "j5", "model": "Sonnet", "state": "running"}])

    def test_head_link_state_marks_running_jobs_and_issues(self):
        state = head_link_state(LINK_TASKS, LINK_JOBS, LINK_ISSUES)
        self.assertEqual(state["task:R5"], "running")
        self.assertEqual(state["task:R7.31"], "running")
        self.assertEqual(state["task:R1"], "done")
        self.assertEqual(state["issue:I4"], "open")
        self.assertEqual(state["issue:I5"], "done")

    def test_titles_then_rows_are_dropped_to_fit_and_prog_stays(self):
        tasks = [{"id": "T%d" % k, "title": "L" * 200, "state": "partial"} for k in range(240)]
        records = [entry("H%d" % i, 30 + i, "Ask %d" % i) for i in range(1, 41)]
        records += [update("H%d" % i, 1, links=["+task:T%d" % (6 * (i - 1) + k) for k in range(6)])
                    for i in range(1, 41)]
        view = linked_view(records, tasks=tasks, issues=[], jobs=[])
        self.assertLessEqual(_head_size({k: v for k, v in view.items() if k != "askOf"}), HEAD_BYTES_MAX)
        self.assertEqual(view["counts"]["open"], len(view["rows"]))
        self.assertLess(len(view["rows"]), 40)
        ids = [row["id"] for row in view["rows"]]
        self.assertEqual(ids, ["H%d" % i for i in range(1, len(ids) + 1)])  # H1 is the newest here (30 + i minutes ago)
        self.assertTrue(all(row["prog"] == {"done": 0, "total": 6} for row in view["rows"]))
        self.assertTrue(all("title" not in item for row in view["rows"] for item in row.get("linked", [])))
        self.assertLessEqual(len(view["rows"][0]["linked"]), HEAD_LINKED_MAX)

    def test_ask_of_lists_asks_per_task_and_is_top_level_only(self):
        records = [entry("H1", 30, "a"), update("H1", 29, links=["+task:R1"]),
                   entry("H2", 20, "b"), update("H2", 19, links=["+task:R1", "+task:R2"]),
                   entry("H3", 10, "c")]
        result = snap(records)
        self.assertEqual(result["askOf"], {"R1": ["H1", "H2"], "R2": ["H2"]})
        self.assertNotIn("askOf", result["head"])

    def test_ask_of_absent_without_head_records_and_empty_without_asks(self):
        self.assertNotIn("askOf", build_snapshot({}, {}, NOW))
        self.assertEqual(snap([entry("H1", 5, "No links")])["askOf"], {})

    def test_ask_backlinks_keeps_the_newest_five_per_task(self):
        entries = [{"id": "H%d" % i, "links": ["task:R1"]} for i in range(1, 8)]
        self.assertEqual(refs.ask_backlinks(entries), {"R1": ["H3", "H4", "H5", "H6", "H7"]})
        self.assertEqual(refs.ask_backlinks([]), {})


if __name__ == "__main__":
    unittest.main()
