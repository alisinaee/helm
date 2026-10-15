"""Work item ops (roadmap/services/work.py, registered in services/cmdops.py): add, set, link, accept, reopen. Each op
writes an activity line and an event, undo reverses it, accept and reopen are the person's only, and the roll-up
moves Todo -> Doing -> Review, with accept -> Done. Temp ROADMAP_HOME only."""

import contextlib
import json
import os
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import agentguard, commands, work
from tests.unit.test_cmd_support import CmdCase, at


def _tty():
    stream = mock.Mock()
    stream.isatty.return_value = True
    return stream


@contextlib.contextmanager
def person():
    """The person's own terminal: an interactive shell with no agent marker."""
    with mock.patch("sys.stdin", _tty()), mock.patch("sys.stdout", _tty()), \
            mock.patch.object(agentguard, "agent_marked", return_value=False):
        yield


class WorkOpsCase(CmdCase):
    def setUp(self):
        super().setUp()
        self.work_path = os.path.join(self.data, work.FILE)

    def run_op(self, name, args, source="cli", now=None):
        return commands.run(name, args, source, self.data, now=now)

    def doc(self):
        with open(self.work_path, encoding="utf-8") as fh:
            return json.load(fh)

    def set_task_status(self, tid, status):
        doc = self.read_json("tasks.json")
        for task in doc["tasks"]:
            if task.get("id") == tid:
                task["status"] = status
        with open(os.path.join(self.data, "tasks.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def add(self, title="Ship the board", **extra):
        args = {"title": title}
        args.update(extra)
        return self.run_op("work.add", args, now=at(0))

    def activity_ops(self):
        return [line["op"] for line in self.read_lines("activity.jsonl")]


class AddTests(WorkOpsCase):
    def test_add_returns_a_todo_item_with_the_next_id(self):
        reply = self.add(prio="P1", outcome="The board shows every item", phase="R7")
        self.assertEqual(reply["data"]["id"], "W1")
        self.assertEqual((reply["data"]["status"], reply["data"]["prio"], reply["data"]["kind"]),
                         ("Todo", "P1", "task"))
        self.assertEqual(reply["data"]["tasks"], [])
        self.assertTrue(reply["undo"])
        self.assertEqual(self.add("Second thing")["data"]["id"], "W2")
        self.assertEqual(self.activity_ops(), ["work.add", "work.add"])

    def test_wording_and_field_checks_refuse_before_any_write(self):
        bad = [{"title": "Edit roadmap/services/work.py"}, {"title": "Use haiku for the edit"},
               {"title": "Wave 2 fixes"}, {"title": "x" * 61}, {"title": ""}, {"title": "Fine", "prio": "P9"},
               {"title": "Fine", "kind": "bug"}, {"title": "Fine", "outcome": "o" * 241}]
        for args in bad:
            with self.assertRaises(RoadmapError) as ctx:
                self.run_op("work.add", args)
            self.assertEqual(ctx.exception.code, "usage", args)
        self.assertFalse(os.path.exists(self.work_path))

    def test_issue_kind_and_prio_as_a_number(self):
        reply = self.add("Login breaks", kind="issue", prio=0)
        self.assertEqual((reply["data"]["kind"], reply["data"]["prio"]), ("issue", "P0"))


class SetLinkTests(WorkOpsCase):
    def test_set_changes_words_and_prio_and_refuses_status(self):
        self.add()
        reply = self.run_op("work.set", {"id": "W1", "title": "Ship the work board", "prio": "P3"})
        self.assertEqual((reply["data"]["title"], reply["data"]["prio"]), ("Ship the work board", "P3"))
        self.assertEqual(self.activity_ops()[-1], "work.set")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("work.set", {"id": "W1", "status": "Done"})
        self.assertEqual(ctx.exception.code, "usage")
        with self.assertRaises(RoadmapError):
            self.run_op("work.set", {"id": "W1"})

    def test_link_binds_an_agent_task_and_refuses_unknown_ids(self):
        self.add()
        reply = self.run_op("work.link", {"task": "P1.1", "work": "W1"})
        self.assertEqual(reply["data"]["tasks"], ["P1.1"])
        self.assertEqual(self.doc()["links"], {"P1.1": "W1"})
        with self.assertRaises(RoadmapError) as missing_task:
            self.run_op("work.link", {"task": "P9.9", "work": "W1"})
        self.assertEqual(missing_task.exception.code, "not_found")
        with self.assertRaises(RoadmapError) as missing_work:
            self.run_op("work.link", {"task": "P1.2", "work": "W7"})
        self.assertEqual(missing_work.exception.code, "not_found")


class PersonOnlyTests(WorkOpsCase):
    def test_accept_and_reopen_are_refused_for_an_agent_the_phone_and_a_script(self):
        self.add()
        for source in ("phone", "agent", "cli"):
            for op in ("work.accept", "work.reopen"):
                with self.assertRaises(RoadmapError) as ctx:
                    self.run_op(op, {"id": "W1"}, source=source)
                self.assertEqual(ctx.exception.code, "agent_refused", (op, source))
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Todo")
        self.assertEqual(self.doc()["items"][0]["accepted"], None)

    def test_the_persons_terminal_accepts_and_reopens(self):
        self.add()
        self.run_op("work.link", {"task": "P1.1", "work": "W1"})
        self.set_task_status("P1.1", "done")
        with person():
            self.assertEqual(self.run_op("work.accept", {"id": "W1"}, now=at(5))["data"]["status"], "Done")
            self.assertEqual(self.run_op("work.reopen", {"id": "W1"}, now=at(6))["data"]["status"], "Doing")


class UndoTests(WorkOpsCase):
    def test_undo_reverses_add_set_link_accept_and_reopen(self):
        added = self.add()
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Todo")
        self.run_op("undo", {"activity": added["activity"]})
        self.assertEqual(work.list_views(self.data), [])

        self.add()
        set_line = self.run_op("work.set", {"id": "W1", "title": "Renamed item"})["activity"]
        self.run_op("undo", {"activity": set_line})
        self.assertEqual(work.get_view(self.data, "W1")["title"], "Ship the board")

        link_line = self.run_op("work.link", {"task": "P1.1", "work": "W1"})["activity"]
        self.run_op("undo", {"activity": link_line})
        self.assertEqual(self.doc()["links"], {})

        self.run_op("work.link", {"task": "P1.1", "work": "W1"})
        self.set_task_status("P1.1", "done")
        with person():
            accept_line = self.run_op("work.accept", {"id": "W1"}, now=at(7))["activity"]
            self.assertEqual(work.get_view(self.data, "W1")["status"], "Done")
            self.run_op("undo", {"activity": accept_line})
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Review")

    def test_undo_of_a_reopen_puts_the_done_item_back(self):
        self.add()
        self.run_op("work.link", {"task": "P1.1", "work": "W1"})
        self.set_task_status("P1.1", "done")
        with person():
            self.run_op("work.accept", {"id": "W1"}, now=at(1))
            reopen_line = self.run_op("work.reopen", {"id": "W1"}, now=at(2))["activity"]
            self.assertEqual(work.get_view(self.data, "W1")["status"], "Doing")
            self.run_op("undo", {"activity": reopen_line})
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Done")


class EventTests(WorkOpsCase):
    def test_every_write_appends_an_event(self):
        self.add()
        self.run_op("work.set", {"id": "W1", "outcome": "Plain words"})
        self.run_op("work.link", {"task": "P1.1", "work": "W1"})
        self.set_task_status("P1.1", "done")
        with person():
            self.run_op("work.accept", {"id": "W1"})
        kinds = [event["kind"] for event in self.doc()["events"]]
        self.assertEqual(kinds, ["work.add", "work.set", "work.link", "work.accept"])
        self.assertEqual(self.doc()["events"][-1]["entity_id"], "W1")


class RollupTests(WorkOpsCase):
    def test_rollup_goes_todo_doing_review_then_accept_makes_done(self):
        self.add()
        self.run_op("work.link", {"task": "P1.1", "work": "W1"})
        self.run_op("work.link", {"task": "P1.2", "work": "W1"})
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Todo")
        self.set_task_status("P1.1", "running")
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Doing")
        self.set_task_status("P1.1", "done")
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Doing")
        self.set_task_status("P1.2", "done")
        view = work.get_view(self.data, "W1")
        self.assertEqual((view["status"], view["progress"]), ("Review", {"done": 2, "total": 2}))
        self.assertEqual(self.doc()["items"][0]["status"], "Todo")
        with person():
            self.assertEqual(self.run_op("work.accept", {"id": "W1"})["data"]["status"], "Done")
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Done")

    def test_reject_holds_doing_until_new_work_is_done(self):
        self.add()
        self.run_op("work.link", {"task": "P1.1", "work": "W1"})
        self.set_task_status("P1.1", "done")
        with person():
            self.assertEqual(work.get_view(self.data, "W1")["status"], "Review")
            self.run_op("work.reopen", {"id": "W1"})
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Doing")
        self.run_op("work.link", {"task": "P1.2", "work": "W1"})
        self.set_task_status("P1.2", "done")
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Review")

    def test_a_cancelled_or_missing_task_does_not_hold_the_item_open(self):
        self.add()
        self.run_op("work.link", {"task": "P1.1", "work": "W1"})
        self.run_op("work.link", {"task": "P1.2", "work": "W1"})
        self.set_task_status("P1.1", "done")
        self.set_task_status("P1.2", "cancelled")
        self.assertEqual(work.get_view(self.data, "W1")["status"], "Review")
