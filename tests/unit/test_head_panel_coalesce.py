"""R11.131: repeated stop changes of one Limits stop made within 5 s update one panel line (last value wins).
Temp ROADMAP_HOME only."""

import datetime
import os

from roadmap.services import headpanel
from tests.unit.test_control_support import ControlCase

MOMENT = datetime.datetime(2026, 10, 18, 9, 0, tzinfo=datetime.timezone.utc)


def at(seconds):
    return MOMENT + datetime.timedelta(seconds=seconds)


class StopCoalesceTests(ControlCase):
    def setUp(self):
        super().setUp()
        self.ledger = os.path.join(self.docs, headpanel.FILE)

    def stop(self, sum_text, seconds, window="five_hour", src="gui"):
        return headpanel.record(self.docs, "limits.set", sum_text, src=src, key=window, now=at(seconds))

    def test_drag_within_five_seconds_updates_one_line_last_value_wins(self):
        first = self.stop("five_hour stop at 60%", 0)
        self.assertEqual(first["id"], "P1")
        second = self.stop("five_hour stop at 65%", 2)
        third = self.stop("five_hour stop at 72%", 4)
        self.assertEqual(second["id"], "P1")
        self.assertEqual(third["id"], "P1")
        lines = headpanel.read(self.docs)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["sum"], "five_hour stop at 72%")

    def test_a_change_after_the_window_adds_a_new_line(self):
        self.stop("five_hour stop at 60%", 0)
        late = self.stop("five_hour stop at 70%", 6)
        self.assertEqual(late["id"], "P2")
        self.assertEqual([o["sum"] for o in headpanel.read(self.docs)],
                         ["five_hour stop at 60%", "five_hour stop at 70%"])

    def test_the_window_runs_from_the_previous_change_not_the_first(self):
        self.stop("v1", 0)
        self.stop("v2", 4)
        chained = self.stop("v3", 8)
        self.assertEqual(chained["id"], "P1")
        self.assertEqual(len(headpanel.read(self.docs)), 1)

    def test_different_stops_do_not_coalesce(self):
        self.stop("five_hour stop at 60%", 0, window="five_hour")
        week = self.stop("week stop at 50%", 1, window="week")
        self.assertEqual(week["id"], "P2")
        self.assertEqual(len(headpanel.read(self.docs)), 2)

    def test_an_unkeyed_line_is_never_replaced(self):
        headpanel.record(self.docs, "limits.set", "plain", src="gui", now=at(0))
        keyed = self.stop("five_hour stop at 60%", 1)
        self.assertEqual(keyed["id"], "P2")
        self.assertEqual(len(headpanel.read(self.docs)), 2)

    def test_an_updated_line_is_delivered_again_with_its_last_value(self):
        self.stop("five_hour stop at 60%", 0)
        headpanel.take(self.docs, "prompt", now=at(1))
        self.assertEqual(headpanel.state(self.docs)["counts"]["seen"], 1)
        self.stop("five_hour stop at 80%", 2)
        taken = headpanel.take(self.docs, "prompt", now=at(3))
        self.assertEqual([o["sum"] for o in taken], ["five_hour stop at 80%"])

    def test_a_busy_or_broken_write_still_fails_open(self):
        self.assertIsNone(self.stop("five_hour stop at 60%", 0, src="agent"))
        self.assertEqual(headpanel.read(self.docs), [])
