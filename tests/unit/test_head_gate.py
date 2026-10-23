"""HEAD H12: the autopilot gate (HEAD-SPEC section 11). The pure head_svc.gate function (open asks oldest first, queued
tasks, idle cursor and agy only beside other work, uncommitted and unpushed counts, the usage stops, the pause flag and
the five-item cap) and the Stop hook branch in hooks._stop_gate (config switch, stop_hook_active, pause sentinels,
one block per window, fail-open). Runs in a temp ROADMAP_HOME; git is stubbed and nothing touches the real home."""

import datetime
import os
import unittest
from unittest import mock

from roadmap.services import hooks
from roadmap.services import head as head_svc
from tests.unit.test_control_support import ControlCase, read_json, write_json

MOMENT = datetime.datetime(2026, 10, 15, 9, 30, tzinfo=datetime.timezone.utc)
NOW = MOMENT + datetime.timedelta(minutes=40)


def row(eid, status="new", kind="task", sum_text="do the thing", ts=None):
    return {"id": eid, "status": status, "kind": kind, "sum": sum_text,
            "ts": ts or MOMENT.strftime("%Y-%m-%dT%H:%M:%SZ")}


class GatePure(unittest.TestCase):
    def test_nothing_waiting_gives_no_items(self):
        self.assertEqual(head_svc.gate([], now=NOW), [])

    def test_paused_and_usage_stops_give_no_items(self):
        rows = [row("H1")]
        self.assertEqual(head_svc.gate(rows, paused=True, now=NOW), [])
        self.assertEqual(head_svc.gate(rows, usage={"fiveHourPercent": 90}, now=NOW), [])
        self.assertEqual(head_svc.gate(rows, usage={"weeklyPercent": 95.0}, now=NOW), [])
        items = head_svc.gate(rows, usage={"weeklyPercent": True}, now=NOW)
        self.assertEqual(items[0], "H1 unanswered 40m: do the thing")

    def test_under_stops_or_missing_reading_still_gates(self):
        rows = [row("H1")]
        self.assertEqual(len(head_svc.gate(rows, usage={"fiveHourPercent": 89, "weeklyPercent": 94}, now=NOW)), 3)
        self.assertEqual(len(head_svc.gate(rows, usage=None, now=NOW)), 3)

    def test_open_asks_oldest_first_and_closed_or_decisions_skipped(self):
        rows = [
            row("H3", status="bound", ts="2026-10-15T09:50:00Z", sum_text="newer"),
            row("H2", status="doing", ts="2026-10-15T09:00:00Z", sum_text="older"),
            row("H4", status="done", ts="2026-10-15T09:00:00Z", sum_text="closed"),
            row("H5", status="new", kind="decision", ts="2026-10-15T09:00:00Z", sum_text="a decision"),
            row("H6", status="needs-you", ts="2026-10-15T09:00:00Z", sum_text="the person's"),
        ]
        items = head_svc.gate(rows, now=NOW)
        self.assertEqual(items[:2], ["H2 doing 1h: older", "H3 bound 20m: newer"])
        self.assertEqual(len(items), 4)  # two idle lines follow the asks

    def test_queue_and_idle_and_work_lines(self):
        rows = [row("H1")]
        items = head_svc.gate(rows, queue=["R7.29"], dirty=3, unpushed=2, now=NOW)
        self.assertEqual(items, ["H1 unanswered 40m: do the thing", "task R7.29 queued, not started",
                                 "3 uncommitted files", "2 unpushed commits", "cursor idle: run the review audit"])

    def test_idle_lines_only_beside_other_work_and_not_when_running(self):
        self.assertEqual(head_svc.gate([], dirty=1, now=NOW), ["1 uncommitted files", "cursor idle: run the review audit",
                                                              "agy idle: run an audit"])
        running = [{"title": "cursor review", "model": "x", "status": "running"}]
        items = head_svc.gate([], dirty=1, running=running, now=NOW)
        self.assertEqual(items, ["1 uncommitted files", "agy idle: run an audit"])
        self.assertEqual(head_svc.gate([], queue=[], dirty=0, unpushed=0, now=NOW), [])

    def test_capped_at_five_items(self):
        rows = [row("H%d" % i) for i in range(1, 9)]
        items = head_svc.gate(rows, queue=["A.1"], dirty=1, now=NOW)
        self.assertEqual(len(items), head_svc.GATE_LIMIT)
        self.assertTrue(items[0].startswith("H1 "))


class GateAgeLimit(unittest.TestCase):
    OLD_TS = "2026-10-13T09:30:00Z"  # two days before NOW

    def test_ask_two_days_old_is_not_listed_but_counted(self):
        rows = [row("H1", ts=self.OLD_TS), row("H2", ts="2026-10-15T09:00:00Z", sum_text="recent")]
        items = head_svc.gate(rows, now=NOW)
        self.assertEqual(items[0], "H2 unanswered 1h: recent")
        self.assertEqual(items[1], "+1 older asks: roadmap head list")
        self.assertFalse(any(item.startswith("H1 ") for item in items))

    def test_ask_one_hour_old_is_listed(self):
        items = head_svc.gate([row("H1", ts="2026-10-15T08:30:00Z")], now=NOW)
        self.assertEqual(items, ["H1 unanswered 1h: do the thing", "cursor idle: run the review audit",
                                 "agy idle: run an audit"])

    def test_no_older_asks_means_no_plus_item(self):
        items = head_svc.gate([row("H1")], now=NOW)
        self.assertFalse(any(item.startswith("+") for item in items))

    def test_only_old_asks_still_count_and_keep_idle_lines(self):
        items = head_svc.gate([row("H1", ts=self.OLD_TS), row("H2", ts=self.OLD_TS)], now=NOW)
        self.assertEqual(items, ["+2 older asks: roadmap head list", "cursor idle: run the review audit",
                                 "agy idle: run an audit"])

    def test_unknown_age_is_kept(self):
        items = head_svc.gate([row("H1", ts="yesterday-ish")], now=NOW)
        self.assertEqual(items[0], "H1 unanswered 0m: do the thing")


class GateHook(ControlCase):
    def setUp(self):
        super().setUp()
        self.stamp = os.path.join(self.docs, "head-gate.json")
        self.project_ref = {"id": "demo", "path": self.project}
        config_path = os.path.join(self.docs, "roadmap.config.json")
        write_json(config_path, dict(read_json(config_path), headCapture=True))
        head_svc.capture(self.docs, "please add a dark mode toggle to the settings page", now=MOMENT)
        self.git = mock.patch.object(hooks, "_git_counts", return_value=(0, 0))
        self.git.start()
        self.addCleanup(self.git.stop)
        self.epoch = NOW.timestamp()

    def gate(self, now=None, payload=None):
        return hooks._stop_gate(payload or {}, self.project_ref, self.docs, self.epoch if now is None else now)

    def set_head_gate(self, value):
        path = os.path.join(self.docs, "roadmap.config.json")
        data = read_json(path)
        data["head"] = {"gate": value}
        write_json(path, data)

    def test_blocks_with_items_then_throttles_for_the_window(self):
        reply = self.gate()
        self.assertEqual(reply["decision"], "block")
        self.assertIn("continue with:", reply["reason"])
        self.assertIn("unanswered", reply["reason"])
        self.assertIsNone(self.gate(now=self.epoch + 300))
        self.assertIsNotNone(self.gate(now=self.epoch + head_svc.GATE_WINDOW_S + 1))

    def test_only_runs_where_head_capture_is_on(self):
        path = os.path.join(self.docs, "roadmap.config.json")
        data = read_json(path)
        data["headCapture"] = False
        write_json(path, data)
        self.assertIsNone(self.gate())

    def test_stop_hook_active_never_blocks_again(self):
        self.assertIsNone(self.gate(payload={"stop_hook_active": True}))
        self.assertFalse(os.path.exists(self.stamp))

    def test_config_switch_pause_file_and_stop_state_silence_the_gate(self):
        self.set_head_gate(False)
        self.assertIsNone(self.gate())
        self.set_head_gate(True)
        pause = os.path.join(self.docs, head_svc.GATE_PAUSE_FILE)
        open(pause, "w").close()
        self.assertIsNone(self.gate())
        os.remove(pause)
        with mock.patch.object(hooks.control, "read_state", return_value={"stop": True}):
            self.assertIsNone(self.gate())
        self.assertIsNotNone(self.gate())

    def test_no_items_no_block_and_no_stamp(self):
        with mock.patch.object(hooks, "_git_counts", return_value=(0, 0)), \
                mock.patch.object(hooks.head_svc, "rows", return_value=[]), \
                mock.patch.object(hooks, "_idle_text", return_value=""):
            self.assertIsNone(self.gate())
        self.assertFalse(os.path.exists(self.stamp))

    def test_fail_open_on_error(self):
        with mock.patch.object(hooks.head_svc, "gate", side_effect=RuntimeError("boom")):
            self.assertIsNone(self.gate())
        self.assertIsNotNone(self.gate())


class GateEdges(unittest.TestCase):
    """Edge cases from docs/reviews/agy-head-testgaps-cli.md that the gate tests did not cover."""

    def test_cursor_and_agy_both_running_add_no_idle_lines(self):
        running = [{"title": "cursor review", "model": "x"}, {"title": "agy audit", "model": "y"}]
        items = head_svc.gate([row("H1")], dirty=1, running=running, now=NOW)
        self.assertEqual(items, ["H1 unanswered 40m: do the thing", "1 uncommitted files"])

    def test_ask_summary_is_cut_to_fifty_characters(self):
        items = head_svc.gate([row("H1", sum_text="x" * 80)], now=NOW)
        self.assertEqual(items[0], "H1 unanswered 40m: " + "x" * 50)

    def test_unparseable_timestamp_counts_as_zero_minutes(self):
        items = head_svc.gate([row("H1", ts="yesterday-ish")], now=NOW)
        self.assertEqual(items[0], "H1 unanswered 0m: do the thing")

    def test_empty_usage_reading_is_not_a_stop(self):
        self.assertEqual(len(head_svc.gate([row("H1")], usage={}, now=NOW)), 3)


if __name__ == "__main__":
    unittest.main()
