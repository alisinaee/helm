"""Budget guard: budget.guard() reads only docs/autonomy.json. job start refuses at a stop (exit 3) and warns on stale
usage (never refuses for it). Uses the temp ROADMAP_HOME of the CMD case; nothing touches the keychain or port 8780."""

import datetime
import json
import os
import tempfile
import unittest

from roadmap.services import budget, jobs
from tests.unit.test_cmd_support import CmdCase

NOW = datetime.datetime.now(datetime.timezone.utc)  # relative times, so the CLI tests (real clock) agree


def _autonomy(weekly=82, five=34, updated=None, extra=None):
    stamp = updated or (NOW - datetime.timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    doc = {"schemaVersion": 2, "maxUsageAgeMin": 90,
           "limit": {"kind": "weekly", "stopAtPercent": 85, "fiveHourStopAtPercent": 80},
           "usage": {"weeklyPercent": weekly, "fiveHourPercent": five, "updated": stamp}}
    doc.update(extra or {})
    return doc


def _write(folder, doc):
    with open(os.path.join(folder, budget.AUTONOMY_FILE), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


class GuardServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_weekly_at_the_stop_is_a_stop(self):
        _write(self.folder, _autonomy(weekly=86))
        self.assertEqual(budget.guard(self.folder, NOW), ("stop: weekly 86% >= 85%", None))

    def test_weekly_below_the_stop_is_allowed(self):
        _write(self.folder, _autonomy(weekly=84))
        self.assertEqual(budget.guard(self.folder, NOW), (None, None))

    def test_five_hour_stop_is_checked_too(self):
        _write(self.folder, _autonomy(weekly=10, five=81))
        self.assertEqual(budget.guard(self.folder, NOW), ("stop: 5-hour 81% >= 80%", None))

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

    def test_a_stop_is_not_hidden_by_a_stale_warning(self):
        stamp = (NOW - datetime.timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        _write(self.folder, _autonomy(weekly=90, updated=stamp))
        self.assertEqual(budget.guard(self.folder, NOW), ("stop: weekly 90% >= 85%", None))

    def test_unreadable_file_warns_and_does_not_refuse(self):
        with open(os.path.join(self.folder, budget.AUTONOMY_FILE), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(budget.guard(self.folder, NOW), (None, "autonomy.json unreadable: limits not checked"))


class JobStartGuardTests(CmdCase):
    def _limits(self, **kwargs):
        _write(self.data, _autonomy(**kwargs))

    def test_job_start_refused_at_a_weekly_stop_with_exit_3(self):
        self._limits(weekly=86)
        code, out, err = self.cli(["job", "start", "x", "haiku", "P1.1"])
        self.assertEqual(code, 3, err)
        self.assertIn("stop: weekly 86% >= 85%", err)
        self.assertEqual(out, "")
        self.assertEqual(jobs.list_jobs(self.data), [])

    def test_job_start_allowed_at_84(self):
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
