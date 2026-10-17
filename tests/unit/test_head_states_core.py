"""R7.66: the Head states in the pure fold (roadmap/core/head.py). A bound job that failed gives failed, a bound task on
hold or blocked gives blocked, and the precedence is manual, done, failed, blocked, doing, bound, understood, new."""

import unittest
from datetime import datetime, timezone

from roadmap.core import head

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def e(eid, ts="2026-10-15T09:00:00Z"):
    return {"v": 1, "t": "e", "id": eid, "ts": ts, "src": "hook", "sid": "s1", "acct": "A", "kind": "ask",
            "sum": "Please fix the export button", "len": 28}


def u(eid, set_=None, link=None, by="person"):
    rec = {"v": 1, "t": "u", "id": eid, "ts": "2026-10-15T09:30:00Z", "by": by}
    if set_ is not None:
        rec["set"] = set_
    if link is not None:
        rec["link"] = link
    return rec


def status_of(recs, link_state):
    return head.fold(recs, link_state=link_state, now=NOW)[0]["status"]


class BoundStates(unittest.TestCase):
    def test_failed_job_on_a_link_is_failed(self):
        recs = [e("H1"), u("H1", link=["+job:j1"])]
        self.assertEqual(status_of(recs, {"job:j1": "failed"}), "failed")

    def test_task_on_hold_or_blocked_is_blocked(self):
        for state in ("hold", "blocked"):
            recs = [e("H1"), u("H1", link=["+task:R7.31"])]
            self.assertEqual(status_of(recs, {"task:R7.31": state}), "blocked", state)

    def test_running_task_is_doing_and_a_plain_link_is_bound(self):
        recs = [e("H1"), u("H1", link=["+task:R7.31"])]
        self.assertEqual(status_of(recs, {"task:R7.31": "doing"}), "doing")
        self.assertEqual(status_of(recs, {"task:R7.31": "todo"}), "bound")
        self.assertEqual(status_of(recs, {}), "bound")

    def test_failed_beats_blocked_beats_doing(self):
        recs = [e("H1"), u("H1", link=["+job:j1", "+task:R7.31", "+task:R7.32"])]
        both = {"job:j1": "failed", "task:R7.31": "hold", "task:R7.32": "doing"}
        self.assertEqual(status_of(recs, both), "failed")
        self.assertEqual(status_of(recs, {"task:R7.31": "hold", "task:R7.32": "doing"}), "blocked")

    def test_a_hand_set_status_beats_the_links(self):
        recs = [e("H1"), u("H1", link=["+job:j1"]), u("H1", set_={"status": "needs-you"})]
        self.assertEqual(status_of(recs, {"job:j1": "failed"}), "needs-you")
        recs = [e("H1"), u("H1", link=["+job:j1"]), u("H1", set_={"status": "done"})]
        self.assertEqual(status_of(recs, {"job:j1": "failed"}), "done")

    def test_all_links_done_is_done_and_no_link_stays_queued(self):
        recs = [e("H1"), u("H1", link=["+task:R7.31"])]
        self.assertEqual(status_of(recs, {"task:R7.31": "done"}), "done")
        self.assertEqual(status_of([e("H2")], {}), "new")

    def test_link_bound_while_done_does_not_close_the_ask(self):
        recs = [e("H1"), u("H1", link=["+task:R10.27"])]
        recs[1]["seen"] = ["task:R10.27"]
        self.assertEqual(status_of(recs, {"task:R10.27": "done"}), "bound")

    def test_a_task_that_turns_done_after_the_bind_closes_the_ask(self):
        recs = [e("H1"), u("H1", link=["+task:R10.27"]), u("H1", link=["+task:R10.28"])]
        recs[1]["seen"] = ["task:R10.27"]
        self.assertEqual(status_of(recs, {"task:R10.27": "done", "task:R10.28": "doing"}), "doing")
        self.assertEqual(status_of(recs, {"task:R10.27": "done", "task:R10.28": "done"}), "done")

    def test_plain_bind_to_a_task_that_finishes_later_still_closes(self):
        recs = [e("H1"), u("H1", link=["+task:R10.27"])]
        self.assertEqual(status_of(recs, {"task:R10.27": "done"}), "done")

    def test_understood_is_still_queued_until_bound(self):
        recs = [e("H1"), u("H1", by="head", set_={"kind": "bug", "sum": "Export button fails"})]
        self.assertEqual(status_of(recs, {}), "understood")

    def test_failed_and_blocked_are_open_not_closed(self):
        recs = [e("H1"), u("H1", link=["+job:j1"])]
        row = head.fold(recs, link_state={"job:j1": "failed"}, now=NOW)[0]
        self.assertNotIn(row["status"], head.CLOSED_STATUSES)
        self.assertEqual(head.FAILED_LINK_STATES, ("failed",))
        self.assertEqual(head.BLOCKED_LINK_STATES, ("hold", "blocked"))


if __name__ == "__main__":
    unittest.main()
