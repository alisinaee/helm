"""R7.77: usage is stored with no manual step, from a hook payload's rate_limits block or the status line sidecar,
at most once a minute and only when newer. ROADMAP_HOME and HOME are temp dirs; no keychain is read."""

import datetime
import json
import os
import unittest
from unittest import mock

from roadmap.services import hooks
from roadmap.services import usage as uc
from tests.unit.test_store_support import HomeCase

CONFIG = {"projects": []}


def block(week=80, five=67):
    return {"five_hour": {"used_percentage": five, "resets_at": 1800000000},
            "seven_day": {"used_percentage": week, "resets_at": "2030-10-19T05:59:59Z"}}


class AutoCase(HomeCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(uc, "_control_after_write")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = datetime.datetime.now().astimezone()

    def test_parse_rate_limits(self):
        changes = uc.parse_rate_limits(block())
        self.assertEqual(changes["weeklyPercent"], 80)
        self.assertEqual(changes["fiveHourPercent"], 67)
        self.assertEqual(changes["weeklyResetsAt"], "2030-10-19T05:59:59Z")
        self.assertTrue(changes["fiveHourResetsAt"])
        self.assertEqual(uc.parse_rate_limits({"seven_day": {"used_percentage": 140}}), {})
        self.assertEqual(uc.parse_rate_limits(None), {})

    def test_hook_payload_is_stored_with_its_source(self):
        source = uc.auto_update({"rate_limits": block()}, self.now, CONFIG, sidecar="/nonexistent")
        self.assertEqual(source, uc.SOURCE_HOOK)
        shown = uc.show(CONFIG)
        self.assertEqual(shown["weeklyPercent"], 80)
        self.assertEqual(shown["source"], uc.SOURCE_HOOK)
        self.assertFalse(shown["stale"])

    def test_once_per_minute(self):
        uc.auto_update({"rate_limits": block()}, self.now, CONFIG, sidecar="/nonexistent")
        later = self.now + datetime.timedelta(seconds=30)
        self.assertIsNone(uc.auto_update({"rate_limits": block(90)}, later, CONFIG, sidecar="/nonexistent"))
        self.assertEqual(uc.show(CONFIG)["weeklyPercent"], 80)
        after = self.now + datetime.timedelta(seconds=61)
        self.assertEqual(uc.auto_update({"rate_limits": block(90)}, after, CONFIG, sidecar="/nonexistent"),
                         uc.SOURCE_HOOK)
        self.assertEqual(uc.show(CONFIG)["weeklyPercent"], 90)

    def test_sidecar_is_used_when_fresh_and_newer(self):
        path = os.path.join(self.tmp, "rate-limits.json")
        data = dict(block(55, 20), timestamp=self.now.timestamp() * 1000, source="statusline")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        self.assertEqual(uc.auto_update({}, self.now, CONFIG, sidecar=path), uc.SOURCE_STATUSLINE)
        self.assertEqual(uc.show(CONFIG)["weeklyPercent"], 55)
        # the same sidecar a minute later is not newer than the stored reading
        again = self.now + datetime.timedelta(seconds=90)
        self.assertIsNone(uc.auto_update({}, again, CONFIG, sidecar=path))

    def test_old_sidecar_is_ignored(self):
        path = os.path.join(self.tmp, "rate-limits.json")
        old = self.now - datetime.timedelta(hours=1)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(dict(block(), timestamp=old.timestamp() * 1000), fh)
        self.assertIsNone(uc.auto_update({}, self.now, CONFIG, sidecar=path))

    def test_a_newer_head_push_is_not_overwritten_by_an_older_sidecar(self):
        uc.push(json.dumps({"rateLimits": [{"kind": "seven_day", "percentUsed": 70}]}), CONFIG)
        path = os.path.join(self.tmp, "rate-limits.json")
        old = self.now - datetime.timedelta(minutes=5)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(dict(block(10), timestamp=old.timestamp() * 1000), fh)
        self.assertIsNone(uc.auto_update({}, self.now, CONFIG, sidecar=path))
        self.assertEqual(uc.show(CONFIG)["weeklyPercent"], 70)

    def test_hook_never_fails_on_usage(self):
        with mock.patch.object(uc, "auto_update", side_effect=RuntimeError("boom")):
            hooks._usage_auto({"rate_limits": block()}, self.now.timestamp())
        with mock.patch.object(uc, "auto_update", return_value=None) as auto:
            hooks.run_hook(json.dumps({"hook_event_name": "Stop", "rate_limits": block()}), environ={}, cwd=self.tmp)
        auto.assert_called_once()
        self.assertIn("rate_limits", auto.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
