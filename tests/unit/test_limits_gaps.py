"""WP27 gap tests: the ledger and limit branches that test_wp27_limits.py does not reach (see changes/agy-verify.md).

Same rules as test_wp27_limits.py: temp ROADMAP_HOME and temp project (HomeCase / ControlCase), injected times built
by at(), never the real clock. Two tests are expectedFailure because they show a real bug in services/limits.py;
the bug is recorded in changes/agy-verify.md and the service code is not changed here.
"""

import datetime
import json
import os
import unittest

from roadmap.errors import RoadmapError
from roadmap.services import budget, control, ledger, limits
from roadmap.store import config
from tests.unit.test_control_support import ControlCase, write_json
from tests.unit.test_store_support import HomeCase


def at(hour, minute=0, day=13):
    """A local aware time on 2026-10-<day>."""
    return datetime.datetime(2026, 10, day, hour, minute).astimezone()


class LedgerGapTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.file = ledger.path()

    def test_a_non_numeric_reading_returns_none_and_writes_nothing(self):
        for value in ("40", None, True, float("nan")):
            with self.subTest(value=value):
                self.assertIsNone(ledger.record_reading(value, now=at(9)))
        self.assertFalse(os.path.exists(self.file))

    def test_the_first_reading_ever_adds_nothing(self):
        self.assertEqual(ledger.record_reading(40, now=at(9)), 0.0)

    def test_a_weekly_reset_adds_the_new_reading_itself(self):
        ledger.record_reading(43, now=at(9))
        self.assertEqual(ledger.record_reading(1, now=at(10)), 1.0)

    def test_a_spend_for_no_project_or_no_tokens_is_refused_and_writes_nothing(self):
        self.assertIsNone(ledger.record_spend("", 10, now=at(9)))
        self.assertIsNone(ledger.record_spend("demo", 0, now=at(9)))
        self.assertIsNone(ledger.record_spend("demo", -5, now=at(9)))
        self.assertFalse(os.path.exists(self.file))

    def test_spends_on_one_day_add_up_per_project(self):
        ledger.record_spend("demo", 12.3, now=at(9))
        self.assertEqual(ledger.record_spend("demo", 7.7, now=at(10)), 20.0)

    def test_the_points_of_a_day_without_readings_are_zero(self):
        ledger.record_reading(40, now=at(9))
        ledger.record_reading(43, now=at(10))
        self.assertEqual(ledger.daily_points(ledger.read()[0], at(9, day=14)), 0.0)

    def test_tokens_with_no_project_sum_every_project(self):
        ledger.record_spend("alpha", 10, now=at(9))
        ledger.record_spend("beta", 5.5, now=at(9))
        doc = ledger.read()[0]
        self.assertEqual(ledger.tokens_k(doc, None, "day", at(9)), 15.5)
        self.assertEqual(ledger.tokens_k(doc, "alpha", "day", at(9)), 10.0)

    def test_tokens_of_a_project_with_no_spend_are_zero(self):
        ledger.record_spend("alpha", 10, now=at(9))
        self.assertEqual(ledger.tokens_k(ledger.read()[0], "gamma", "week", at(9)), 0.0)

    def test_last_reading_is_none_without_readings_and_the_newest_otherwise(self):
        self.assertIsNone(ledger.last_reading(ledger.read()[0]))
        ledger.record_reading(40, now=at(9))
        ledger.record_reading(41, now=at(9, 30))
        self.assertEqual(ledger.last_reading(ledger.read()[0]).timestamp(), at(9, 30).timestamp())

    def test_pace_of_points_is_the_slope_of_today_points_per_hour(self):
        for minutes, weekly in ((0, 40), (30, 41), (60, 42)):
            ledger.record_reading(weekly, now=at(9) + datetime.timedelta(minutes=minutes))
        doc = ledger.read()[0]  # points 0, 1, 2 at 9:00, 9:30, 10:00
        self.assertAlmostEqual(ledger.pace_per_hour(doc, at(10), "pts"), 2.0)

    def test_the_weekly_pace_ignores_readings_before_a_weekly_reset(self):
        for minutes, weekly in ((0, 40), (30, 41), (40, 10), (50, 11), (60, 12)):
            ledger.record_reading(weekly, now=at(9) + datetime.timedelta(minutes=minutes))
        doc = ledger.read()[0]
        # after the reset at 9:40 only 10, 11, 12 count: one point every ten minutes is six per hour
        self.assertAlmostEqual(ledger.pace_per_hour(doc, at(10), "w"), 6.0)

    def test_a_pace_needs_two_readings_and_ten_minutes_of_span(self):
        ledger.record_reading(40, now=at(9))
        self.assertIsNone(ledger.pace_per_hour(ledger.read()[0], at(9, 1), "w"))
        ledger.record_reading(41, now=at(9, 5))
        self.assertIsNone(ledger.pace_per_hour(ledger.read()[0], at(9, 6), "w"))
        ledger.record_reading(42, now=at(9, 10))
        self.assertIsNotNone(ledger.pace_per_hour(ledger.read()[0], at(9, 11), "w"))


class ProjectIdTests(ControlCase):
    def test_a_data_folder_maps_to_its_registered_project_id(self):
        data_dir = os.path.join(self.project, "docs")
        self.assertEqual(ledger.project_id_for_dir(data_dir), "demo")
        self.assertIsNone(ledger.project_id_for_dir(os.path.join(self.tmp, "elsewhere", "docs")))


class LimitsGapTests(ControlCase):
    def setUp(self):
        super().setUp()
        self.now = at(14, 2)
        self.project = config.get_project("demo")

    def reading(self, weekly, minutes_before_now=2):
        moment = self.now - datetime.timedelta(minutes=minutes_before_now)
        write_json(os.path.join(self.state_dir, "usage.json"),
                   {"schemaVersion": 1, "weeklyPercent": weekly, "updated": moment.isoformat(timespec="seconds")})
        ledger.record_reading(weekly, None, now=moment)

    def rows(self):
        return {row["id"]: row for row in limits.evaluate_rows(self.project, now=self.now, strict=True)}

    def test_label_names_a_row_in_the_activity_form(self):
        row = {"id": "L3", "scope": "global", "window": "day", "kind": "pct", "value": 10.0, "action": "block"}
        self.assertEqual(limits.label(row), "L3 global day pct 10% block")
        row = {"id": "L1", "scope": "project", "window": "week", "kind": "tok", "value": 200.0, "action": "warn"}
        self.assertEqual(limits.label(row), "L1 project week tok 200k warn")
        row = {"id": "L2", "scope": "global", "window": "day", "kind": "pct", "value": 2.5, "action": "block"}
        self.assertEqual(limits.label(row), "L2 global day pct 2.5% block")

    def test_global_rows_keeps_only_the_valid_stored_rows(self):
        def add_rows(rows):
            rows.extend([
                {"id": "L1", "window": "day", "kind": "pct", "value": 10, "action": "block"},
                {"id": "X1", "window": "day", "kind": "pct", "value": 10, "action": "block"},
                {"id": "L2", "window": "month", "kind": "pct", "value": 10, "action": "block"},
                {"id": "L3", "window": "week", "kind": "tok", "value": "5", "action": "block"},
                "not a row",
                {"id": "L4", "window": "week", "kind": "tok", "value": 5, "action": "warn"},
            ])

        config.update_limits(add_rows)
        rows = limits.global_rows()
        self.assertEqual([row["id"] for row in rows], ["L1", "L4"])
        self.assertEqual({row["scope"] for row in rows}, {"global"})
        self.assertEqual({row["src"] for row in rows}, {"config"})

    def test_a_tok_row_is_unknown_when_the_ledger_is_corrupt_and_never_blocks(self):
        self.reading(40)
        limits.add(self.project, "project", "week", "tok", 10, now=self.now)
        with open(ledger.path(), "w", encoding="utf-8") as fh:
            fh.write("garbage")
        row = self.rows()["L1"]
        self.assertIsNone(row["used"])
        self.assertEqual(row["state"], "unknown")
        self.assertNotEqual(limits.evaluate(self.project, now=self.now)["state"], "block")

    def test_the_ratio_of_a_zero_limit_is_all_or_nothing(self):
        self.assertEqual(limits._ratio(5, 0), 100.0)
        self.assertEqual(limits._ratio(0, 0), 0.0)
        self.assertEqual(limits._ratio(50, 200), 25.0)

    def test_a_project_pct_estimate_has_no_pace_even_when_the_trend_is_rising(self):
        self.reading(40, minutes_before_now=70)
        self.reading(43, minutes_before_now=12)
        ledger.record_spend("demo", 250, now=at(13, 55))
        ledger.record_spend("other", 250, now=at(13, 56))
        limits.add(self.project, "project", "day", "pct", 2, now=self.now)
        row = self.rows()["L1"]
        self.assertTrue(row["est"])
        self.assertEqual(row["used"], 1.5)
        self.assertIsNone(row["paceAt"])

    def test_with_no_rules_the_evaluation_is_ok_with_nothing_in_it(self):
        write_json(os.path.join(self.docs, "autonomy.json"), {"schemaVersion": 2})
        self.assertEqual(limits.evaluate(self.project, now=self.now),
                         {"state": "ok", "row": None, "used": None, "limit": None})

    def test_a_warned_weekly_stop_is_described_as_usage_at_a_percent(self):
        self.assertEqual(limits.describe({"id": "AUTO", "state": "warn", "used": 85.0, "limit": 100.0}),
                         "weekly usage at 85%")
        self.assertEqual(limits.describe({"id": "AUTO", "state": "block", "used": 100.0, "limit": 100.0}),
                         "weekly usage 100% reached stopAtPercent 100%")

    def test_list_rows_names_every_row_that_applies_without_evaluating_them(self):
        limits.add(self.project, "global", "day", "pct", 10, now=self.now)     # L1, config
        limits.add(self.project, "project", "week", "tok", 50, now=self.now)   # L2, budget.json limitRows
        budget.set_project_limit(self.docs, 200)                               # BUD
        rows = limits.list_rows(self.project)
        self.assertEqual(sorted(row["id"] for row in rows), ["AUTO", "BUD", "L1", "L2"])
        self.assertTrue(all("state" not in row for row in rows))

    def test_add_returns_the_prior_row_and_keeps_the_id_of_the_replaced_row(self):
        prior, saved = limits.add(self.project, "global", "day", "pct", 10, now=self.now)
        self.assertIsNone(prior)
        self.assertEqual((saved["id"], saved["value"], saved["action"]), ("L1", 10.0, "block"))
        prior, saved = limits.add(self.project, "global", "day", "pct", 20, action="warn", now=self.now)
        self.assertEqual((prior["value"], prior["action"]), (10.0, "block"))
        self.assertEqual((saved["id"], saved["value"], saved["action"]), ("L1", 20.0, "warn"))

    def test_rm_returns_the_removed_row_and_a_second_rm_is_not_found(self):
        limits.add(self.project, "global", "day", "pct", 10, now=self.now)
        removed = limits.rm(self.project, "L1", now=self.now)
        self.assertEqual((removed["id"], removed["value"]), ("L1", 10.0))
        self.assertEqual(limits.global_rows(), [])
        with self.assertRaises(RoadmapError) as cm:
            limits.rm(self.project, "L1", now=self.now)
        self.assertEqual(cm.exception.code, "not_found")

    def test_rm_refuses_an_id_that_is_not_a_row_id(self):
        with self.assertRaises(RoadmapError) as cm:
            limits.rm(self.project, "X9", now=self.now)
        self.assertEqual(cm.exception.code, "usage")

    @unittest.expectedFailure
    def test_rm_that_raises_not_found_leaves_the_budget_file_unchanged(self):
        # BUG (services/limits.py:541-545): mutate_project pops a stored row whose id matches even when the row is
        # malformed, _clean_row then returns None, the save happens, and rm raises not_found. The file has changed.
        path = os.path.join(self.docs, "budget.json")
        write_json(path, {"schemaVersion": 1, "limits": {"project": None, "phases": {}, "models": {}, "tasks": {}},
                          "spent": {}, "jobs": [], "limitRows": [{"id": "L7", "window": "week", "kind": "tok"}]})
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
        with self.assertRaises(RoadmapError):
            limits.rm(self.project, "L7", now=self.now)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    @unittest.expectedFailure
    def test_removing_a_warning_budget_returns_it_with_its_warn_action(self):
        # BUG (services/limits.py:532): remove_row builds the prior BUD row with action "block" even when the budget
        # stores limitAction "warn", so an undo of `limit rm BUD` would restore a blocking budget.
        budget.set_project_limit(self.docs, 200, "warn")
        removed = limits.rm(self.project, "BUD", now=self.now)
        self.assertEqual(removed["action"], "warn")

    def test_status_line_with_no_rows_says_none_set(self):
        self.assertEqual(limits.status_line([]), "limits: none set")

    def test_status_line_names_the_three_worst_rows_and_counts_the_rest(self):
        rows = [self.fake(i, state) for i, state in enumerate(["ok", "block", "ok", "warn", "ok"], 1)]
        self.assertEqual(limits.status_line(rows),
                         "limits: day 1/10% BLOCK; day 1/10% WARN; day 1/10% ok (+2 more)")

    def test_show_lines_with_no_rows_gives_the_hint(self):
        self.assertEqual(limits.show_lines([]),
                         ["no limits set (for example: roadmap limit set --scope global --window day --pct 10)"])

    def test_show_lines_stops_at_eight_lines_and_says_how_many_are_hidden(self):
        lines = limits.show_lines([self.fake(i, "ok") for i in range(1, 11)])
        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[-1], "(+3 more rows)")

    def fake(self, number, state):
        return {"id": "L%d" % number, "scope": "global", "window": "day", "kind": "pct", "used": 1.0,
                "limit": 10.0, "est": False, "state": state, "src": "config", "paceAt": None, "action": "block"}


if __name__ == "__main__":
    unittest.main()
