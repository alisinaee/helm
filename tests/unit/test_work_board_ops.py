"""Work board ops (R7.24, R7.25): work.add with issue fields, work.set state (person only), work.move rank + undo."""

from roadmap.errors import RoadmapError
from roadmap.services import work
from tests.unit.test_work_ops import WorkOpsCase, person


class BoardOpsTests(WorkOpsCase):
    def status(self, wid):
        return work.get_view(self.data, wid)["status"]

    def test_issue_fields_are_stored_and_checked(self):
        self.add("Login fails", kind="issue", issue="bug", sev="2")
        item = self.doc()["items"][0]
        self.assertEqual((item["issue"], item["sev"]), ("bug", 2))
        for bad in ({"issue": "bug"}, {"kind": "issue", "issue": "nope"}, {"kind": "issue", "sev": "9"}):
            with self.assertRaises(RoadmapError):
                self.add("x", **bad)

    def test_state_backlog_wontfix_todo_for_the_person(self):
        self.add("One")
        with person():
            self.run_op("work.set", {"id": "W1", "state": "backlog"}, now=None)
            self.assertEqual(self.status("W1"), "Backlog")
            self.run_op("work.set", {"id": "W1", "state": "wontfix"}, now=None)
            self.assertEqual(self.status("W1"), "Won't do")
            self.run_op("work.set", {"id": "W1", "state": "todo"}, now=None)
            self.assertEqual(self.status("W1"), "Todo")
            with self.assertRaises(RoadmapError):
                self.run_op("work.set", {"id": "W1", "state": "todo"}, now=None)

    def test_state_is_refused_for_an_agent(self):
        self.add("One")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("work.set", {"id": "W1", "state": "backlog"}, source="agent")
        self.assertEqual(ctx.exception.code, "agent_refused")

    def test_move_swaps_inside_status_and_prio_and_undoes(self):
        self.add("A")
        self.add("B", prio="P0")
        self.add("C")
        reply = self.run_op("work.move", {"id": "W3", "dir": "up"})
        self.assertEqual([i["id"] for i in self.doc()["items"]], ["W3", "W2", "W1"])
        self.run_op("undo", {"activity": reply["activity"]})
        self.assertEqual([i["id"] for i in self.doc()["items"]], ["W1", "W2", "W3"])
        with self.assertRaises(RoadmapError):
            self.run_op("work.move", {"id": "W1", "dir": "up"})
