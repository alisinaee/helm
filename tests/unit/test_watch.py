"""roadmap watch (commands/watch.py): start, stop and answer lines for news that appears after the command starts, the
timeout with a fake clock, the --max bounds, and the --json envelope. The clock and the sleep are fakes, so the wait
logic runs without real delays; the CLI tests use --max 1 and a real clock."""

import json
import os
import time

from roadmap.commands import watch
from roadmap.errors import RoadmapError
from roadmap.services import presence, questions, queue, records
from roadmap.store import atomic, config
from tests.unit.test_jobs_support import run_cli
from tests.unit.test_store_support import HomeCase

WALL_BASE = 1e9


class FakeTime:
    """A clock that only moves when sleep is called."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class WatchTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        self.fake = FakeTime()
        self.bumps = 0

    def bump(self, name):
        """Give a file a new mtime, so the poll sees a change even on a coarse file system."""
        self.bumps += 1
        stamp = 1e9 + 100 + self.bumps
        os.utime(os.path.join(self.data, name), (stamp, stamp))

    def run_watch(self, max_s=10, during=None):
        """Run wait with the fake clock. during(poll_number) runs before each sleep: it makes the news."""
        def sleep(seconds):
            if during is not None:
                during(len(self.fake.sleeps))
            self.fake.sleep(seconds)

        return watch.wait(self.data, max_s, sleep=sleep, clock=self.fake.clock)

    def test_timeout_after_max_seconds_with_a_fake_clock(self):
        event = self.run_watch(max_s=5)
        self.assertEqual(event, {"event": "timeout", "line": "timeout"})
        self.assertEqual(self.fake.sleeps, [2, 2, 1])
        self.assertEqual(self.fake.now, 5)

    def test_a_queued_start_is_reported_and_older_entries_are_not(self):
        queue.enqueue(self.data, "P1.0", by="lead", now=None)

        def add(poll):
            if poll == 0:
                queue.enqueue(self.data, "P1.1", by="gui", now=None)
                self.bump(queue.FILE)

        event = self.run_watch(max_s=10, during=add)
        self.assertEqual(event["line"], "start P1.1")
        self.assertEqual(self.fake.now, 2)

    def test_a_queued_stop_request_is_reported_as_stop(self):
        def add(poll):
            if poll == 0:
                doc = {"schemaVersion": 1, "entries": [{"task": "P1.2", "by": "gui",
                                                       "at": "2026-10-14T10:00:00+00:00", "op": "stop"}]}
                records.save("queue", self.data, queue.FILE, doc)
                self.bump(queue.FILE)

        self.assertEqual(self.run_watch(max_s=10, during=add)["line"], "stop P1.2")

    def test_an_answer_is_reported_and_an_old_answer_is_not(self):
        questions.ask(self.data, "P1.0", "ship?", opts=["yes", "no"], default="no", now=None)
        questions.answer(self.data, "Q1", "no")
        questions.ask(self.data, "P1.0", "deploy?", opts=["yes", "no"], default="no", now=None)

        def answer(poll):
            if poll == 0:
                questions.answer(self.data, "Q2", "yes")
                self.bump(questions.FILE)

        event = self.run_watch(max_s=10, during=answer)
        self.assertEqual(event, {"event": "answer", "line": "answer Q2 yes"})

    def test_missing_data_folder_is_an_error_with_a_next_line_not_a_wait(self):
        with self.assertRaises(RoadmapError) as caught:
            watch.wait(os.path.join(self.tmp, "nope"), 5, sleep=self.fake.sleep, clock=self.fake.clock)
        self.assertEqual(caught.exception.code, "not_found")
        self.assertEqual(self.fake.sleeps, [])

    def test_max_outside_the_allowed_range_is_a_usage_error(self):
        code, _, err = run_cli(["watch", "--project", "demo", "--max", "0"])
        self.assertEqual(code, 2)
        self.assertIn("next: roadmap watch --max 1800", err)


class WatchCliTests(HomeCase):
    """The command in a temp home with one registered project. --max 1 keeps the real wait short."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("demo")
        config.add_project("Demo", self.project)
        os.makedirs(os.path.join(self.project, "docs"))

    def test_timeout_prints_one_line_and_exits_zero(self):
        start = time.monotonic()
        code, out, err = run_cli(["watch", "--project", "demo", "--max", "1"])
        self.assertEqual((code, out), (0, "timeout\n"))
        self.assertLess(time.monotonic() - start, 10)

    def test_json_envelope_carries_the_event(self):
        code, out, _ = run_cli(["watch", "--project", "demo", "--max", "1", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"ok": True, "data": {"event": "timeout", "line": "timeout"}})


class WatchPresenceTests(HomeCase):
    """wait() stamps presence while it polls, refreshes the stamp every 30 s, and clears it on every exit."""

    def setUp(self):
        super().setUp()
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        self.fake = FakeTime()

    def wall(self):
        return WALL_BASE + self.fake.now

    def doc(self):
        return atomic.read_json(presence.file_for(self.data), default={})

    def run_watch(self, max_s, during=None):
        def sleep(seconds):
            if during is not None:
                during(len(self.fake.sleeps))
            self.fake.sleep(seconds)

        return watch.wait(self.data, max_s, sleep=sleep, clock=self.fake.clock, wall=self.wall)

    def test_watching_is_visible_while_polling_and_cleared_after_a_timeout(self):
        seen = []

        def look(poll):
            seen.append((presence.state(self.data, now=self.wall()), self.doc().get("watchPid")))

        self.assertEqual(self.run_watch(max_s=4, during=look)["event"], "timeout")
        self.assertEqual(seen[0], ("watching", os.getpid()))
        self.assertEqual(presence.state(self.data, now=self.wall()), "none")
        self.assertEqual(self.doc().get("watch"), None)
        self.assertIsNone(self.doc().get("watchPid"))

    def test_the_watch_stamp_is_refreshed_every_30_seconds(self):
        stamps = []

        def look(poll):
            stamps.append((self.fake.now, self.doc().get("watch")))

        self.run_watch(max_s=70, during=look)
        # the first stamp is written at the start; a refresh happens once 30 s have passed, then again at 60 s
        starts = [(now, stamp) for now, stamp in stamps if stamp is not None]
        self.assertEqual(starts[0][1], WALL_BASE + 0)
        self.assertEqual(starts[-1][1], WALL_BASE + 60)
        self.assertIn(WALL_BASE + 30, [stamp for _, stamp in stamps])

    def test_an_event_clears_the_watch_stamp_too(self):
        def add(poll):
            if poll == 0:
                queue.enqueue(self.data, "P1.1", by="gui", now=None)
                os.utime(os.path.join(self.data, queue.FILE), (2e9, 2e9))

        self.assertEqual(self.run_watch(max_s=10, during=add)["line"], "start P1.1")
        self.assertIsNone(self.doc().get("watch"))
        self.assertIsNone(self.doc().get("watchPid"))

    def test_ctrl_c_during_the_wait_still_clears_the_watch_stamp(self):
        def interrupt(poll):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.run_watch(max_s=10, during=interrupt)
        self.assertIsNone(self.doc().get("watch"))
        self.assertIsNone(self.doc().get("watchPid"))

    def test_a_missing_data_folder_writes_no_presence(self):
        with self.assertRaises(RoadmapError):
            watch.wait(os.path.join(self.tmp, "nope"), 5, sleep=self.fake.sleep, clock=self.fake.clock, wall=self.wall)
        self.assertFalse(os.path.exists(presence.file_for(os.path.join(self.tmp, "nope"))))
