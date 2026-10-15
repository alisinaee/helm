"""Work v2 ops (R7.24 W1, roadmap/services/commands.py): task.add quick add to todo, task.move reorder inside one phase,
issue.status public with undo, and the CLI lines (task add, task move, and the issue new next: line on stderr).

Every op logs one activity line and reverses with undo. A move never crosses phases."""

import json
import os

from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import issues, tasks
from tests.unit.test_cmd_support import CmdCase, at


class TaskAddTests(CmdCase):
    def test_no_phase_goes_to_the_first_phase_not_done(self):
        reply = self.op("task.add", {"title": "Write the spec"}, now=at(0))
        self.assertEqual((reply["data"]["id"], reply["data"]["phase"], reply["data"]["status"]),
                         ("P1.4", "P1", "todo"))
        self.assertEqual(tasks.get(self.data, "P1.4")["status"], "todo")
        self.assertTrue(reply["undo"])
        self.assertEqual(self.read_lines("activity.jsonl")[-1]["op"], "task.add")

    def test_first_phase_skips_a_done_phase(self):
        doc = self.read_json("tasks.json")
        for p in doc["phases"]:
            if p.get("id") == "P1":
                p["status"] = "done"
        with open(os.path.join(self.data, "tasks.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        self.assertEqual(self.op("task.add", {"title": "Next"}, now=at(0))["data"]["id"], "P2.2")

    def test_explicit_phase_is_used(self):
        reply = self.op("task.add", {"title": "Surface work", "phase": "P2"}, now=at(0))
        self.assertEqual(reply["data"]["id"], "P2.2")

    def test_undo_removes_the_task_and_keeps_the_phase(self):
        reply = self.op("task.add", {"title": "Gone"}, now=at(0))
        self.op("undo", {"activity": reply["activity"]}, now=at(1))
        self.assertNotIn("P1.4", [t["id"] for t in tasks.load(self.data)["tasks"]])
        self.assertIn("P1", [p["id"] for p in tasks.load(self.data)["phases"]])

    def test_unknown_phase_and_empty_title_are_usage_errors(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.add", {"title": "x", "phase": "ZZ"})
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.add", {"title": "   "})
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        self.assertEqual(len(tasks.load(self.data)["tasks"]), 4)


class TaskMoveTests(CmdCase):
    def order(self, phase):
        return [t["id"] for t in tasks.load(self.data)["tasks"] if t["id"].startswith(phase + ".")]

    def test_move_before_and_after_inside_a_phase(self):
        reply = self.op("task.move", {"id": "P1.3", "before": "P1.1"}, now=at(0))
        self.assertEqual((reply["data"]["moved"], reply["data"]["where"]), (True, "before"))
        self.assertEqual(self.order("P1"), ["P1.3", "P1.1", "P1.2"])
        self.op("task.move", {"id": "P1.3", "after": "P1.2"}, now=at(1))
        self.assertEqual(self.order("P1"), ["P1.1", "P1.2", "P1.3"])

    def test_undo_restores_the_order(self):
        moved = self.op("task.move", {"id": "P1.1", "after": "P1.3"}, now=at(0))
        self.op("undo", {"activity": moved["activity"]}, now=at(1))
        self.assertEqual(self.order("P1"), ["P1.1", "P1.2", "P1.3"])

    def test_a_move_across_phases_is_refused_and_writes_nothing(self):
        before = self.read_json("tasks.json")
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.move", {"id": "P1.1", "before": "P2.1"}, now=at(0))
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        self.assertEqual(self.read_json("tasks.json"), before)

    def test_move_into_place_writes_nothing(self):
        reply = self.op("task.move", {"id": "P1.1", "before": "P1.2"}, now=at(0))
        self.assertFalse(reply["data"]["moved"])
        self.assertFalse(reply["undo"])

    def test_unknown_task_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.move", {"id": "P1.9", "before": "P1.1"})
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)


class IssueStatusTests(CmdCase):
    def test_issue_status_is_public_and_undoes(self):
        issue = self.op("issue.new", {"title": "Slow sync", "kind": "risk"}, now=at(0))
        iid = issue["data"]["id"]
        moved = self.op("issue.status", {"id": iid, "status": "doing"}, now=at(1))
        self.assertEqual(issues.get(self.data, iid)["status"], "doing")
        self.assertEqual((moved["data"]["changed"], moved["data"]["was"]), (True, "open"))
        self.assertTrue(moved["undo"])
        self.op("undo", {"activity": moved["activity"]}, now=at(2))
        self.assertEqual(issues.get(self.data, iid)["status"], "open")

    def test_same_status_changes_nothing_and_has_no_undo(self):
        iid = self.op("issue.new", {"title": "Same", "kind": "bug"}, now=at(0))["data"]["id"]
        reply = self.op("issue.status", {"id": iid, "status": "open"}, now=at(1))
        self.assertFalse(reply["data"]["changed"])
        self.assertFalse(reply["undo"])

    def test_bad_status_is_refused(self):
        iid = self.op("issue.new", {"title": "Bad", "kind": "bug"}, now=at(0))["data"]["id"]
        with self.assertRaises(RoadmapError) as ctx:
            self.op("issue.status", {"id": iid, "status": "chaos"})
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)


class WorkCliTests(CmdCase):
    def test_task_add_prints_the_id_and_next(self):
        code, out, err = self.cli(["task", "add", "Write the spec", "--phase", "P2"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok P2.2 todo in P2. next: roadmap task start P2.2")

    def test_task_move_prints_the_placement(self):
        code, out, err = self.cli(["task", "move", "P1.3", "--before", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "ok P1.3 before P1.1 in P1"), err)
        code, out, _ = self.cli(["task", "move", "P1.3", "--before", "P1.1"])
        self.assertEqual(out.strip(), "ok P1.3 already in place in P1")

    def test_task_move_needs_exactly_one_side(self):
        code, _, err = self.cli(["task", "move", "P1.3"])
        self.assertEqual(code, 2)
        self.assertIn("next:", err)

    def test_issue_new_prints_the_link_next_line_on_stderr(self):
        code, out, err = self.cli(["issue", "new", "Login fails", "--kind", "bug"])
        self.assertEqual((code, out.strip()), (0, "I1 open"))
        self.assertIn("next: roadmap issue link I1 <task>", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
