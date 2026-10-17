"""Limits v2 (R11.126): effective stop for both modes, budget re-base on reset, lowest stop wins, migration, CLI."""

import json
import os
import tempfile
import unittest
from unittest import mock

from roadmap.services import limits, limits_v2
from roadmap.store import config as config_store

NOW = "2026-10-17T10:00:00+00:00"
NEXT = "2026-10-17T15:00:00+00:00"


class V2Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = mock.patch.dict(os.environ, {"ROADMAP_HOME": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.reading = {"five_hour": (30.0, NOW, True), "week": (20.0, "2026-10-20T00:00:00+00:00", True)}
        patch = mock.patch.object(limits_v2, "_reading", lambda window, moment=None: self.reading[window])
        patch.start()
        self.addCleanup(patch.stop)


class EffectiveStop(V2Base):
    def test_cap_is_the_value_and_off_is_none(self):
        rec = dict(limits_v2.default_window("week"), on=True, mode="cap", value=35)
        self.assertEqual(limits_v2.effective_stop(rec), 35)
        self.assertIsNone(limits_v2.effective_stop(dict(rec, on=False)))

    def test_budget_is_base_plus_value_clamped_to_100(self):
        rec = dict(limits_v2.default_window("week"), on=True, mode="budget", value=20, base=30)
        self.assertEqual(limits_v2.effective_stop(rec), 50)
        self.assertEqual(limits_v2.effective_stop(dict(rec, base=90)), 100)

    def test_budget_takes_the_reading_as_its_base_when_set(self):
        limits_v2.set_window("five_hour", {"on": True, "mode": "budget", "value": 20})
        info = limits_v2.stops(persist=False)["five_hour"]
        self.assertEqual((info["base"], info["stop"]), (30.0, 50.0))
        limits_v2.set_window("five_hour", {"value": 25})  # dragging N keeps the base
        self.assertEqual(limits_v2.stops(persist=False)["five_hour"]["stop"], 55.0)

    def test_budget_rebases_when_the_window_resets(self):
        limits_v2.set_window("five_hour", {"on": True, "mode": "budget", "value": 20})
        self.reading["five_hour"] = (4.0, NEXT, True)
        info = limits_v2.stops()["five_hour"]
        self.assertEqual((info["base"], info["stop"]), (4.0, 24.0))
        self.assertEqual(config_store.load()[limits_v2.KEY]["five_hour"]["base"], 4.0)

    def test_a_once_budget_turns_off_at_the_reset(self):
        limits_v2.set_window("five_hour", {"on": True, "mode": "budget", "value": 20, "once": True})
        self.reading["five_hour"] = (4.0, NEXT, True)
        self.assertIsNone(limits_v2.stops()["five_hour"]["stop"])

    def test_a_small_reset_jitter_is_not_a_reset(self):
        limits_v2.set_window("five_hour", {"on": True, "mode": "budget", "value": 20})
        self.reading["five_hour"] = (35.0, "2026-10-17T10:01:00+00:00", True)
        self.assertEqual(limits_v2.stops()["five_hour"]["base"], 30.0)

    def test_bad_input_is_a_usage_error(self):
        for patch in ({"value": 0}, {"value": 101}, {"mode": "x"}, {"on": "yes"}):
            with self.assertRaises(Exception):
                limits_v2.set_window("week", patch)
        with self.assertRaises(Exception):
            limits_v2.set_window("day", {"on": True})

    def test_the_old_weekly_stop_moves_into_week_cap(self):
        config_store.update_limits(lambda rows: rows.append(
            {"id": "L1", "window": "week", "kind": "pct", "value": 80, "action": "block"}))
        week = limits_v2.load()["week"]
        self.assertEqual((week["on"], week["mode"], week["value"]), (True, "cap", 80))
        limits_v2.set_window("week", {"value": 70})
        self.assertEqual(config_store.load()["limits"], [])
        self.assertEqual(limits_v2.load()["week"]["value"], 70)


class Gate(V2Base):
    def test_the_lowest_active_stop_wins_and_gates_a_job(self):
        limits_v2.set_window("five_hour", {"on": True, "mode": "cap", "value": 25})
        limits_v2.set_window("week", {"on": True, "mode": "cap", "value": 90})
        self.assertEqual(limits_v2.lowest(), ("five_hour", 25.0))
        rows = limits_v2.gate_rows()
        self.assertEqual({r["id"] for r in rows}, {"S5H", "SWK"})
        ctx = mock.Mock(now=None, pct_ok=True, weekly=20.0)
        judged = [limits._judge(r, *limits._measure(r, ctx), ctx) for r in rows]
        states = {r["id"]: r["state"] for r in judged}
        self.assertEqual(states, {"S5H": "block", "SWK": "ok"})
        self.assertIn("5 hours usage reached the stop at 25%", limits.describe(judged[0]))

    def test_brief_line(self):
        limits_v2.set_window("five_hour", {"on": True, "mode": "cap", "value": 50})
        self.assertEqual(limits_v2.brief_line(), "5h 30% / stop 50% | W 20% / stop off")


if __name__ == "__main__":
    unittest.main()
