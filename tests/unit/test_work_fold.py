"""M6 fold (docs/WORK-MODEL.md sections 2, 3, 7): the last agent task done puts the Work item in Review with one Inbox
item; accept closes the asks bound to it; reopen returns it to Doing; the queue orders by the Work item prio."""

from roadmap.services import commands, head as head_svc, supervisor, work
from roadmap.store import db
from tests.unit import test_supervisor as ts
from tests.unit.test_work_ops import WorkOpsCase, at, person


class FoldCase(WorkOpsCase):
    def setUp(self):
        super().setUp()
        self.add("Ship the board")
        for tid in ("P1.1", "P1.2"):
            self.run_op("work.link", {"task": tid, "work": "W1"})

    def status(self):
        return work.get_view(self.data, "W1")["status"]

    def ask(self, refs, text="add a map view"):
        eid = self.run_op("head.log", {"text": text})["data"]["id"]
        self.run_op("head.bind", {"id": eid, "refs": refs})
        return eid

    def row(self, eid):
        return next(r for r in head_svc.rows(self.data) if r["id"] == eid)

    def states(self):
        s, _ = work.head_states(self.data)
        return {k: v for k, v in s.items() if not k.startswith("_")}

    def row_now(self, eid):
        return next(r for r in head_svc.rows(self.data, link_state=self.states()) if r["id"] == eid)

    def inbox(self):
        return [line for line in commands.inbox_lines(self.data) if "work accept" in line]


class ReviewTests(FoldCase):
    def test_partial_is_doing_with_no_inbox_item(self):
        self.set_task_status("P1.1", "done")
        self.assertEqual(self.status(), "Doing")
        self.assertEqual(work.review_items(self.data), [])
        self.assertEqual(self.inbox(), [])

    def test_all_done_is_review_with_one_inbox_item_and_accept_clears_it(self):
        self.set_task_status("P1.1", "done")
        self.set_task_status("P1.2", "done")
        self.assertEqual(self.status(), "Review")
        for _ in range(2):  # repeated reads never duplicate
            items = work.review_items(self.data)
            self.assertEqual([i["title"] for i in items], ["Review W1 Ship the board"])
            self.assertEqual(items[0]["action"], {"op": "work.accept", "args": {"id": "W1"}})
        self.assertEqual(len(self.inbox()), 1)
        with person():
            self.run_op("work.accept", {"id": "W1"}, now=at(5))
        self.assertEqual(self.status(), "Done")
        self.assertEqual(work.review_items(self.data), [])

    def test_reopen_returns_to_doing_and_clears_the_item(self):
        self.set_task_status("P1.1", "done")
        self.set_task_status("P1.2", "done")
        with person():
            self.run_op("work.reopen", {"id": "W1"}, now=at(5))
        self.assertEqual(self.status(), "Doing")
        self.assertEqual(work.review_items(self.data), [])


class AskTests(FoldCase):
    def test_asks_review_then_close_on_accept_not_on_task_done(self):
        by_work = self.ask(["work:W1"])
        by_task = self.ask(["task:P1.1"], "fix the sidebar")
        self.set_task_status("P1.1", "done")
        self.assertEqual(head_svc.fold_asks(self.data), [])  # one task done closes nothing
        self.set_task_status("P1.2", "done")
        self.assertEqual(head_svc.fold_asks(self.data), [])
        for eid in (by_work, by_task):
            self.assertEqual(self.row_now(eid)["status"], "review")
        with person():
            self.run_op("work.accept", {"id": "W1"}, now=at(5))
        self.assertEqual(sorted(head_svc.fold_asks(self.data)), sorted([by_work, by_task]))
        for eid in (by_work, by_task):
            row = self.row(eid)
            self.assertEqual(row["status"], "done")
        notes = [r.get("note") for r in head_svc._records(self.data) if r.get("t") == "u" and r.get("note")]
        self.assertIn("W1 accepted", notes)

    def test_wont_do_closes_the_asks_too(self):
        eid = self.ask(["work:W1"])
        doc = self.doc()
        doc["items"][0]["status"] = "Won't do"
        work._save(self.data, doc)
        self.assertEqual(head_svc.fold_asks(self.data), [eid])


class QueueTests(ts.SupervisorCase):
    def test_ready_tasks_are_ordered_by_their_work_item_prio(self):
        self.add_job("a", "queued", "T.a", ["a.py"], prio="P0", queued_at=1.0)
        self.add_job("b", "queued", "T.b", ["b.py"], prio="P2", queued_at=2.0)
        self.add_job("c", "queued", "T.c", ["c.py"], prio="P2", queued_at=3.0)
        with db.txn(self.conn):  # T.c belongs to a P0 item, T.a to a P3 item
            ids = [j["id"] for j in supervisor.next_launches(self.conn, 3, now=10,
                                                            work_prio={"T.c": "P0", "T.a": "P3"})]
        self.assertEqual(ids, ["c", "b", "a"])


class PrioTests(FoldCase):
    def test_task_prios_and_needs_you_badge(self):
        self.run_op("work.set", {"id": "W1", "prio": "P0"})
        self.assertEqual(work.task_prios(self.data), {"P1.1": "P0", "P1.2": "P0"})
        self.set_task_status("P1.2", "needs-you")
        self.assertIn("needs-you", work.get_view(self.data, "W1")["badges"])
