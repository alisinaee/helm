"""HEAD-SPEC H1: the pure fold, the status rules, age/stale/carried, and the stdlib heuristics in roadmap/core/head.py."""

import json
import unittest
from datetime import datetime, timezone

from roadmap.core import head

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def e(eid, ts="2026-10-15T09:00:00Z", sid="s1", text="Please fix the export button", kind="ask"):
    return {"v": 1, "t": "e", "id": eid, "ts": ts, "src": "hook", "sid": sid, "acct": "A",
            "kind": kind, "sum": text, "len": len(text)}


def u(eid, by="person", set_=None, link=None, ts="2026-10-15T09:30:00Z"):
    rec = {"v": 1, "t": "u", "id": eid, "ts": ts, "by": by}
    if set_ is not None:
        rec["set"] = set_
    if link is not None:
        rec["link"] = link
    return rec


def s(sid, ev, ts):
    return {"v": 1, "t": "s", "ts": ts, "sid": sid, "acct": "A", "model": "Opus 5.5", "ev": ev}


def one(rows, eid):
    return next(r for r in rows if r["id"] == eid)


class FoldStatusTests(unittest.TestCase):
    def test_new_when_nothing_is_known(self):
        rows = head.fold([e("H1")], now=NOW)
        self.assertEqual(one(rows, "H1")["status"], "new")

    def test_understood_when_head_triaged_kind_and_sum(self):
        recs = [e("H1"), u("H1", by="head", set_={"kind": "bug", "sum": "Export button fails"})]
        self.assertEqual(one(head.fold(recs, now=NOW), "H1")["status"], "understood")

    def test_triage_by_person_does_not_count(self):
        recs = [e("H1"), u("H1", by="person", set_={"kind": "bug", "sum": "x"})]
        self.assertEqual(one(head.fold(recs, now=NOW), "H1")["status"], "new")

    def test_bound_with_one_link(self):
        recs = [e("H1"), u("H1", link=["+task:R7.31"])]
        self.assertEqual(one(head.fold(recs, now=NOW), "H1")["status"], "bound")

    def test_doing_when_linked_task_doing_or_partial_or_job_running(self):
        for state in ("doing", "partial"):
            recs = [e("H1"), u("H1", link=["+task:R7.31"])]
            row = one(head.fold(recs, {"task:R7.31": state}, now=NOW), "H1")
            self.assertEqual(row["status"], "doing", state)
        recs = [e("H1"), u("H1", link=["+job:j599"])]
        row = one(head.fold(recs, {"job:j599": "running"}, now=NOW), "H1")
        self.assertEqual(row["status"], "doing")

    def test_auto_done_when_every_link_done(self):
        recs = [e("H1"), u("H1", link=["+task:R7.31", "+issue:I4"])]
        row = one(head.fold(recs, {"task:R7.31": "done", "issue:I4": "done"}, now=NOW), "H1")
        self.assertEqual(row["status"], "done")
        self.assertTrue(row["auto_done"])

    def test_one_open_link_blocks_auto_done(self):
        recs = [e("H1"), u("H1", link=["+task:R7.31", "+issue:I4"])]
        row = one(head.fold(recs, {"task:R7.31": "done"}, now=NOW), "H1")
        self.assertEqual(row["status"], "bound")

    def test_manual_done_is_not_auto(self):
        recs = [e("H1"), u("H1", by="head", set_={"status": "done"})]
        row = one(head.fold(recs, now=NOW), "H1")
        self.assertEqual(row["status"], "done")
        self.assertFalse(row["auto_done"])

    def test_done_without_links_only_by_hand(self):
        recs = [e("H1")]
        self.assertEqual(one(head.fold(recs, now=NOW), "H1")["status"], "new")

    def test_merged_declined_needs_you_win_over_links(self):
        for status in ("merged", "declined", "needs-you"):
            recs = [e("H1"), u("H1", link=["+task:R7.31"]), u("H1", set_={"status": status})]
            row = one(head.fold(recs, {"task:R7.31": "doing"}, now=NOW), "H1")
            self.assertEqual(row["status"], status)

    def test_reopen_clears_manual_done_and_does_not_auto_close(self):
        recs = [e("H1"), u("H1", link=["+task:R7.31"]), u("H1", set_={"status": "done"}),
                u("H1", set_={"status": "open"})]
        row = one(head.fold(recs, {"task:R7.31": "done"}, now=NOW), "H1")
        self.assertEqual(row["status"], "bound")

    def test_merge_into_is_recorded_and_status_stays_manual(self):
        recs = [e("H1"), u("H1", set_={"into": "H9"})]
        row = one(head.fold(recs, now=NOW), "H1")
        self.assertEqual(row["into"], "H9")
        self.assertEqual(row["status"], "new")

    def test_update_for_unknown_entry_is_ignored(self):
        rows = head.fold([u("H404", link=["+task:R1"])], now=NOW)
        self.assertEqual(rows, [])

    def test_duplicate_entry_id_keeps_first(self):
        recs = [e("H1", text="first text here"), e("H1", text="second text here")]
        rows = head.fold(recs, now=NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sum"], "first text here")

    def test_link_cap_six_and_minus_removes(self):
        refs = ["+task:R%d" % i for i in range(1, 9)]
        recs = [e("H1"), u("H1", link=refs), u("H1", link=["-task:R1"])]
        row = one(head.fold(recs, now=NOW), "H1")
        self.assertEqual(len(row["links"]), 5)
        self.assertNotIn("task:R1", row["links"])

    def test_invalid_link_refs_are_ignored(self):
        recs = [e("H1"), u("H1", link=["+nonsense:x", "+task:", "task:R1", 7])]
        self.assertEqual(one(head.fold(recs, now=NOW), "H1")["links"], [])


class FoldAgeTests(unittest.TestCase):
    def test_age_and_amber_and_stale_for_new_entries(self):
        row = one(head.fold([e("H1", ts="2026-10-15T11:00:00Z")], now=NOW), "H1")
        self.assertEqual(row["age_min"], 60.0)
        self.assertTrue(row["amber"])
        self.assertFalse(row["stale"])

    def test_stale_after_two_hours_unhandled(self):
        row = one(head.fold([e("H1", ts="2026-10-15T09:00:00Z")], now=NOW), "H1")
        self.assertEqual(row["age_min"], 180.0)
        self.assertTrue(row["stale"])

    def test_no_age_once_bound(self):
        recs = [e("H1", ts="2026-10-15T09:00:00Z"), u("H1", link=["+task:R1"])]
        row = one(head.fold(recs, now=NOW), "H1")
        self.assertIsNone(row["age_min"])
        self.assertFalse(row["stale"])

    def test_future_timestamp_clamps_age_to_zero(self):
        row = one(head.fold([e("H1", ts="2026-10-15T13:00:00Z")], now=NOW), "H1")
        self.assertEqual(row["age_min"], 0.0)

    def test_bad_timestamp_gives_no_age(self):
        row = one(head.fold([e("H1", ts="yesterday")], now=NOW), "H1")
        self.assertIsNone(row["age_min"])
        self.assertFalse(row["amber"])


class FoldCarriedTests(unittest.TestCase):
    def test_open_entry_from_older_session_is_carried(self):
        recs = [s("old", "start", "2026-10-14T08:00:00Z"), e("H1", ts="2026-10-14T08:10:00Z", sid="old"),
                s("new", "claim", "2026-10-15T09:00:00Z")]
        self.assertTrue(one(head.fold(recs, now=NOW), "H1")["carried"])

    def test_entry_from_current_session_is_not_carried(self):
        recs = [s("new", "claim", "2026-10-15T09:00:00Z"), e("H1", ts="2026-10-15T09:10:00Z", sid="new")]
        self.assertFalse(one(head.fold(recs, now=NOW), "H1")["carried"])

    def test_closed_entry_is_never_carried(self):
        recs = [e("H1", ts="2026-10-14T08:10:00Z", sid="old"), u("H1", set_={"status": "declined"}),
                s("new", "claim", "2026-10-15T09:00:00Z")]
        self.assertFalse(one(head.fold(recs, now=NOW), "H1")["carried"])

    def test_no_claim_means_nothing_carried(self):
        recs = [e("H1", ts="2026-10-14T08:10:00Z", sid="old")]
        self.assertFalse(one(head.fold(recs, now=NOW), "H1")["carried"])


class ParseTests(unittest.TestCase):
    def test_unknown_version_and_type_are_skipped(self):
        lines = [
            json.dumps({"v": 1, "t": "e", "id": "H1"}),
            json.dumps({"v": 2, "t": "e", "id": "H2"}),
            json.dumps({"v": 1, "t": "x", "id": "H3"}),
            "not json",
            "",
            json.dumps([1, 2]),
        ]
        records, skipped = head.parse_lines(lines)
        self.assertEqual([r["id"] for r in records], ["H1"])
        self.assertEqual(skipped, 4)

    def test_future_version_entry_does_not_reach_fold(self):
        lines = [json.dumps(e("H1")), json.dumps(dict(e("H2"), v=2))]
        records, _ = head.parse_lines(lines)
        self.assertEqual([r["id"] for r in head.fold(records, now=NOW)], ["H1"])

    def test_parse_link(self):
        self.assertEqual(head.parse_link("task:R7.31"), ("task", "R7.31"))
        self.assertIsNone(head.parse_link("task:"))
        self.assertIsNone(head.parse_link("bogus:1"))
        self.assertIsNone(head.parse_link("R7.31"))

    def test_parse_ts(self):
        self.assertEqual(head.parse_ts("2026-10-15T09:12:03Z").hour, 9)
        self.assertIsNone(head.parse_ts("2026-10-15 09:12:03"))
        self.assertIsNone(head.parse_ts(None))


class KindTests(unittest.TestCase):
    def test_table_rows(self):
        cases = {
            "The export is broken": "bug?",
            "This does not work on Safari": "bug?",
            "Always use the table view": "rule?",
            "Never commit secrets": "rule?",
            "Yes": "decision?",
            "We go with option B": "decision?",
            "I prefer short labels": "preference?",
            "I want the board to be dark": "preference?",
            "Review the diff": "review?",
            "Can we ship this?": "question?",
            "Add a dark mode toggle": "ask?",
        }
        for text, want in cases.items():
            self.assertEqual(head.guess_kind(text), want, text)

    def test_table_order_bug_beats_rule(self):
        self.assertEqual(head.guess_kind("never let the export fail"), "bug?")
        self.assertEqual(head.guess_kind("never let the export stop"), "rule?")
        self.assertEqual(head.guess_kind("the page is broken and must be fixed"), "bug?")

    def test_imperative_with_question_mark_is_not_a_question(self):
        self.assertEqual(head.guess_kind("Add a column for owner?"), "ask?")

    def test_checkout_is_not_review(self):
        self.assertEqual(head.guess_kind("Checkout the branch"), "ask?")


class SummaryTests(unittest.TestCase):
    def test_greetings_and_filler_dropped(self):
        self.assertEqual(head.summarize("Hi, please also fix the export button"), "fix the export button")

    def test_tell_prefix_dropped(self):
        self.assertEqual(head.summarize("tell opus: split the status work"), "split the status work")

    def test_first_clause_of_two_words_wins(self):
        self.assertEqual(head.summarize("Fix the login. Then add tests."), "Fix the login.")

    def test_single_word_clause_is_skipped(self):
        self.assertEqual(head.summarize("Ok. Fix login now."), "Fix login now.")

    def test_cut_at_100_chars_with_ellipsis(self):
        text = "word " * 60
        out = head.summarize(text)
        self.assertLessEqual(len(out), 100)
        self.assertTrue(out.endswith("…"))

    def test_empty_gives_empty(self):
        self.assertEqual(head.summarize(None), "")
        self.assertEqual(head.summarize("   "), "")


class DupTests(unittest.TestCase):
    def test_jaccard_ignores_stopwords_and_case(self):
        self.assertEqual(head.jaccard("Export Button", "export the button"), 1.0)
        self.assertEqual(head.jaccard("fix export", "deploy board"), 0.0)
        self.assertAlmostEqual(head.jaccard("export button broken", "export button fails"), 0.5)

    def test_jaccard_empty_is_zero(self):
        self.assertEqual(head.jaccard("the a an", "export"), 0.0)

    def test_dup_suggested_at_threshold_for_open_entry(self):
        recs = [e("H9", ts="2026-08-01T09:00:00Z", text="export csv file button"),
                e("H10", ts="2026-10-15T09:00:00Z", text="export csv file button now")]
        row = one(head.fold(recs, now=NOW), "H10")
        self.assertEqual(row["dup"]["id"], "H9")
        self.assertGreaterEqual(row["dup"]["score"], 0.6)

    def test_no_dup_below_threshold(self):
        recs = [e("H1", text="export csv file button"), e("H2", text="dark mode for the board")]
        self.assertIsNone(one(head.fold(recs, now=NOW), "H2")["dup"])

    def test_closed_old_entry_is_not_a_dup_candidate(self):
        recs = [e("H1", ts="2026-01-01T09:00:00Z", text="export csv file button"),
                u("H1", set_={"status": "done"}),
                e("H2", ts="2026-10-15T09:00:00Z", text="export csv file button")]
        self.assertIsNone(one(head.fold(recs, now=NOW), "H2")["dup"])

    def test_dup_is_only_against_earlier_entries(self):
        recs = [e("H1", text="export csv file button"), e("H2", text="export csv file button")]
        rows = head.fold(recs, now=NOW)
        self.assertIsNone(one(rows, "H1")["dup"])
        self.assertEqual(one(rows, "H2")["dup"]["id"], "H1")


class LinkedRunningWorkTests(unittest.TestCase):
    """HEAD-SPEC section 12: the fold reads running work on a linked task or job as doing, and nothing else as doing."""

    def test_running_job_on_a_linked_task_makes_the_ask_doing(self):
        recs = [e("H1"), u("H1", link=["+task:R5"])]
        self.assertEqual(one(head.fold(recs, {"task:R5": "running"}, now=NOW), "H1")["status"], "doing")
        self.assertEqual(one(head.fold(recs, {"task:R5": "todo"}, now=NOW), "H1")["status"], "bound")

    def test_finished_job_does_not_make_it_doing(self):
        recs = [e("H1"), u("H1", link=["+job:j7"])]
        self.assertEqual(one(head.fold(recs, {"job:j7": "open"}, now=NOW), "H1")["status"], "bound")
        self.assertEqual(one(head.fold(recs, {"job:j7": "done"}, now=NOW), "H1")["status"], "done")


class VerifiedGapTests(unittest.TestCase):
    """Test gaps confirmed in docs/reviews/agy-head-testgaps-core.md (rows for roadmap/core/head.py)."""

    def test_head_triage_needs_both_kind_and_sum(self):
        kind_only = one(head.fold([e("H1"), u("H1", by="head", set_={"kind": "bug"})], now=NOW), "H1")
        sum_only = one(head.fold([e("H1"), u("H1", by="head", set_={"sum": "Export broken"})], now=NOW), "H1")
        for row in (kind_only, sum_only):
            self.assertFalse(row["triaged"])
            self.assertEqual(row["status"], "new")

    def test_duplicate_link_is_not_appended_and_missing_minus_is_ignored(self):
        recs = [e("H1"), u("H1", link=["+task:R1"]), u("H1", link=["+task:R1"]), u("H1", link=["-task:R99"])]
        self.assertEqual(one(head.fold(recs, now=NOW), "H1")["links"], ["task:R1"])

    def test_understood_entry_gets_age_amber_and_stale_like_new(self):
        recs = [e("H1", ts="2026-10-15T09:00:00Z"), u("H1", by="head", set_={"kind": "bug", "sum": "Export broken"})]
        row = one(head.fold(recs, now=NOW), "H1")
        self.assertEqual(row["status"], "understood")
        self.assertEqual(row["age_min"], 180.0)
        self.assertTrue(row["amber"])
        self.assertTrue(row["stale"])

    def test_custom_amber_and_stale_thresholds_are_honoured(self):
        recs = [e("H1", ts="2026-10-15T11:00:00Z")]  # 60 minutes old
        quiet = one(head.fold(recs, now=NOW, amber_min=90, stale_min=200), "H1")
        self.assertFalse(quiet["amber"])
        self.assertFalse(quiet["stale"])
        loud = one(head.fold(recs, now=NOW, amber_min=30, stale_min=50), "H1")
        self.assertTrue(loud["amber"])
        self.assertTrue(loud["stale"])

    def test_open_entry_without_session_record_falls_back_to_its_own_ts(self):
        before = [e("H1", ts="2026-10-14T08:10:00Z", sid="old"), s("new", "claim", "2026-10-15T09:00:00Z")]
        self.assertTrue(one(head.fold(before, now=NOW), "H1")["carried"])
        after = [e("H2", ts="2026-10-15T09:30:00Z", sid="old"), s("new", "claim", "2026-10-15T09:00:00Z")]
        self.assertFalse(one(head.fold(after, now=NOW), "H2")["carried"])

    def test_recent_closed_entry_is_a_duplicate_candidate(self):
        recs = [e("H1", ts="2026-10-01T09:00:00Z", text="export csv file button"),
                u("H1", set_={"status": "done"}),
                e("H2", ts="2026-10-15T09:00:00Z", text="export csv file button")]
        rows = head.fold(recs, now=NOW)
        self.assertEqual(one(rows, "H1")["status"], "done")
        self.assertEqual(one(rows, "H2")["dup"], {"id": "H1", "score": 1.0})

    def test_best_duplicate_is_the_highest_score_not_the_first(self):
        recs = [e("H2", text="export csv file button broken"),  # 4 of 6 words shared with H3: 0.67
                e("H1", text="export csv file button"),          # 4 of 5 shared with H3: 0.8
                e("H3", text="export csv file button now")]
        self.assertEqual(one(head.fold(recs, now=NOW), "H3")["dup"]["id"], "H1")

    def test_question_mark_with_no_words_is_an_ask(self):
        self.assertEqual(head.guess_kind("???"), "ask?")

    def test_parse_link_strips_value_and_rejects_non_strings(self):
        self.assertEqual(head.parse_link("task:  R7.31 "), ("task", "R7.31"))
        self.assertIsNone(head.parse_link(None))
        self.assertIsNone(head.parse_link(123))


class SuggestBindsTests(unittest.TestCase):
    TASKS = [{"id": "R7.31", "title": "Head section design"},
             {"id": "R7.40", "title": "Export button in the map view"},
             {"id": "R2.1", "title": "Login page"}]
    ISSUES = [{"id": "I4", "title": "Export button fails"}]

    def test_id_mentioned_in_text_scores_one(self):
        self.assertEqual(head.suggest_binds("ship R7.31 today", self.TASKS, []), ["task:R7.31"])

    def test_issue_id_mentioned_in_text(self):
        self.assertEqual(head.suggest_binds("see I4 again", self.TASKS, self.ISSUES), ["issue:I4"])

    def test_unknown_id_is_ignored(self):
        self.assertEqual(head.suggest_binds("do R9.9 now", self.TASKS, []), [])

    def test_title_overlap_gives_the_best_match_first(self):
        refs = head.suggest_binds("Fix the export button", self.TASKS, self.ISSUES)
        self.assertEqual(refs, ["issue:I4", "task:R7.40"])

    def test_at_most_two_refs(self):
        tasks = [{"id": "T%d" % i, "title": "export map button"} for i in range(1, 5)]
        self.assertEqual(len(head.suggest_binds("export map button", tasks, [])), head.BIND_MAX)

    def test_below_minimum_gives_nothing(self):
        self.assertEqual(head.suggest_binds("unrelated words here", self.TASKS, self.ISSUES), [])

    def test_empty_text_or_no_rows_gives_nothing(self):
        self.assertEqual(head.suggest_binds("", self.TASKS, self.ISSUES), [])
        self.assertEqual(head.suggest_binds("export button", [], []), [])
        self.assertEqual(head.suggest_binds(None, None, None), [])

    def test_bad_rows_are_skipped(self):
        rows = [None, {"title": "no id"}, {"id": 5, "title": "export"}, {"id": "R7.40", "title": "export button"}]
        self.assertEqual(head.suggest_binds("export button", rows, None), ["task:R7.40"])

    def test_same_input_same_output(self):
        first = head.suggest_binds("Fix the export button", self.TASKS, self.ISSUES)
        self.assertEqual(first, head.suggest_binds("Fix the export button", self.TASKS, self.ISSUES))


if __name__ == "__main__":
    unittest.main()
