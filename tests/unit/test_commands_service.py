"""Command layer (services/commands.py): the registry, the reply shape, the activity line, undo of task.status,
issue.close and the other reversible ops, idempotent subtask ticks, plan.move, and the refusal of internal ops."""

import json
import os

from roadmap.errors import EXIT_CONFLICT, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import commands, issues, tasks
from tests.unit.test_cmd_support import CmdCase, at


class RegistryTests(CmdCase):
    def test_public_ops_are_the_mvp_list(self):
        self.assertEqual(commands.public_ops(), sorted([
            "backlog.add", "budget.set", "comment.add", "control.override", "control.resume", "control.stop",
            "feature.accept", "feature.add", "feature.link", "feature.move", "feature.rm", "feature.set",
            "feature.unlink",
            "git.branch", "git.commit", "git.push", "git.revert", "git.switch",
            "head.accept", "head.bind", "head.convert", "head.forget", "head.log", "head.merge", "head.review",
                "head.set", "head.split", "head.triage", "head.unbind",
            "issue.close", "issue.status",
            "issue.link", "issue.new", "job.remove", "limit.rm", "limit.set", "phase.approve", "plan.move",
                "question.answer",
            "question.ask",
            "rules.accept", "rules.add", "rules.propose", "rules.reject", "rules.rm", "rules.sync",
            "subtask.add", "subtask.toggle", "task.add", "task.backlog", "task.cap", "task.move",
            "task.promote", "task.rename", "task.start", "task.status", "task.stop", "undo", "usage.set",
            "work.accept", "work.add", "work.link", "work.move", "work.reopen", "work.set"]))

    def test_unknown_op_is_a_usage_error_with_next(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.teleport", {})
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        self.assertIn("unknown op", ctx.exception.message)
        self.assertTrue(ctx.exception.next)

    def test_internal_inverse_ops_are_refused_from_callers(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("queue.remove", {"task": "P1.1"})
        self.assertEqual(ctx.exception.code, "usage")

    def test_source_must_be_known(self):
        with self.assertRaises(RoadmapError):
            commands.run("task.status", {"id": "P1.1", "status": "done"}, "web", self.data)
        self.assertEqual(self.read_lines("activity.jsonl"), [])

    def test_bad_args_write_nothing(self):
        before = self.read_json("tasks.json")
        with self.assertRaises(RoadmapError):
            self.op("task.status", {"id": "P1.1", "status": "finished"})
        self.assertEqual(self.read_json("tasks.json"), before)
        self.assertEqual(self.read_lines("activity.jsonl"), [])


class ReplyAndActivityTests(CmdCase):
    def test_reply_has_ok_data_activity_and_undo(self):
        reply = self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["data"]["was"], "todo")
        self.assertEqual(reply["activity"], "A1")
        self.assertTrue(reply["undo"])

    def test_activity_line_is_written_once_per_write(self):
        self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        self.op("task.status", {"id": "P1.2", "status": "partial"}, now=at(1))
        lines = self.read_lines("activity.jsonl")
        self.assertEqual([l["id"] for l in lines], ["A1", "A2"])
        self.assertEqual(lines[0]["op"], "task.status")
        self.assertEqual(lines[0]["src"], "cli")
        self.assertTrue(lines[0]["undo"])
        self.assertLessEqual(len(lines[0]["sum"]), 60)

    def test_a_no_change_write_has_no_undo(self):
        self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        reply = self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(1))
        self.assertFalse(reply["undo"])
        self.assertEqual(reply["data"]["changed"], False)

    def test_unknown_task_is_not_found_with_next(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.status", {"id": "P9.9", "status": "done"})
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertIn("roadmap task list --phase P9", ctx.exception.next)


class UndoTests(CmdCase):
    def test_undo_reverses_task_status(self):
        done = self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "done")
        reply = self.op("undo", {"activity": done["activity"]}, now=at(1))
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "todo")
        self.assertEqual(reply["data"]["undone"], done["activity"])
        self.assertFalse(reply["undo"])

    def test_undo_is_refused_the_second_time(self):
        done = self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        self.op("undo", {"activity": done["activity"]}, now=at(1))
        with self.assertRaises(RoadmapError) as ctx:
            self.op("undo", {"activity": done["activity"]}, now=at(2))
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)

    def test_undo_of_an_unknown_or_irreversible_activity_is_not_found(self):
        self.op("question.ask", {"text": "ok?", "opts": ["yes", "no"]}, now=at(0))
        with self.assertRaises(RoadmapError) as ctx:
            self.op("undo", {"activity": "A1"}, now=at(1))
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        with self.assertRaises(RoadmapError):
            self.op("undo", {"activity": "A99"}, now=at(2))
        with self.assertRaises(RoadmapError):
            self.op("undo", {"activity": "812"}, now=at(3))

    def test_undo_reverses_issue_close(self):
        issue = self.op("issue.new", {"title": "Login fails", "kind": "bug", "sev": 1}, now=at(0))
        closed = self.op("issue.close", {"id": issue["data"]["id"]}, now=at(1))
        self.assertEqual(issues.get(self.data, issue["data"]["id"])["status"], "closed")
        self.op("undo", {"activity": closed["activity"]}, now=at(2))
        self.assertEqual(issues.get(self.data, issue["data"]["id"])["status"], "open")

    def test_undo_of_issue_new_closes_the_issue(self):
        created = self.op("issue.new", {"title": "Slow sync", "kind": "risk"}, now=at(0))
        self.op("undo", {"activity": created["activity"]}, now=at(1))
        self.assertEqual(issues.get(self.data, created["data"]["id"])["status"], "closed")

    def test_undo_reverses_queue_entries_and_stop_requests(self):
        started = self.op("task.start", {"id": "P1.1", "by": "cli"}, now=at(0))
        self.assertEqual(len(commands.queue_line(self.data).split()), 4)
        self.op("undo", {"activity": started["activity"]}, now=at(1))
        self.assertEqual(commands.queue_line(self.data), "queue: empty")
        stopped = self.op("task.stop", {"id": "P1.2"}, now=at(2))
        self.assertIn("stop", commands.queue_line(self.data))
        self.op("undo", {"activity": stopped["activity"]}, now=at(3))
        self.assertEqual(commands.queue_line(self.data), "queue: empty")

    def test_undo_reverses_a_subtask_tick_with_its_status(self):
        self.op("subtask.add", {"id": "P1.1", "title": "write the parser"}, now=at(0))
        ticked = self.op("subtask.toggle", {"addr": "P1.1/1", "done": True}, now=at(1))
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "partial")
        self.assertTrue(tasks.get(self.data, "P1.1")["subs"][0]["d"])
        self.op("undo", {"activity": ticked["activity"]}, now=at(2))
        self.assertFalse(tasks.get(self.data, "P1.1")["subs"][0]["d"])
        self.assertEqual(tasks.get(self.data, "P1.1")["status"], "todo")


class SubtaskTests(CmdCase):
    def test_done_is_idempotent_and_reports_no_change(self):
        self.op("subtask.add", {"id": "P1.2", "title": "one"}, now=at(0))
        first = self.op("subtask.toggle", {"addr": "P1.2/1", "done": True}, now=at(1))
        self.assertTrue(first["data"]["changed"])
        again = self.op("subtask.toggle", {"addr": "P1.2/1", "done": True}, now=at(2))
        self.assertFalse(again["data"]["changed"])
        self.assertTrue(tasks.get(self.data, "P1.2")["subs"][0]["d"])

    def test_toggle_without_a_done_flag_flips(self):
        self.op("subtask.add", {"id": "P1.2", "title": "one"}, now=at(0))
        self.op("subtask.toggle", {"addr": "P1.2/1"}, now=at(1))
        self.assertTrue(tasks.get(self.data, "P1.2")["subs"][0]["d"])
        self.op("subtask.toggle", {"addr": "P1.2/1"}, now=at(2))
        self.assertFalse(tasks.get(self.data, "P1.2")["subs"][0]["d"])

    def test_bad_address_and_missing_subtask_are_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("subtask.toggle", {"addr": "P1.2"})
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        with self.assertRaises(RoadmapError) as ctx:
            self.op("subtask.toggle", {"addr": "P1.2/5", "done": True})
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertTrue(ctx.exception.next)


class PlanMoveTests(CmdCase):
    def order(self, phase):
        return [t["id"] for t in tasks.load(self.data)["tasks"] if t["id"].startswith(phase + ".")]

    def test_move_before_and_after_within_a_phase(self):
        self.op("plan.move", {"id": "P1.3", "before": "P1.1"}, now=at(0))
        self.assertEqual(self.order("P1"), ["P1.3", "P1.1", "P1.2"])
        self.op("plan.move", {"id": "P1.3", "after": "P1.2"}, now=at(1))
        self.assertEqual(self.order("P1"), ["P1.1", "P1.2", "P1.3"])

    def test_undo_restores_the_order(self):
        moved = self.op("plan.move", {"id": "P1.3", "before": "P1.1"}, now=at(0))
        self.op("undo", {"activity": moved["activity"]}, now=at(1))
        self.assertEqual(self.order("P1"), ["P1.1", "P1.2", "P1.3"])

    def test_moving_across_phases_or_next_to_itself_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("plan.move", {"id": "P1.1", "after": "P2.1"})
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        with self.assertRaises(RoadmapError):
            self.op("plan.move", {"id": "P1.1", "after": "P1.1"})

    def test_exactly_one_of_before_or_after(self):
        with self.assertRaises(RoadmapError):
            self.op("plan.move", {"id": "P1.1"})
        with self.assertRaises(RoadmapError):
            self.op("plan.move", {"id": "P1.1", "before": "P1.2", "after": "P1.3"})

    def test_moving_into_place_writes_nothing(self):
        before = self.read_json("tasks.json")
        reply = self.op("plan.move", {"id": "P1.1", "before": "P1.2"}, now=at(0))
        self.assertFalse(reply["data"]["moved"])
        self.assertEqual(self.read_json("tasks.json"), before)


class ActivityFileTests(CmdCase):
    def test_activity_keeps_the_newest_500_lines(self):
        for n in range(505):
            self.op("comment.add", {"on": "P1.1", "text": "note %d" % n}, now=at(n))
        lines = self.read_lines("activity.jsonl")
        self.assertEqual(len(lines), 500)
        self.assertEqual(lines[-1]["id"], "A505")

    def test_undo_log_is_a_plain_json_lines_file_in_the_data_folder(self):
        self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        path = os.path.join(self.data, commands.UNDO_FILE)
        with open(path, encoding="utf-8") as fh:
            row = json.loads(fh.readline())
        self.assertEqual(row["activity"], "A1")
        self.assertEqual(row["op"], "task.status")


class StartApprovalTests(CmdCase):
    """WP62b on the GUI path: task.status to partial (a start) is refused in a phase with approved false."""

    def set_approved(self, phase, value):
        doc = self.read_json("tasks.json")
        for p in doc["phases"]:
            if p.get("id") == phase:
                p["approved"] = value
        with open(os.path.join(self.data, "tasks.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def test_start_in_unapproved_phase_is_refused_and_writes_nothing(self):
        self.set_approved("P1", False)
        before = self.read_json("tasks.json")
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.status", {"id": "P1.1", "status": "partial"}, now=at(0))
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertIn("not approved", ctx.exception.message)
        self.assertIn("phase approve P1", ctx.exception.next)
        self.assertEqual(self.read_json("tasks.json"), before)
        self.assertEqual(self.read_lines("activity.jsonl"), [])

    def test_done_in_unapproved_phase_is_not_blocked(self):
        self.set_approved("P1", False)
        reply = self.op("task.status", {"id": "P1.1", "status": "done"}, now=at(0))
        self.assertTrue(reply["ok"])

    def test_start_in_approved_or_other_phase_works(self):
        self.set_approved("P1", False)
        self.set_approved("P2", True)
        self.assertTrue(self.op("task.status", {"id": "P2.1", "status": "partial"}, now=at(0))["ok"])
        self.set_approved("P1", True)
        self.assertTrue(self.op("task.status", {"id": "P1.1", "status": "partial"}, now=at(1))["ok"])
