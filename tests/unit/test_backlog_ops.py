"""The backlog ops (R7.22 step 2, roadmap/services/commands.py): task.backlog and task.promote move a task between todo
and backlog (person only), backlog.add adds a backlog task (agents may add), undo reverses each one, and a backlog
task cannot be started, by task.start or by task.status partial. A backlog task leaves only by promote, so an agent
cannot promote it with task.status either."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import commands, queue, tasks
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID


class BacklogCase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-backlog-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]
        self.todo = next(t["id"] for t in tasks.load(self.data_dir)["tasks"] if t.get("status") == "todo")

    def run_op(self, op, args, source="cli"):
        with commands.context(source, PROJECT_ID):
            return commands.run(op, args, source, self.data_dir)

    def expect(self, code, op, args, source="cli"):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op(op, args, source)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def status_of(self, task_id):
        return tasks.get(self.data_dir, task_id)["status"]

    def activity_count(self):
        return len(commands.activity.recent(self.data_dir, 1000))

    def add_backlog(self, title="Idea", source="cli", **extra):
        args = dict(title=title, **extra)
        return self.run_op("backlog.add", args, source)

    def undo(self, reply):
        return self.run_op("undo", {"activity": reply["activity"]})


class BacklogAdd(BacklogCase):
    def test_no_phase_creates_the_bl_phase_and_logs_one_line(self):
        before = self.activity_count()
        reply = self.add_backlog("Try a new idea")
        new_id = reply["data"]["id"]
        self.assertEqual(new_id, "BL.1")
        self.assertEqual(reply["data"]["phase"], "BL")
        self.assertTrue(reply["data"]["phaseCreated"])
        self.assertEqual(self.status_of(new_id), "backlog")
        self.assertIn("BL", [p["id"] for p in tasks.load(self.data_dir)["phases"]])
        self.assertEqual(self.activity_count(), before + 1)
        self.assertTrue(reply["undo"])

    def test_second_add_numbers_on_and_keeps_the_phase(self):
        self.add_backlog("First")
        reply = self.add_backlog("Second")
        self.assertEqual(reply["data"]["id"], "BL.2")
        self.assertFalse(reply["data"]["phaseCreated"])

    def test_explicit_existing_phase_is_used(self):
        reply = self.add_backlog("In P1", phase="P1")
        self.assertTrue(reply["data"]["id"].startswith("P1."))
        self.assertEqual(self.status_of(reply["data"]["id"]), "backlog")
        self.assertNotIn("BL", [p["id"] for p in tasks.load(self.data_dir)["phases"]])

    def test_unknown_phase_is_refused(self):
        self.expect("usage", "backlog.add", {"title": "x", "phase": "ZZ"})

    def test_empty_title_is_refused(self):
        self.expect("usage", "backlog.add", {"title": "   "})

    def test_agent_may_add_to_backlog(self):
        reply = self.add_backlog("From an agent", source="agent")
        self.assertEqual(self.status_of(reply["data"]["id"]), "backlog")

    def test_undo_removes_the_task_and_the_created_phase(self):
        reply = self.add_backlog("Gone soon")
        self.undo(reply)
        ids = [t["id"] for t in tasks.load(self.data_dir)["tasks"]]
        self.assertNotIn("BL.1", ids)
        self.assertNotIn("BL", [p["id"] for p in tasks.load(self.data_dir)["phases"]])

    def test_undo_keeps_an_existing_phase(self):
        self.add_backlog("Keep phase")
        second = self.add_backlog("Undo me")
        self.undo(second)
        self.assertIn("BL", [p["id"] for p in tasks.load(self.data_dir)["phases"]])
        self.assertEqual(self.status_of("BL.1"), "backlog")


class BacklogMoves(BacklogCase):
    def test_person_demotes_todo_to_backlog_and_undo_restores(self):
        reply = self.run_op("task.backlog", {"id": self.todo})
        self.assertEqual(self.status_of(self.todo), "backlog")
        self.assertEqual(reply["data"]["was"], "todo")
        self.assertTrue(reply["undo"])
        self.undo(reply)
        self.assertEqual(self.status_of(self.todo), "todo")

    def test_agent_cannot_demote(self):
        exc = self.expect("agent_refused", "task.backlog", {"id": self.todo}, source="agent")
        self.assertIn("person-only", exc.message)
        self.assertIn('roadmap task note ' + self.todo + ' "propose backlog"', exc.next)
        self.assertEqual(self.status_of(self.todo), "todo")

    def test_only_todo_can_go_to_backlog(self):
        done = next(t["id"] for t in tasks.load(self.data_dir)["tasks"] if t.get("status") == "done")
        self.expect("conflict", "task.backlog", {"id": done})

    def test_demote_twice_changes_nothing(self):
        self.run_op("task.backlog", {"id": self.todo})
        reply = self.run_op("task.backlog", {"id": self.todo})
        self.assertFalse(reply["data"]["changed"])

    def test_person_promotes_backlog_to_todo_and_undo_restores(self):
        self.run_op("task.backlog", {"id": self.todo})
        reply = self.run_op("task.promote", {"id": self.todo})
        self.assertEqual(self.status_of(self.todo), "todo")
        self.assertEqual(reply["data"]["was"], "backlog")
        self.undo(reply)
        self.assertEqual(self.status_of(self.todo), "backlog")

    def test_agent_cannot_promote(self):
        reply = self.add_backlog("Agent idea", source="agent")
        exc = self.expect("agent_refused", "task.promote", {"id": reply["data"]["id"]}, source="agent")
        self.assertIn("promote is person-only", exc.message)
        self.assertIn('roadmap task note ' + reply["data"]["id"] + ' "propose promote"', exc.next)
        self.assertEqual(self.status_of(reply["data"]["id"]), "backlog")

    def test_promote_of_a_task_not_in_backlog_is_a_conflict(self):
        self.expect("conflict", "task.promote", {"id": self.todo})

    def test_agent_cannot_promote_with_task_status(self):
        self.run_op("task.backlog", {"id": self.todo})
        self.expect("agent_refused", "task.status", {"id": self.todo, "status": "todo"}, source="agent")
        self.assertEqual(self.status_of(self.todo), "backlog")

    def test_person_task_status_todo_promotes_and_undo_demotes(self):
        self.run_op("task.backlog", {"id": self.todo})
        reply = self.run_op("task.status", {"id": self.todo, "status": "todo"})
        self.assertEqual(self.status_of(self.todo), "todo")
        self.undo(reply)
        self.assertEqual(self.status_of(self.todo), "backlog")

    def test_backlog_task_cannot_go_to_done_by_status(self):
        self.run_op("task.backlog", {"id": self.todo})
        self.expect("conflict", "task.status", {"id": self.todo, "status": "done"})


class BacklogStart(BacklogCase):
    def setUp(self):
        super().setUp()
        self.run_op("task.backlog", {"id": self.todo})

    def test_task_start_refuses_a_backlog_task(self):
        exc = self.expect("conflict", "task.start", {"id": self.todo})
        self.assertIn("is backlog", exc.message)
        self.assertEqual(exc.next, "ask the person to promote")
        self.assertFalse([e for e in queue.list_queue(self.data_dir) if e.get("task") == self.todo])

    def test_task_status_partial_refuses_a_backlog_task(self):
        self.expect("conflict", "task.status", {"id": self.todo, "status": "partial"})
        self.assertEqual(self.status_of(self.todo), "backlog")

    def test_promoted_task_can_start(self):
        self.run_op("task.promote", {"id": self.todo})
        reply = self.run_op("task.start", {"id": self.todo})
        self.assertTrue(reply["data"]["queued"])


if __name__ == "__main__":
    unittest.main()
