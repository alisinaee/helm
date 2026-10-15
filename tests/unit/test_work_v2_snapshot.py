"""Work v2 snapshot fields (R7.24 W2, R7.25 W2): issuesClosed (newest 5 closed or wontfix issues, additive and left out
when none is closed) and head_link_state passing a failed job through as failed (so the Head screen can show Failed).
The issues stay as they are: open and doing in issues, with kind on each."""

import json
import unittest
from datetime import datetime, timezone

from roadmap.core.snapshot import build_snapshot, head_link_state

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def issue(iid, status, kind="bug", closed=None, created="2026-10-01T10:00:00+00:00", title=None):
    return {"id": iid, "title": title or (iid + " title"), "kind": kind, "sev": 2, "status": status, "tasks": [],
            "by": "you", "created": created, "closed": closed, "note": ""}


def issues_file(*rows):
    return json.dumps({"issues": list(rows)})


def snap(*rows):
    files = {"tasks.json": json.dumps({"updated": "2026-10-15", "phases": [], "tasks": []})}
    if rows:
        files["issues.json"] = issues_file(*rows)
    return build_snapshot(files, {}, NOW)


class IssuesClosedTests(unittest.TestCase):
    def test_key_is_left_out_when_no_issue_is_closed(self):
        out = snap()
        self.assertNotIn("issuesClosed", out)
        self.assertNotIn("issuesClosed", snap(issue("I1", "open")))

    def test_lists_closed_and_wontfix_newest_first_with_kind(self):
        out = snap(issue("I1", "open"),
                   issue("I2", "closed", kind="risk", closed="2026-10-02T09:00:00+00:00"),
                   issue("I3", "wontfix", kind="question", closed="2026-10-05T09:00:00+00:00"),
                   issue("I4", "doing"))
        self.assertEqual([row["id"] for row in out["issuesClosed"]], ["I3", "I2"])
        self.assertEqual(out["issuesClosed"][0], {"id": "I3", "title": "I3 title", "kind": "question",
                                                  "closed": "2026-10-05T09:00:00+00:00"})

    def test_caps_at_five_newest(self):
        rows = [issue("I%d" % n, "closed", closed="2026-10-%02dT09:00:00+00:00" % n) for n in range(1, 8)]
        out = snap(*rows)
        self.assertEqual([row["id"] for row in out["issuesClosed"]], ["I7", "I6", "I5", "I4", "I3"])

    def test_open_issues_stay_in_issues_with_kind(self):
        out = snap(issue("I1", "open", kind="blocker"), issue("I2", "closed"))
        self.assertEqual([row["id"] for row in out["issues"]], ["I1"])
        self.assertEqual(out["issues"][0]["kind"], "blocker")
        self.assertEqual(out["blocked"], [])


class HeadLinkStateTests(unittest.TestCase):
    def test_failed_job_passes_through_as_failed(self):
        state = head_link_state([], [{"id": "j1", "status": "failed"}])
        self.assertEqual(state["job:j1"], "failed")

    def test_running_and_done_pass_through_and_queued_reads_open(self):
        jobs = [{"id": "j1", "status": "running"}, {"id": "j2", "status": "done"}, {"id": "j3", "status": "queued"}]
        state = head_link_state([], jobs)
        self.assertEqual((state["job:j1"], state["job:j2"], state["job:j3"]), ("running", "done", "open"))

    def test_failed_job_does_not_mark_its_task_running(self):
        tasks = [{"id": "P1.1", "state": "todo"}]
        state = head_link_state(tasks, [{"id": "j1", "status": "failed", "task": "P1.1"}])
        self.assertEqual(state["task:P1.1"], "todo")


if __name__ == "__main__":
    unittest.main()
