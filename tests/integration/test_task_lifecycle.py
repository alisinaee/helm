"""Flow 4: the task lifecycle. The six-line plan example is imported, tasks are started and done with --tokens from the
CLI and through /api/v1/cmd (the budget is fed exactly once each), the status screen stays short, subtasks are added and
toggled, a blocker issue marks its task blocked in the snapshot until it is closed, and a comment is kept."""

import json
import unittest

from tests.integration.harness import stack

PLAN_EXAMPLE = """P M1 todo | Foundations
T M1.1 todo 20 haiku/low | Scaffold repo, CI and lint
T M1.2 todo 40 sonnet/medium c:sonnet/8 | Data model and storage layer
T M1.3 todo 5 haiku/low ! | Create hosting account and API key # needs your login
T M1.4 todo 80 opus/high c:opus/15 | Sync engine design and spike
T M1.5 todo 10 haiku/low | README quick start
"""


def spent_total(budget, task_id):
    return sum(budget["spent"].get(task_id, {}).values())


class TaskLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sandbox, self.server = stack(self)
        sb = self.sandbox
        with open(sb.root + "/plan.txt", "w", encoding="utf-8") as fh:
            fh.write(PLAN_EXAMPLE)
        imported = sb.cli_json(["plan", "import", sb.root + "/plan.txt"])
        self.assertEqual((imported["changed"], imported["wrote"]), (6, True))

    def task(self, task_id):
        snap = self.server.snapshot(self.sandbox.pid)
        return next(t for t in snap["tasks"] if t["id"] == task_id)

    def test_plan_import_then_start_and_done_feed_the_budget_once_each(self):
        sb = self.sandbox
        listed = sb.cli(["task", "list", "--phase", "M1"]).stdout.splitlines()
        self.assertEqual(len(listed), 5)
        self.assertTrue(listed[0].startswith("T M1.1 todo"))

        self.assertIn("M1.1 partial", sb.cli(["task", "start", "M1.1", "--tokens", "10"]).stdout)
        self.assertIn("M1.1 done", sb.cli(["task", "done", "M1.1", "--tokens", "30"]).stdout)
        self.assertEqual(spent_total(sb.read_doc("budget.json"), "M1.1"), 10.0)

        reply = self.server.cmd("task.status", {"id": "M1.2", "status": "done", "tokensK": 20})
        self.assertTrue(reply["data"]["budgetFed"])
        again = self.server.cmd("task.status", {"id": "M1.2", "status": "done", "tokensK": 20})
        self.assertFalse(again["data"]["changed"])
        self.assertEqual(spent_total(sb.read_doc("budget.json"), "M1.2"), 20.0)

        self.assertEqual(self.task("M1.1")["state"], "done")
        self.assertEqual(self.task("M1.2")["state"], "done")

    def test_status_stays_within_eight_lines_and_700_characters(self):
        self.server.cmd("task.status", {"id": "M1.1", "status": "done", "tokensK": 20})
        text = self.sandbox.cli(["status"]).stdout
        self.assertLessEqual(len(text.splitlines()), 8)
        self.assertLessEqual(len(text), 700)

    def test_subtasks_are_added_and_toggled_from_the_cli_and_the_gui(self):
        sb, srv = self.sandbox, self.server
        added = sb.cli_json(["subtask", "add", "M1.3", "Write the failing test"])
        self.assertEqual(added["addr"], "M1.3/1")
        self.assertIn("M1.3/1 done", sb.cli(["subtask", "done", "M1.3/1"]).stdout)
        self.assertEqual(self.task("M1.3")["subs"], [{"t": "Write the failing test", "d": True}])

        toggled = srv.cmd("subtask.toggle", {"addr": "M1.3/1", "done": False})
        self.assertTrue(toggled["data"]["changed"])
        self.assertEqual(self.task("M1.3")["subs"][0]["d"], False)

        second = srv.cmd("subtask.add", {"id": "M1.3", "title": "Review it"})
        self.assertEqual(second["data"]["addr"], "M1.3/2")
        self.assertEqual(len(self.task("M1.3")["subs"]), 2)

    def test_blocker_issue_marks_the_task_blocked_until_it_is_closed(self):
        sb, srv = self.sandbox, self.server
        opened = sb.cli_json(["issue", "new", "--kind", "blocker", "--task", "M1.4", "--sev", "1",
                              "Vendor API key missing"])
        self.assertEqual((opened["id"], opened["status"]), ("I1", "open"))
        self.assertEqual(srv.snapshot(sb.pid)["blocked"], ["M1.4"])

        closed = srv.cmd("issue.close", {"id": "I1"})
        self.assertEqual(closed["data"]["status"], "closed")
        self.assertEqual(srv.snapshot(sb.pid)["blocked"], [])

    def test_a_comment_from_the_cli_is_kept_in_the_snapshot(self):
        sb, srv = self.sandbox, self.server
        self.assertIn("commented M1.1", sb.cli(["comment", "M1.1", "Looks good"]).stdout)
        comments = srv.snapshot(sb.pid)["comments"]["M1.1"]
        self.assertEqual([c["t"] for c in comments], ["Looks good"])
        self.assertEqual(json.loads(json.dumps(comments))[0]["on"], "M1.1")


if __name__ == "__main__":
    unittest.main()
