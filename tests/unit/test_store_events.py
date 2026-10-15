"""Tests for roadmap/store/events.py. Temp dirs only; never touches the real docs/ or port 8780."""

import os
import tempfile
import threading
import unittest

from roadmap.store import db
from roadmap.store import events


class EventsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "board.db")
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_append_requires_txn(self):
        with self.assertRaises(RuntimeError):
            events.append(self.conn, "task.set", "task", "P1.1", {})

    def test_rev_strictly_increases_across_kinds(self):
        revs = []
        for kind in ("task.set", "job.start", "head.text", "task.set"):
            with db.txn(self.conn):
                revs.append(events.append(self.conn, kind, "x", "1", {"n": 1}))
        self.assertEqual(revs, [1, 2, 3, 4])
        self.assertEqual(events.current_rev(self.conn), 4)

    def test_current_rev_empty(self):
        self.assertEqual(events.current_rev(self.conn), 0)

    def test_several_events_in_one_txn_roll_back_together(self):
        with self.assertRaises(RuntimeError):
            with db.txn(self.conn):
                events.append(self.conn, "a", "task", "1", {})
                events.append(self.conn, "b", "task", "2", {})
                raise RuntimeError("boom")
        self.assertEqual(events.current_rev(self.conn), 0)
        self.assertEqual(events.since(self.conn, 0), [])
        with db.txn(self.conn):
            self.assertEqual(events.append(self.conn, "c", "task", "3", {}), 1)

    def test_since_pagination_in_order(self):
        with db.txn(self.conn):
            for i in range(7):
                events.append(self.conn, "k%d" % i, "task", str(i), {"i": i})
        page, cursor, seen = None, 0, []
        while True:
            page = events.since(self.conn, cursor, limit=3)
            if not page:
                break
            seen.extend(e["rev"] for e in page)
            cursor = page[-1]["rev"]
        self.assertEqual(seen, [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(events.since(self.conn, 5, limit=10)[0]["payload"], {"i": 5})
        self.assertEqual(events.since(self.conn, 7), [])
        with self.assertRaises(ValueError):
            events.since(self.conn, 0, limit=0)

    def test_event_fields_round_trip(self):
        with db.txn(self.conn):
            events.append(self.conn, "task.set", "task", 42, {"status": "done"})
        row = events.since(self.conn, 0)[0]
        self.assertEqual(row["kind"], "task.set")
        self.assertEqual(row["entity"], "task")
        self.assertEqual(row["entity_id"], "42")
        self.assertEqual(row["payload"], {"status": "done"})
        self.assertTrue(row["ts"].endswith("Z"))

    def test_idempotency_key_returns_first_rev_and_adds_nothing(self):
        with db.txn(self.conn):
            first = events.append(self.conn, "ask.add", "ask", "A1", {}, idem="ask-A1-create")
        with db.txn(self.conn):
            again = events.append(self.conn, "ask.add", "ask", "A1", {}, idem="ask-A1-create")
        self.assertEqual(first, again)
        self.assertEqual(len(events.since(self.conn, 0)), 1)
        with db.txn(self.conn):
            other = events.append(self.conn, "ask.add", "ask", "A2", {}, idem="ask-A2-create")
        self.assertEqual(other, first + 1)

    def test_idempotency_key_rolled_back_is_not_kept(self):
        with self.assertRaises(RuntimeError):
            with db.txn(self.conn):
                events.append(self.conn, "x", "t", "1", {}, idem="k1")
                raise RuntimeError("boom")
        with db.txn(self.conn):
            self.assertEqual(events.append(self.conn, "x", "t", "1", {}, idem="k1"), 1)

    def test_two_connections_never_duplicate_a_rev(self):
        errors = []
        per_thread = 40

        def worker(tag):
            conn = db.connect(self.path)
            try:
                for i in range(per_thread):
                    with db.txn(conn):
                        events.append(conn, "tick", "task", "%s-%d" % (tag, i), {})
            except Exception as exc:  # collected and asserted below
                errors.append(exc)
            finally:
                conn.close()

        threads = [threading.Thread(target=worker, args=(t,)) for t in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        all_events = events.since(self.conn, 0, limit=1000)
        revs = [e["rev"] for e in all_events]
        self.assertEqual(len(revs), 2 * per_thread)
        self.assertEqual(len(set(revs)), len(revs))
        self.assertEqual(revs, sorted(revs))
        self.assertEqual(events.current_rev(self.conn), 2 * per_thread)


if __name__ == "__main__":
    unittest.main()
