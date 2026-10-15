"""R7.63: one usage truth. A window whose reset has passed has no current percent (null, reason "reset passed"),
and the weekly limit uses the same reading and staleness rule as the usage view (the top bar).

Pure view checks need no home; the limit checks run under a temp ROADMAP_HOME (HomeCase).
"""

import datetime
import json
import os
import unittest

from roadmap.services import limits, usage
from tests.unit.test_store_support import HomeCase

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def record(**fields):
    base = {"weeklyPercent": 82, "fiveHourPercent": 34, "weeklyResetsAt": "2026-10-20T00:00:00+00:00",
            "fiveHourResetsAt": "2026-10-15T15:00:00+00:00", "updated": "2026-10-15T11:59:00+00:00",
            "source": "Anthropic usage endpoint"}
    base.update(fields)
    return base


class ResetPassedTests(HomeCase):
    def test_a_passed_five_hour_reset_has_no_current_percent(self):
        out = usage.view(record(fiveHourResetsAt="2026-10-14T09:50:00+00:00"), now=NOW)
        self.assertIsNone(out["fiveHourPercent"])
        self.assertEqual(out["fiveHourReason"], "reset passed")
        self.assertEqual(out["weeklyPercent"], 82)
        self.assertIsNone(out["weeklyReason"])

    def test_a_passed_weekly_reset_has_no_current_percent(self):
        out = usage.view(record(weeklyResetsAt="2026-10-14T00:00:00+00:00"), now=NOW)
        self.assertIsNone(out["weeklyPercent"])
        self.assertEqual(out["weeklyReason"], "reset passed")
        self.assertEqual(out["fiveHourPercent"], 34)
        self.assertIsNone(out["fiveHourReason"])

    def test_a_reset_exactly_now_has_passed(self):
        out = usage.view(record(fiveHourResetsAt="2026-10-15T12:00:00+00:00"), now=NOW)
        self.assertIsNone(out["fiveHourPercent"])

    def test_a_future_reset_keeps_the_number(self):
        out = usage.view(record(), now=NOW)
        self.assertEqual((out["weeklyPercent"], out["fiveHourPercent"]), (82, 34))
        self.assertIsNone(out["weeklyReason"] or out["fiveHourReason"])

    def test_a_missing_reset_keeps_the_number(self):
        out = usage.view(record(fiveHourResetsAt=None, weeklyResetsAt=None), now=NOW)
        self.assertEqual((out["weeklyPercent"], out["fiveHourPercent"]), (82, 34))

    def test_the_stored_record_is_not_changed_by_the_view(self):
        raw = record(fiveHourResetsAt="2026-10-14T09:50:00+00:00")
        usage.view(raw, now=NOW)
        self.assertEqual(raw["fiveHourPercent"], 34)

    def test_stale_reading_is_older_than_ninety_minutes(self):
        fresh = usage.view(record(updated="2026-10-15T10:31:00+00:00"), now=NOW)
        old = usage.view(record(updated="2026-10-15T10:29:00+00:00"), now=NOW)
        self.assertFalse(fresh["stale"])
        self.assertTrue(old["stale"])
        self.assertEqual(old["ageS"], 5400 + 60)
        self.assertEqual(fresh["maxAgeS"], 90 * 60)

    def test_autonomy_key_maxUsageAgeMin_overrides_the_default(self):
        path = os.path.join(self.tmp, "proj", "docs", "autonomy.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 1, "maxUsageAgeMin": 30}, fh)
        cfg = {"projects": [{"id": "p", "path": os.path.join(self.tmp, "proj")}]}
        self.assertEqual(usage.max_age_s(cfg), 30 * 60)
        self.assertEqual(usage.max_age_s({"projects": []}), 90 * 60)

    def test_no_reading_is_stale(self):
        self.assertTrue(usage.view({}, now=NOW)["stale"])


class LimitUsageTests(HomeCase):
    def write(self, **fields):
        path = usage.paths.usage_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = {"schemaVersion": 1, "weeklyPercent": 63, "fiveHourPercent": 26,
                "weeklyResetsAt": "2026-10-20T00:00:00+00:00", "fiveHourResetsAt": "2026-10-15T15:00:00+00:00",
                "updated": (NOW - datetime.timedelta(seconds=30)).isoformat(timespec="seconds"),
                "source": "Anthropic usage endpoint"}
        body.update(fields)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh)

    def test_a_fresh_reading_gives_the_weekly_percent(self):
        self.write()
        self.assertEqual(limits._usage_state(NOW), (63.0, True))

    def test_a_stale_reading_is_not_fresh_for_the_limits(self):
        self.write(updated=(NOW - datetime.timedelta(hours=31)).isoformat(timespec="seconds"))
        self.assertFalse(limits._usage_state(NOW)[1])

    def test_a_passed_weekly_reset_is_unknown_for_the_limits(self):
        self.write(weeklyResetsAt="2026-10-14T00:00:00+00:00")
        self.assertEqual(limits._usage_state(NOW), (None, False))

    def test_limits_and_top_bar_share_one_staleness_rule(self):
        for seconds in (60, 5399, 5401, 7200):
            self.write(updated=(NOW - datetime.timedelta(seconds=seconds)).isoformat(timespec="seconds"))
            fresh = limits._usage_state(NOW)[1]
            self.assertEqual(fresh, not usage.show(now=NOW)["stale"], seconds)

    def test_the_stale_top_bar_and_limits_agree_on_unknown(self):
        self.write(updated=(NOW - datetime.timedelta(hours=31)).isoformat(timespec="seconds"))
        shown = usage.show(now=NOW)
        self.assertTrue(shown["stale"])
        self.assertFalse(limits._usage_state(NOW)[1])


if __name__ == "__main__":
    unittest.main()
