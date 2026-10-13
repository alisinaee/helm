"""Status lines from the command layer, plan view and plan move, inbox ordering and budget, comments and subtasks on
the CLI. Budgets: status at most 8 lines and 700 characters with the four new lines present, plan view at most 15
lines, inbox at most 6 lines, budget show at most 8 lines."""

import datetime

from roadmap.commands import status as status_cmd
from roadmap.services import commands, tasks
from tests.unit.test_cmd_support import CmdCase, at


class StatusLinesTests(CmdCase):
    def test_status_keeps_all_four_new_lines_within_budget(self):
        self.op("task.start", {"id": "P1.1"}, now=at(0))
        self.op("question.ask", {"text": "deploy now, or wait for the review?", "opts": ["now", "wait"]}, now=at(0))
        self.op("issue.new", {"title": "Login fails on Safari", "kind": "blocker", "sev": 1}, now=at(0))
        self.op("subtask.add", {"id": "P1.2", "title": "x"}, now=at(0))
        self.cli(["job", "start", "Engine work", "haiku", "P1.2"])
        self.cli(["job", "done", "j1", "--tokens", "12"])
        self.cli(["job", "start", "Still running", "sonnet", "P2.1"])
        code, out, err = self.cli(["status"])
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertLessEqual(len(lines), 8)
        self.assertLessEqual(len(out), 700)
        for prefix in ("ask: ", "queue: ", "issues: ", "budget: "):
            self.assertTrue(any(line.startswith(prefix) for line in lines), prefix + " missing from " + out)
        self.assertIn("run: j2 sonnet P2.1", out)

    def test_status_lines_when_nothing_is_going_on(self):
        code, out, _ = self.cli(["status"])
        self.assertEqual(code, 0)
        self.assertIn("ask: none open", out.splitlines())
        self.assertIn("queue: empty", out.splitlines())
        self.assertIn("issues: none open", out.splitlines())
        self.assertIn("budget: 0k spent, no project limit", out.splitlines())

    def test_budget_line_shows_the_project_limit_when_set(self):
        from roadmap.services import budget
        budget.set_limit(self.data, "project", None, 100)
        _, out, _ = self.cli(["status"])
        self.assertIn("budget: 0k spent of 100k", out.splitlines())

    def test_status_json_lines_match_the_text(self):
        code, body = self.envelope(["status"])
        self.assertEqual(code, 0)
        self.assertTrue(any(line.startswith("queue: ") for line in body["data"]["lines"]))

    def test_compose_drops_the_lowest_priority_lines_first(self):
        base = ["demo  updated x", "left 1", "P1 0%", "run: j1 haiku P1.1 1m", "next: P1.2 sonnet 40k a",
                "you: P1.3 b"]
        extras = {"ask": "ask: none open", "queue": "queue: empty", "issues": "issues: none open",
                  "budget": "budget: 0k spent, no project limit"}
        lines = status_cmd.compose(base, extras)
        self.assertEqual(lines[:4], ["demo  updated x", "left 1", "P1 0%", "run: j1 haiku P1.1 1m"])
        self.assertIn("budget: 0k spent, no project limit", lines)
        self.assertNotIn("next: P1.2 sonnet 40k a", lines)
        self.assertLessEqual(len(lines), 8)


class PlanViewAndMoveTests(CmdCase):
    def test_plan_view_shows_phases_and_open_tasks_within_fifteen_lines(self):
        code, out, err = self.cli(["plan", "view"])
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertLessEqual(len(lines), 15)
        self.assertEqual(lines[0], "P1 todo 0% Engine")
        self.assertIn("  P1.1 todo First task", lines)

    def test_plan_view_truncates_long_plans_with_a_pointer(self):
        rows = ["P P9 todo | Big"] + ["T P9.%d todo 1 haiku/low | task %d" % (n, n) for n in range(1, 30)]
        path = self.tmp + "/big.txt"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")
        self.cli(["plan", "import", path])
        _, out, _ = self.cli(["plan", "view"])
        lines = out.splitlines()
        self.assertLessEqual(len(lines), 15)
        self.assertIn("roadmap task list", lines[-1])

    def test_plan_move_on_the_cli_and_its_errors(self):
        code, out, err = self.cli(["plan", "move", "P1.3", "--before", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "moved P1.3 before P1.1"), err)
        self.assertEqual([t["id"] for t in tasks.load(self.data)["tasks"] if t["id"].startswith("P1.")],
                         ["P1.3", "P1.1", "P1.2"])
        code, _, err = self.cli(["plan", "move", "P1.3"])
        self.assertEqual(code, 2)
        self.assertIn("next:", err)
        code, _, err = self.cli(["plan", "move", "P1.3", "--after", "P9.9"])
        self.assertEqual(code, 3)
        self.assertIn("next:", err)


class InboxTests(CmdCase):
    def test_inbox_orders_queued_then_answered_then_open_and_stays_within_six_lines(self):
        self.op("task.start", {"id": "P1.1"}, now=at(0))
        self.op("question.ask", {"text": "first?", "opts": ["yes", "no"]}, now=at(10))
        self.op("question.answer", {"id": "Q1", "value": "no"}, now=at(20))
        self.op("question.ask", {"text": "second?", "opts": ["yes", "no"]}, now=at(30))
        lines = commands.inbox_lines(self.data, now=at(60))
        self.assertEqual(lines[0], "queued: start P1.1 by -")
        self.assertEqual(lines[1], "answered: Q1 no")
        self.assertEqual(lines[2], "open: Q2 second?")
        self.assertLessEqual(len(lines), 6)

    def test_answers_older_than_a_day_are_not_newly_answered(self):
        self.op("question.ask", {"text": "old?", "opts": ["yes", "no"]}, now=at(0))
        self.op("question.answer", {"id": "Q1", "value": "yes"}, now=at(0))
        lines = commands.inbox_lines(self.data, now=at(0) + datetime.timedelta(days=2))
        self.assertEqual(lines, ["inbox: nothing waiting"])

    def test_inbox_on_the_cli_is_at_most_six_lines(self):
        for n in range(4):
            self.cli(["ask", "q %d" % n])
        code, out, err = self.cli(["inbox"])
        self.assertEqual(code, 0, err)
        self.assertLessEqual(len(out.splitlines()), 6)


class CommentAndSubtaskCliTests(CmdCase):
    def test_comment_then_comments_last(self):
        self.assertEqual(self.cli(["comment", "P1.1", "first note"])[1].strip(), "commented P1.1")
        self.cli(["comment", "P1.1", "second note"])
        code, out, err = self.cli(["comments", "P1.1", "--last", "1"])
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIn("second note", out)

    def test_comments_with_none_says_so(self):
        code, out, _ = self.cli(["comments", "P2.1"])
        self.assertEqual((code, out.strip()), (0, "no comments on P2.1"))

    def test_comment_refuses_a_bad_target_with_next(self):
        code, _, err = self.cli(["comment", "not an id!", "hello"])
        self.assertEqual(code, 2)
        self.assertIn("next:", err)

    def test_subtask_add_then_done_twice(self):
        code, out, err = self.cli(["subtask", "add", "P1.1", "write", "the", "parser"])
        self.assertEqual((code, out.strip()), (0, "P1.1/1 added"), err)
        self.assertEqual(self.cli(["subtask", "done", "P1.1/1"])[1].strip(), "P1.1/1 done")
        self.assertEqual(self.cli(["subtask", "done", "P1.1/1"])[1].strip(), "P1.1/1 done (no change)")
        self.assertEqual(tasks.get(self.data, "P1.1")["subs"][0]["t"], "write the parser")

    def test_subtask_done_on_a_missing_subtask_is_not_found_with_next(self):
        code, _, err = self.cli(["subtask", "done", "P1.1/4"])
        self.assertEqual(code, 3)
        self.assertIn("next:", err)
