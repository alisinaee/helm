"""WP27: the usage ledger, the limit rows, fan-out, fail-open, the CLI, undo and the snapshot meters.

Every test runs under a temp ROADMAP_HOME with a temp project (ControlCase / HomeCase). Times are injected: the
readings and the evaluations use the local clock values built by at(), never the real clock.
"""

import datetime
import hashlib
import json
import os
from unittest import mock

from roadmap.core.snapshot import build_snapshot
from roadmap.errors import RoadmapError
from roadmap.services import budget, control, hooks, ledger, limits, limits_v2
from roadmap.services import commands as command_layer
from roadmap.store import config
from tests.unit.test_control_support import ROADMAP_CONFIG, TASKS, ControlCase, read_json, write_json
from tests.unit.test_jobs_support import run_cli
from tests.unit.test_store_support import HomeCase


def at(hour, minute=0, day=13):
    """A local aware time on 2026-10-<day>."""
    return datetime.datetime(2026, 10, day, hour, minute).astimezone()


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class LedgerTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.file = ledger.path()

    def test_forty_then_forty_three_on_one_day_is_three_points(self):
        ledger.record_reading(40, now=at(9))
        ledger.record_reading(43, now=at(10))
        self.assertEqual(ledger.daily_points(ledger.read()[0], at(10)), 3.0)

    def test_a_reset_of_43_then_1_adds_one(self):
        ledger.record_reading(43, now=at(9))
        ledger.record_reading(1, now=at(10))
        self.assertEqual(ledger.daily_points(ledger.read()[0], at(10)), 1.0)

    def test_the_first_reading_after_midnight_is_compared_with_the_last_one_before(self):
        ledger.record_reading(40, now=at(23, 0, day=13))
        ledger.record_reading(43, now=at(0, 30, day=14))
        doc = ledger.read()[0]
        self.assertEqual(ledger.daily_points(doc, at(0, 30, day=14)), 3.0)
        self.assertEqual(ledger.daily_points(doc, at(23, 0, day=13)), 0.0)

    def test_the_file_keeps_fourteen_days_and_stays_under_4_kb(self):
        for day in range(1, 21):
            for project in ("alpha", "beta", "gamma", "delta"):
                ledger.record_spend(project, 12.3, now=at(9, day=day))
            for minute in range(0, 24, 2):
                ledger.record_reading(10 + day * 0.4 + minute * 0.01, now=at(9, minute, day=day))
        doc, status = ledger.read()
        self.assertEqual(status, "ok")
        self.assertLessEqual(len(doc["days"]), 14)
        self.assertLessEqual(os.path.getsize(self.file), 4096)

    def test_a_corrupt_file_is_moved_aside_and_started_again(self):
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(ledger.read()[1], "corrupt")
        ledger.record_reading(5, now=at(9))
        self.assertEqual(ledger.read()[1], "ok")
        self.assertTrue(os.path.exists(self.file + ".corrupt"))

    def test_an_estimate_needs_two_hundred_thousand_tracked_tokens(self):
        ledger.record_reading(40, now=at(9))
        ledger.record_reading(43, now=at(10))
        ledger.record_spend("demo", 100, now=at(11))
        doc = ledger.read()[0]
        self.assertIsNone(ledger.rate(doc, at(11)))
        self.assertIsNone(ledger.project_estimate(doc, "demo", "day", at(11)))
        ledger.record_spend("demo", 150, now=at(12))
        doc = ledger.read()[0]
        self.assertAlmostEqual(ledger.rate(doc, at(12)), 3.0 / 250)
        self.assertAlmostEqual(ledger.project_estimate(doc, "demo", "day", at(12)), 3.0)

    def test_pace_is_the_slope_of_the_last_two_hours(self):
        for minutes, weekly in ((0, 40), (30, 41), (60, 42)):
            ledger.record_reading(weekly, now=at(9) + datetime.timedelta(minutes=minutes))
        doc = ledger.read()[0]
        self.assertAlmostEqual(ledger.pace_per_hour(doc, at(10), "w"), 2.0)


class PaceTests(ControlCase):
    def test_the_pace_is_anchored_on_the_newest_reading_so_it_does_not_move_with_the_clock(self):
        for minutes, weekly in ((0, 40), (30, 41), (60, 42)):
            ledger.record_reading(weekly, now=at(9) + datetime.timedelta(minutes=minutes))
        write_json(os.path.join(self.state_dir, "usage.json"),
                   {"schemaVersion": 1, "weeklyPercent": 42, "updated": at(10).isoformat(timespec="seconds")})
        ledger.record_reading(42, now=at(10))
        project = config.get_project("demo")
        control.set_limit_row("demo", "global", "week", "pct", 60, now=at(10, 1))
        first = {r["id"]: r for r in limits.evaluate_rows(project, now=at(10, 1), strict=True)}
        second = {r["id"]: r for r in limits.evaluate_rows(project, now=at(10, 20), strict=True)}
        self.assertIsNotNone(first["L1"]["paceAt"])
        self.assertEqual(first["L1"]["paceAt"], second["L1"]["paceAt"])


class LimitMatrixTests(ControlCase):
    """Each kind, window and action, read from the same stores the hook and the status use."""

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

    def set_row(self, scope, window, kind, value, action="block"):
        return control.set_limit_row("demo", scope, window, kind, value, action, now=self.now)["row"]["id"]

    def test_global_day_pct_warns_at_eighty_and_blocks_at_one_hundred(self):
        self.reading(40, minutes_before_now=20)
        self.reading(48, minutes_before_now=10)
        row = self.set_row("global", "day", "pct", 10)
        self.assertEqual(self.rows()[row]["state"], "warn")
        self.reading(50, minutes_before_now=1)
        self.assertEqual(self.rows()[row]["state"], "block")
        self.assertIn("reached at 100%", limits.describe(self.rows()[row]))
        self.assertIn("global day limit", control.recompute("demo", now=self.now)["block"]["reason"])
        self.assertTrue(self.sentinel_exists())

    def test_a_warn_action_warns_and_never_blocks(self):
        self.reading(40, minutes_before_now=20)
        self.reading(50, minutes_before_now=1)
        row = self.set_row("global", "day", "pct", 10, "warn")
        self.assertEqual(self.rows()[row]["state"], "warn")
        state = control.recompute("demo", now=self.now)
        self.assertIsNone(state["block"])
        self.assertFalse(self.sentinel_exists())

    def test_a_project_estimate_is_its_token_share_of_the_measured_points(self):
        self.reading(40, minutes_before_now=70)
        self.reading(43, minutes_before_now=12)  # 3 points today, from 13:50 to 14:02
        ledger.record_spend("demo", 250, now=at(13, 55))
        ledger.record_spend("other", 250, now=at(13, 56))  # rate 3/500, so demo's 250k is 1.5 points
        row = self.set_row("project", "day", "pct", 2)
        self.assertEqual(self.rows()[row]["used"], 1.5)
        self.assertTrue(self.rows()[row]["est"])
        self.assertEqual(self.rows()[row]["state"], "ok")  # 75% of 2 is below the warn line
        self.reading(45, minutes_before_now=3)  # 5 points today: demo's share is 2.5, which is 125%
        self.assertEqual(self.rows()[row]["used"], 2.5)
        self.assertEqual(self.rows()[row]["state"], "block")
        self.assertIn("project day limit", control.recompute("demo", now=self.now)["block"]["reason"])

    def test_without_two_hundred_thousand_tracked_a_project_pct_row_is_unknown(self):
        self.reading(40, minutes_before_now=70)
        self.reading(43, minutes_before_now=12)
        ledger.record_spend("demo", 100, now=at(13, 55))
        row = self.set_row("project", "day", "pct", 10)
        self.assertEqual(self.rows()[row]["state"], "unknown")
        self.assertIsNone(control.recompute("demo", now=self.now)["block"])

    def test_a_tok_day_row_counts_exact_job_tokens(self):
        row = self.set_row("project", "day", "tok", 100)
        ledger.record_spend("demo", 60, now=at(13))
        self.assertEqual(self.rows()[row]["state"], "ok")
        ledger.record_spend("demo", 45, now=at(13, 30))
        self.assertEqual(self.rows()[row]["used"], 105.0)
        self.assertEqual(self.rows()[row]["state"], "block")
        self.assertIn("project day token limit", control.recompute("demo", now=self.now)["block"]["reason"])

    def test_the_project_total_budget_blocks_and_a_warn_action_only_warns(self):
        self.set_budget(limits={"project": 100}, spent={"P0.2": {"sonnet": 85}})
        self.assertEqual(control.recompute("demo", now=self.now)["warn"], ["project budget at 85%"])
        self.set_budget(limits={"project": 100}, spent={"P0.2": {"sonnet": 100}})
        self.assertEqual(control.recompute("demo", now=self.now)["block"]["reason"], "project budget 100% used")
        self.set_row("project", "total", "tok", 100, "warn")
        state = control.recompute("demo", now=self.now)
        self.assertIsNone(state["block"])
        self.assertEqual(state["warn"], ["project budget at 100%"])

    def week_stop(self, value=100):
        limits_v2.set_window("week", {"on": True, "mode": "cap", "value": value})

    def test_the_weekly_stop_is_the_limits_week_window(self):
        self.reading(101)
        self.assertIsNone(control.recompute("demo", now=self.now)["block"])  # Limits week is off: no stop
        self.week_stop(100)
        self.assertIn("week usage reached the stop at 100%",
                      control.recompute("demo", now=self.now)["block"]["reason"])
        self.assertNotIn("AUTO", self.rows())

    def test_a_global_week_pct_uses_the_measured_weekly_percent(self):
        self.reading(62, minutes_before_now=5)
        row = self.set_row("global", "week", "pct", 60)
        self.assertEqual(self.rows()[row]["used"], 62.0)
        self.assertEqual(self.rows()[row]["state"], "block")

    def test_stale_usage_makes_pct_and_acct_unknown_but_tok_still_enforces(self):
        self.reading(105, minutes_before_now=120)  # older than 90 minutes
        self.week_stop(100)
        pct = self.set_row("global", "day", "pct", 10)
        tok = self.set_row("project", "day", "tok", 20)
        ledger.record_spend("demo", 25, now=at(13, 30))
        rows = self.rows()
        self.assertEqual(rows[pct]["state"], "unknown")
        self.assertEqual(rows["SWK"]["state"], "block")  # an ON stop with a stale reading blocks (R11.160)
        self.assertEqual(rows[tok]["state"], "block")
        self.assertEqual(limits.evaluate(self.project, now=self.now)["state"], "block")

    def test_stale_usage_alone_never_blocks_when_limits_are_off(self):
        self.reading(105, minutes_before_now=120)
        self.assertNotIn("AUTO", self.rows())
        self.assertIsNone(control.recompute("demo", now=self.now)["block"])

    def test_stale_usage_blocks_an_on_week_stop(self):
        self.reading(105, minutes_before_now=120)
        self.week_stop(100)
        self.assertEqual(self.rows()["SWK"]["state"], "block")

    def test_a_corrupt_ledger_leaves_pct_and_acct_unknown(self):
        self.reading(105, minutes_before_now=2)
        pct = self.set_row("global", "day", "pct", 10)
        with open(ledger.path(), "w", encoding="utf-8") as fh:
            fh.write("garbage")
        self.assertEqual(self.rows()[pct]["state"], "unknown")
        self.assertIsNone(control.recompute("demo", now=self.now)["block"])

    def test_a_failing_evaluation_is_ok_and_does_not_break_the_recompute(self):
        with mock.patch.object(limits, "_evaluate_rows", side_effect=RuntimeError("boom")):
            self.assertEqual(limits.evaluate_rows(self.project, now=self.now), [])
            self.assertEqual(limits.evaluate(self.project, now=self.now)["state"], "ok")
            self.assertIsNone(control.recompute("demo", now=self.now)["block"])

    def test_the_check_refuses_combinations_that_do_not_exist(self):
        cases = [("global", "week", "acct", 50), ("global", "total", "tok", 10), ("project", "total", "pct", 10),
                 ("project", "week", "acct", 0), ("project", "day", "pct", 101), ("project", "day", "tok", 0),
                 ("nowhere", "day", "pct", 1), ("project", "day", "pct", True)]
        for scope, window, kind, value in cases:
            with self.assertRaises(RoadmapError) as ctx:
                limits.check_spec(scope, window, kind, value)
            self.assertEqual(ctx.exception.code, "usage")

    def test_an_autonomy_stop_is_ignored_and_the_file_is_not_touched_by_reading_rows(self):
        old = self.make_project("old")
        old_docs = os.path.join(old, "docs")
        write_json(os.path.join(old_docs, "autonomy.json"),
                   {"schemaVersion": 2, "limit": {"kind": "weekly", "stopAtPercent": 100}})
        write_json(os.path.join(old_docs, "roadmap.config.json"), ROADMAP_CONFIG)
        config.add_project("Old", old)
        before = digest(os.path.join(old_docs, "autonomy.json"))
        self.reading(100, minutes_before_now=3)
        control.recompute_all(self.now)
        rows = limits.evaluate_rows(config.get_project("old"), now=self.now, strict=True)
        self.assertEqual([r for r in rows if r["src"] == "autonomy"], [])  # R11.164: Limits is the only source
        self.assertEqual(digest(os.path.join(old_docs, "autonomy.json")), before)


class FanOutAndHookTests(ControlCase):
    def setUp(self):
        super().setUp()
        self.now = at(14, 2)
        other = self.make_project("other")
        write_json(os.path.join(other, "docs", "tasks.json"), TASKS)
        write_json(os.path.join(other, "docs", "roadmap.config.json"), dict(ROADMAP_CONFIG, id="other"))
        config.add_project("Other", other)

    def reading(self, weekly, minutes_before_now=2):
        moment = self.now - datetime.timedelta(minutes=minutes_before_now)
        write_json(os.path.join(self.state_dir, "usage.json"),
                   {"schemaVersion": 1, "weeklyPercent": weekly, "updated": moment.isoformat(timespec="seconds")})
        ledger.record_reading(weekly, None, now=moment)

    def gate(self, now):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {},
                   "cwd": self.project}
        return hooks.run_hook(json.dumps(payload), now=now.timestamp())

    def test_a_global_row_blocks_every_project_and_the_hook_denies(self):
        self.reading(40, minutes_before_now=20)
        self.reading(45, minutes_before_now=1)
        control.set_limit_row("demo", "global", "day", "pct", 2, now=self.now)
        self.assertTrue(os.path.exists(os.path.join(self.state_dir, "block-demo")))
        self.assertTrue(os.path.exists(os.path.join(self.state_dir, "block-other")))
        self.assertEqual(control.read_state("other")["block"]["scope"], "global")
        reply = self.gate(self.now)
        self.assertEqual(reply["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("global day limit", reply["hookSpecificOutput"]["permissionDecisionReason"])

    def test_the_roadmap_hook_command_denies_a_global_block_on_every_project(self):
        self.reading(40, minutes_before_now=20)
        self.reading(45, minutes_before_now=1)
        control.set_limit_row("demo", "global", "day", "pct", 2, now=self.now)
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {},
                              "cwd": self.project})
        with mock.patch("roadmap.services.hooks.time.time", return_value=self.now.timestamp()):
            code, out, _ = run_cli(["hook", "pre"], stdin_text=payload)
        self.assertEqual(code, 0)
        reply = json.loads(out)
        self.assertEqual(reply["hookSpecificOutput"]["permissionDecision"], "deny")
        code, out, _ = run_cli(["hook", "pre"], stdin_text=json.dumps({
            "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}, "cwd": self.project}))
        self.assertEqual((code, out), (0, ""))

    def test_an_override_lets_the_hook_through_until_it_expires(self):
        self.reading(40, minutes_before_now=20)
        self.reading(45, minutes_before_now=1)
        control.set_limit_row("demo", "global", "day", "pct", 2, now=self.now)
        control.override("demo", 1, now=self.now)
        self.assertIsNone(self.gate(self.now + datetime.timedelta(minutes=30)))
        later = self.now + datetime.timedelta(hours=2)
        self.now = later
        self.reading(45, minutes_before_now=1)  # a fresh reading, still over the day row
        self.assertIsNotNone(self.gate(later))

    def test_stale_usage_lets_the_hook_through(self):
        self.reading(40, minutes_before_now=20)
        self.reading(45, minutes_before_now=1)
        control.set_limit_row("demo", "global", "day", "pct", 2, now=self.now)
        self.assertIsNotNone(self.gate(self.now))
        self.reading(45, minutes_before_now=120)  # the reading is two hours old now
        control.recompute_all(self.now)
        self.assertFalse(os.path.exists(os.path.join(self.state_dir, "block-demo")))
        self.assertIsNone(self.gate(self.now))


class CliTests(ControlCase):
    def setUp(self):
        super().setUp()
        self.now = at(14, 2)

    def envelope(self, argv):
        code, out, err = run_cli(argv + ["--json"])
        return code, json.loads(out) if out.strip() else None, err

    def test_limit_set_prints_the_row_id_and_show_lists_it(self):
        code, out, _ = run_cli(["limit", "set", "--scope", "global", "--window", "day", "--pct", "2"])
        self.assertEqual((code, out.strip()), (0, "L1 set"))
        code, out, _ = run_cli(["limit", "show"])
        lines = out.strip().splitlines()
        self.assertLessEqual(len(lines), 8)
        self.assertTrue(lines[0].startswith("L1 global day ?/2% unknown"), lines[0])

    def test_the_old_form_still_sets_the_weekly_stop(self):
        code, out, _ = run_cli(["limit", "set", "60"])
        self.assertEqual((code, out.strip()), (0, "weekly stop at 60%"))
        self.assertEqual(limits_v2.load()["week"]["value"], 60)
        self.assertTrue(limits_v2.load()["week"]["on"])
        self.assertNotIn("stopAtPercent", read_json(os.path.join(self.docs, "autonomy.json"))["limit"])

    def test_an_agent_shell_is_refused_for_set_and_rm(self):
        self._env("CLAUDECODE", "1")
        code, _, err = run_cli(["limit", "set", "--scope", "global", "--window", "day", "--pct", "2"])
        self.assertNotEqual(code, 0)
        self.assertIn("refused", err)
        code, _, err = run_cli(["limit", "rm", "AUTO"])
        self.assertNotEqual(code, 0)
        self.assertIn("refused", err)

    def test_undo_restores_the_previous_row_and_rm_is_undone_too(self):
        self.envelope(["limit", "set", "--scope", "global", "--window", "day", "--pct", "2"])
        _, body, _ = self.envelope(["limit", "set", "--scope", "global", "--window", "day", "--pct", "5"])
        second = body["data"]["activity"]
        self.assertEqual(config.load()["limits"][0]["value"], 5)
        self.assertEqual(run_cli(["undo", second])[0], 0)
        self.assertEqual(config.load()["limits"][0]["value"], 2)
        _, body, _ = self.envelope(["limit", "rm", "L1"])
        removal = body["data"]["activity"]
        self.assertEqual(config.load()["limits"], [])
        self.assertEqual(run_cli(["undo", removal])[0], 0)
        self.assertEqual(config.load()["limits"][0]["value"], 2)

    def test_removing_the_weekly_stop_is_undone_by_its_set(self):
        self.set_usage(10)
        run_cli(["limit", "set", "70"])
        _, body, _ = self.envelope(["limit", "rm", "AUTO"])
        activity = body["data"]["activity"]
        self.assertFalse(limits_v2.load()["week"]["on"])
        self.assertEqual(run_cli(["undo", activity])[0], 0)
        self.assertEqual((limits_v2.load()["week"]["on"], limits_v2.load()["week"]["value"]), (True, 70))

    def test_a_project_total_row_is_the_budget_and_shows_as_bud(self):
        code, out, _ = run_cli(["limit", "set", "--window", "total", "--tokens", "200"])
        self.assertEqual((code, out.strip()), (0, "BUD set"))
        self.assertEqual(budget.get(self.docs)["limits"]["project"], 200.0)
        rows = limits.evaluate_rows(config.get_project("demo"), now=self.now, strict=True)
        self.assertIn(("BUD", "budget"), [(r["id"], r["src"]) for r in rows])

    def test_status_has_the_limits_line_and_stays_within_eight_lines(self):
        run_cli(["limit", "set", "--scope", "global", "--window", "day", "--pct", "2"])
        code, out, _ = run_cli(["status"])
        lines = out.strip().splitlines()
        self.assertLessEqual(len(lines), 8)
        self.assertTrue(any(line.startswith("limits: ") for line in lines))
        self.assertLessEqual(len(out.strip()), 700)

    def test_a_finished_job_adds_its_tokens_to_the_ledger(self):
        budget.record_job_spend(self.docs, "j1", "P0.2", "sonnet", 50)
        self.assertEqual(ledger.tokens_k(ledger.read()[0], "demo", "day"), 50.0)
        budget.record_job_spend(self.docs, "j1", "P0.2", "sonnet", 50)
        self.assertEqual(ledger.tokens_k(ledger.read()[0], "demo", "day"), 50.0)

    def test_the_snapshot_carries_meters_and_a_snapshot_without_them_is_unchanged(self):
        from roadmap.services import loader
        snap = loader.load_snapshot("demo", now=self.now)
        self.assertEqual(set(snap["meters"]), {"limits", "today", "week"})
        self.assertIn("pct", snap["meters"]["week"])
        plain = build_snapshot({}, {}, self.now)
        self.assertNotIn("meters", plain)
        self.assertEqual(set(plain) - {"meters"}, set(build_snapshot({}, {}, self.now, meters=None)))


class OperationTests(ControlCase):
    def test_the_registry_checks_the_new_limit_shapes(self):
        check = command_layer.OPS["limit.set"].check
        self.assertEqual(check({"pct": 40}), {"pct": 40})
        spec = check({"scope": "global", "window": "day", "kind": "pct", "value": 2, "action": "block"})
        self.assertEqual(spec["row"]["scope"], "global")
        with self.assertRaises(RoadmapError):
            check({"scope": "global", "window": "week", "kind": "acct", "value": 2})
        with self.assertRaises(RoadmapError):
            command_layer.OPS["limit.rm"].check({"id": "../x"})
