"""Gap tests for the command layer (services/commands.py and services/cmdops.py): the queue conflict, the replies of
task.start, task.stop and subtask.add, issue.link and its undo, the phone undo rule, a failing inverse, commands.write,
the one-line status texts (ask, queue, issues), and the registry ops control.override, limit.rm and rules.sync.

Everything runs in a temp ROADMAP_HOME with temp project folders. Nothing reaches the network, the keychain or the
real home. The one-line status texts are checked against their exact format."""

import os
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import agentguard, commands, issues, questions, queue, tasks
from tests.unit.test_cmd_support import CmdCase, at
from tests.unit.test_cmdops import OpsCase


class QueueConflictTests(CmdCase):
    def test_a_stop_for_a_task_already_queued_is_a_conflict_and_changes_nothing(self):
        self.op("task.start", {"id": "P1.1"}, now=at(0))
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.stop", {"id": "P1.1"}, now=at(1))
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(ctx.exception.message, "P1.1 is already queued; not changed")
        entries = queue.list_queue(self.data)
        self.assertEqual([(e["task"], e.get("op")) for e in entries], [("P1.1", None)])


class TaskQueueReplyTests(CmdCase):
    def test_task_start_replies_queued_and_adds_one_queue_entry(self):
        reply = self.op("task.start", {"id": "P1.1", "by": "gui"}, now=at(0))
        self.assertEqual(reply["data"], {"task": "P1.1", "queued": True})
        self.assertEqual([e["task"] for e in queue.list_queue(self.data)], ["P1.1"])
        self.assertTrue(reply["undo"])

    def test_task_stop_replies_stop_and_queues_a_stop_entry(self):
        reply = self.op("task.stop", {"id": "P1.2"}, now=at(0))
        self.assertEqual(reply["data"], {"task": "P1.2", "stop": True})
        entries = queue.list_queue(self.data)
        self.assertEqual([(e["task"], e.get("op")) for e in entries], [("P1.2", "stop")])

    def test_task_start_of_an_unknown_task_is_not_found_with_next(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.start", {"id": "P9.9"}, now=at(0))
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertTrue(ctx.exception.next)


class SubtaskAddReplyTests(CmdCase):
    def test_subtask_add_replies_with_the_new_address_and_keeps_the_title(self):
        reply = self.op("subtask.add", {"id": "P1.1", "title": "sub"}, now=at(0))
        self.assertEqual(reply["data"]["addr"], "P1.1/1")
        subs = tasks.get(self.data, "P1.1")["subs"]
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["t"], "sub")
        self.assertIn("added P1.1/1", self.read_lines("activity.jsonl")[-1]["sum"])


class IssueLinkTests(CmdCase):
    def setUp(self):
        super().setUp()
        self.issue = self.op("issue.new", {"title": "Login fails", "kind": "bug"}, now=at(0))["data"]["id"]

    def test_link_adds_the_tasks_and_undo_puts_the_prior_list_back(self):
        linked = self.op("issue.link", {"id": self.issue, "tasks": ["P1.1"]}, now=at(1))
        self.assertEqual(linked["data"], {"id": self.issue, "tasks": ["P1.1"], "changed": True})
        self.assertEqual(issues.get(self.data, self.issue)["tasks"], ["P1.1"])
        self.op("undo", {"activity": linked["activity"]}, now=at(2))
        self.assertEqual(issues.get(self.data, self.issue)["tasks"], [])

    def test_linking_the_same_task_again_is_no_change_and_has_no_undo(self):
        self.op("issue.link", {"id": self.issue, "tasks": ["P1.1"]}, now=at(1))
        again = self.op("issue.link", {"id": self.issue, "tasks": ["P1.1"]}, now=at(2))
        self.assertFalse(again["data"]["changed"])
        self.assertFalse(again["undo"])

    def test_linking_an_unknown_task_is_not_found_and_links_nothing(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("issue.link", {"id": self.issue, "tasks": ["P9.9"]}, now=at(1))
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertEqual(issues.get(self.data, self.issue)["tasks"], [])


class PhoneUndoTests(CmdCase):
    def test_the_phone_cannot_undo_a_change_made_on_the_cli(self):
        done = self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        with self.assertRaises(RoadmapError) as ctx:
            commands.run("undo", {"activity": done["activity"]}, "phone", self.data, now=at(1))
        self.assertEqual(ctx.exception.code, "forbidden")
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        self.assertEqual(ctx.exception.message, "the phone may undo only its own changes")
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "done")

    def test_the_phone_may_undo_its_own_change(self):
        done = commands.run("task.status", {"id": "P1.1", "status": "done"}, "phone", self.data, now=at(0))
        commands.run("undo", {"activity": done["activity"]}, "phone", self.data, now=at(1))
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "todo")


class FailingInverseTests(CmdCase):
    def test_a_failing_inverse_is_logged_as_undo_failed_and_can_be_retried(self):
        done = self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        with mock.patch.object(commands, "_execute", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                self.op("undo", {"activity": done["activity"]}, now=at(1))
        rows = self.read_lines(commands.UNDO_FILE)
        self.assertIn(done["activity"], [r.get("undoFailed") for r in rows])
        self.assertFalse(any(r.get("undid") == done["activity"] for r in rows))
        retry = self.op("undo", {"activity": done["activity"]}, now=at(2))
        self.assertEqual(retry["data"]["undone"], done["activity"])
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "todo")


class WriteTests(CmdCase):
    def test_write_runs_the_op_on_the_project_and_recomputes_the_control_state(self):
        with mock.patch.object(agentguard, "source_name", return_value="cli"), \
                mock.patch("roadmap.services.control.after_write") as after:
            reply = commands.write("demo", "task.status", {"id": "P1.1", "status": "done"}, "roadmap status")
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["data"]["status"], "done")
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "done")
        after.assert_called_once_with("demo")

    def test_write_to_an_unknown_project_names_the_next_command(self):
        with self.assertRaises(RoadmapError) as ctx:
            commands.write("nobody", "task.status", {"id": "P1.1", "status": "done"}, "roadmap status")
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertEqual(ctx.exception.next, "roadmap status")


class StatusLineTests(CmdCase):
    def test_ask_line_names_the_first_open_question_and_counts_the_rest(self):
        self.assertEqual(commands.ask_line(self.data), "ask: none open")
        questions.ask(self.data, "P1.1", "Ship the parser now?", opts=["yes", "no"], now=at(0))
        questions.ask(self.data, "P1.2", "Second thought", opts=["yes", "no"], now=at(1))
        self.assertEqual(commands.ask_line(self.data), "ask: 2 open: Q1 Ship the parser now? (+1)")

    def test_queue_line_shows_the_first_three_names_with_stop_and_the_rest_counted(self):
        self.assertEqual(commands.queue_line(self.data), "queue: empty")
        self.op("task.start", {"id": "P1.1"}, now=at(0))
        self.op("task.start", {"id": "P1.2"}, now=at(1))
        self.op("task.stop", {"id": "P2.1"}, now=at(2))
        self.assertEqual(commands.queue_line(self.data), "queue: 3 waiting: P1.1 P1.2 stop P2.1")
        self.op("task.start", {"id": "P1.3"}, now=at(3))
        self.assertEqual(commands.queue_line(self.data), "queue: 4 waiting: P1.1 P1.2 stop P2.1 (+1)")

    def test_issues_line_counts_open_issues_by_kind(self):
        self.assertEqual(commands.issues_line(self.data), "issues: none open")
        self.op("issue.new", {"title": "Login fails", "kind": "bug"}, now=at(0))
        risk = self.op("issue.new", {"title": "Sync slow", "kind": "risk"}, now=at(1))["data"]["id"]
        line = commands.issues_line(self.data)
        self.assertTrue(line.startswith("issues: 2 open ("), line)
        self.assertIn("1 bug", line)
        self.assertIn("1 risk", line)
        self.op("issue.close", {"id": risk}, now=at(2))
        self.assertEqual(commands.issues_line(self.data), "issues: 1 open (1 bug)")


class RegistryOpTests(OpsCase):
    """The registry ops of cmdops that no test ran through commands.run before: control.override, limit.rm and
    rules.sync. They use the split-net fixture copy from test_cmdops."""

    def test_control_override_runs_through_the_registry_and_replies_its_hours(self):
        reply = self.run_op("control.override", {"hours": 2}, source="gui")
        self.assertEqual(reply["data"], {"hours": 2})
        self.assertFalse(reply["undo"])
        self.assertEqual(self.activity()[-1]["op"], "control.override")

    def test_limit_rm_through_the_registry_removes_the_row_and_undo_sets_it_again(self):
        added = self.run_op("limit.set", {"scope": "project", "window": "day", "kind": "tok", "value": 5000})
        row_id = added["data"]["id"]
        removed = self.run_op("limit.rm", {"id": row_id}, source="gui")
        self.assertEqual(removed["data"]["id"], row_id)
        self.assertTrue(removed["undo"])
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("limit.rm", {"id": row_id}, source="gui")
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.run_op("undo", {"activity": removed["activity"]})
        again = self.run_op("limit.rm", {"id": row_id}, source="gui")
        self.assertEqual(again["data"]["id"], row_id)

    def test_rules_sync_dry_run_through_the_registry_returns_counts_and_writes_nothing(self):
        claude_md = os.path.join(os.path.dirname(self.data_dir), "CLAUDE.md")
        existed = os.path.exists(claude_md)
        before = open(claude_md, encoding="utf-8").read() if existed else None
        reply = self.run_op("rules.sync", {"dryRun": True}, source="gui")
        self.assertIsInstance(reply["data"], dict)
        self.assertFalse(reply["undo"])
        self.assertEqual(self.activity()[-1]["op"], "rules.sync")
        after = open(claude_md, encoding="utf-8").read() if os.path.exists(claude_md) else None
        self.assertEqual(after, before)
        self.assertEqual(os.path.exists(claude_md), existed)


if __name__ == "__main__":
    import unittest
    unittest.main()
