"""Budget guard (R11.164): the stops come only from Tokens > Limits (limits_v2); the usage reading comes from
docs/autonomy.json usage. job start refuses at a stop (exit 3) and warns on stale usage when no stop is on.
Uses a temp ROADMAP_HOME; nothing touches the keychain or port 8780."""

import datetime
import json
import os
import tempfile
import unittest

from roadmap.services import budget, jobs, limits_v2
from tests.unit.test_cmd_support import CmdCase
from tests.unit.test_store_support import HomeCase

NOW = datetime.datetime.now(datetime.timezone.utc)  # relative times, so the CLI tests (real clock) agree


def _autonomy(weekly=82, five=34, updated=None, extra=None):
    stamp = updated or (NOW - datetime.timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    doc = {"schemaVersion": 2, "maxUsageAgeMin": 90,
           "limit": {"kind": "weekly", "stopAtPercent": 85, "fiveHourStopAtPercent": 80},  # legacy keys: ignored
           "usage": {"weeklyPercent": weekly, "fiveHourPercent": five, "updated": stamp}}
    doc.update(extra or {})
    return doc


def _write(folder, doc):
    with open(os.path.join(folder, budget.AUTONOMY_FILE), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def _stops(week=None, five=None):
    """Set the Limits windows: a cap percent, or None for off."""
    for window, value in (("week", week), ("five_hour", five)):
        patch = {"on": False} if value is None else {"on": True, "mode": "cap", "value": value}
        limits_v2.set_window(window, patch)


class GuardServiceTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.folder = os.path.join(self.tmp, "docs")
        os.makedirs(self.folder)

    def test_weekly_at_the_limits_stop_is_a_stop(self):
        _stops(week=85)
        _write(self.folder, _autonomy(weekly=86))
        self.assertEqual(budget.guard(self.folder, NOW), ("stop: weekly 86% >= 85%", None))

    def test_weekly_below_the_stop_is_allowed(self):
        _stops(week=85)
        _write(self.folder, _autonomy(weekly=84))
        self.assertEqual(budget.guard(self.folder, NOW), (None, None))

    def test_five_hour_stop_is_checked_too(self):
        _stops(week=95, five=80)
        _write(self.folder, _autonomy(weekly=10, five=81))
        self.assertEqual(budget.guard(self.folder, NOW), ("stop: 5-hour 81% >= 80%", None))

    def test_legacy_five_hour_80_with_limits_off_is_allowed(self):
        _stops(week=None, five=None)
        _write(self.folder, _autonomy(weekly=99, five=86))
        self.assertEqual(budget.guard(self.folder, NOW), (None, None))

    def test_limits_week_cap_20_with_25_percent_fresh_is_blocked(self):
        _stops(week=20, five=None)
        _write(self.folder, _autonomy(weekly=25, five=10))
        self.assertEqual(budget.guard(self.folder, NOW), ("stop: weekly 25% >= 20%", None))

    def test_a_stale_reading_on_an_on_stop_blocks_with_the_stale_hint(self):
        _stops(week=20)
        stamp = (NOW - datetime.timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        _write(self.folder, _autonomy(weekly=5, updated=stamp))
        stop, warn = budget.guard(self.folder, NOW)
        self.assertIn("stop: weekly stop at 20%: usage is stale", stop)
        self.assertIn("sync usage before starting new work", stop)
        self.assertIsNone(warn)

    def test_cleanup_drops_the_legacy_keys_and_keeps_a_note(self):
        _write(self.folder, _autonomy())
        budget.guard(self.folder, NOW)
        with open(os.path.join(self.folder, budget.AUTONOMY_FILE), encoding="utf-8") as fh:
            limit = json.load(fh)["limit"]
        self.assertNotIn("stopAtPercent", limit)
        self.assertNotIn("fiveHourStopAtPercent", limit)
        self.assertEqual(limit["note"], "moved to Tokens > Limits (R11.164)")
        self.assertFalse(budget.drop_legacy_stops(self.folder))  # second run: nothing to do
        self.assertFalse(limits_v2.load()["five_hour"]["on"])  # the 5h value is not migrated

    def test_missing_file_gives_no_stop_and_no_warning(self):
        self.assertEqual(budget.guard(self.folder, NOW), (None, None))

    def test_stale_usage_warns_after_91_minutes_and_does_not_stop(self):
        stamp = (NOW - datetime.timedelta(minutes=91)).isoformat().replace("+00:00", "Z")
        _write(self.folder, _autonomy(updated=stamp))
        stop, warn = budget.guard(self.folder, NOW)
        self.assertIsNone(stop)
        self.assertEqual(warn, "usage 91 min old: run usage push")

    def test_usage_three_hours_old_reads_in_hours(self):
        stamp = (NOW - datetime.timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        _write(self.folder, _autonomy(updated=stamp))
        self.assertEqual(budget.guard(self.folder, NOW), (None, "usage 3h old: run usage push"))

    def test_fresh_usage_gives_no_warning(self):
        stamp = (NOW - datetime.timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
        _write(self.folder, _autonomy(updated=stamp))
        self.assertEqual(budget.guard(self.folder, NOW), (None, None))

    def test_max_age_comes_from_the_file(self):
        stamp = (NOW - datetime.timedelta(minutes=31)).isoformat().replace("+00:00", "Z")
        _write(self.folder, _autonomy(updated=stamp, extra={"maxUsageAgeMin": 30}))
        self.assertEqual(budget.guard(self.folder, NOW)[1], "usage 31 min old: run usage push")

    def test_unreadable_file_warns_and_does_not_refuse(self):
        with open(os.path.join(self.folder, budget.AUTONOMY_FILE), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(budget.guard(self.folder, NOW), (None, "autonomy.json unreadable: limits not checked"))


class JobStartGuardTests(CmdCase):
    def _limits(self, **kwargs):
        _write(self.data, _autonomy(**kwargs))

    def test_job_start_refused_at_a_weekly_stop_with_exit_3(self):
        _stops(week=85)
        self._limits(weekly=86)
        code, out, err = self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.assertEqual(code, 3, err)
        self.assertIn("stop: weekly 86% >= 85%", err)
        self.assertEqual(out, "")
        self.assertEqual(jobs.list_jobs(self.data), [])

    def test_legacy_five_hour_80_with_limits_off_starts(self):
        _stops(week=None, five=None)
        self._limits(weekly=40, five=86)
        code, out, err = self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "j1"), err)

    def test_job_start_allowed_at_84(self):
        _stops(week=85)
        self._limits(weekly=84)
        code, out, err = self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "j1"), err)
        self.assertNotIn("warn", err)

    def test_stale_usage_warns_but_the_job_starts(self):
        stamp = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)).isoformat()
        self._limits(weekly=40, updated=stamp.replace("+00:00", "Z"))
        code, out, err = self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "j1"), err)
        self.assertIn("warn: usage 3h old: run usage push", err)

    def test_folder_without_autonomy_json_starts_silently(self):
        os.remove(os.path.join(self.data, budget.AUTONOMY_FILE))
        code, out, err = self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "j1"), err)
        self.assertEqual(err, "")

    def test_default_file_without_usage_warns_and_starts(self):
        # project init writes an autonomy.json with no usage block: no reading, so the warning says to push usage
        code, out, err = self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "j1"), err)
        self.assertIn("warn: usage has no readable time: run usage push", err)


if __name__ == "__main__":
    unittest.main()
