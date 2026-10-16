"""Keychain backoff, the syncError reason code, and the usage.set op (R7.27).

The keychain and the endpoint are fakes: nothing here runs `security` or opens a network connection. The keychain
failures are injected with mock, and the clock is passed in as `now`.
"""

import datetime
import json
import os
import threading
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import commands, usage as uc
from roadmap.store import paths
from tests.unit.test_cmd_support import CmdCase
from tests.unit.test_usage_collector import FAKE_TOKEN, GOOD_REPLY


NOW_UTC = datetime.datetime.now(datetime.timezone.utc)
# A manual weekly reset in the future (+01:00 offset kept as typed); a fixed past date reads as "reset passed".
MANUAL_WEEKLY_RESET = (NOW_UTC + datetime.timedelta(days=3)).astimezone(
    datetime.timezone(datetime.timedelta(hours=1))).isoformat(timespec="seconds")


def fresh_reply():
    """GOOD_REPLY with both resets in the future (a passed reset has no current percent)."""
    later = (NOW_UTC + datetime.timedelta(hours=3)).isoformat(timespec="seconds")
    week = (NOW_UTC + datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return dict(GOOD_REPLY, five_hour=dict(GOOD_REPLY["five_hour"], resets_at=later),
                seven_day=dict(GOOD_REPLY["seven_day"], resets_at=week))
from tests.unit.test_usage_store import UsageCase

T0 = datetime.datetime(2026, 10, 15, 9, 0, 0, tzinfo=datetime.timezone.utc)


def at(seconds):
    return T0 + datetime.timedelta(seconds=seconds)


def denied_keychain():
    """A real keychain failure (access denied). A missing claude.ai login is unavailable instead (R7.100)."""
    return mock.Mock(side_effect=uc.UsageError("keychain access denied or failed (exit 36)", uc.CODE_DENIED))


class KeychainBackoffTests(UsageCase):
    def cfg(self):
        return self.config_with([])

    def test_keychain_failure_records_code_text_and_retry_time(self):
        keychain = denied_keychain()
        with mock.patch.object(uc, "read_keychain_token", keychain):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(0))
        stored = uc._load_store()
        self.assertEqual(stored["syncError"], uc.CODE_DENIED)
        self.assertIn("denied", stored["lastError"])
        self.assertEqual(stored["keychainRetryAfter"], (at(0) + datetime.timedelta(hours=6)).isoformat(
            timespec="seconds"))

    def test_background_loop_skips_the_keychain_during_backoff(self):
        keychain = denied_keychain()
        with mock.patch.object(uc, "read_keychain_token", keychain):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(0))
            self.assertIsNone(uc.sync_once(self.cfg(), background=True, now=at(3600)))
            self.assertIsNone(uc.sync_once(self.cfg(), background=True, now=at(6 * 3600 - 1)))
        self.assertEqual(keychain.call_count, 1)

    def test_background_retries_the_keychain_after_six_hours(self):
        keychain = denied_keychain()
        with mock.patch.object(uc, "read_keychain_token", keychain):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(0))
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), background=True, now=at(6 * 3600 + 1))
        self.assertEqual(keychain.call_count, 2)

    def test_manual_sync_within_a_minute_is_refused_without_a_keychain_read(self):
        keychain = denied_keychain()
        with mock.patch.object(uc, "read_keychain_token", keychain):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(0))
            with self.assertRaisesRegex(uc.UsageError, "try again in a minute") as cm:
                uc.sync_once(self.cfg(), now=at(30))
        self.assertEqual(cm.exception.code, uc.CODE_DENIED)
        self.assertEqual(keychain.call_count, 1)

    def test_manual_sync_after_a_minute_may_retry(self):
        keychain = denied_keychain()
        with mock.patch.object(uc, "read_keychain_token", keychain):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(0))
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(61))
        self.assertEqual(keychain.call_count, 2)

    def test_each_keychain_code_backs_off(self):
        for code in (uc.CODE_NO_TOKEN, uc.CODE_DENIED, uc.CODE_DENIED):
            with self.subTest(code=code):
                if os.path.exists(paths.usage_file()):
                    os.remove(paths.usage_file())
                keychain = mock.Mock(side_effect=uc.UsageError("x", code))
                with mock.patch.object(uc, "read_keychain_token", keychain):
                    if code in uc.UNAVAILABLE_CODES:  # no claude.ai login: unavailable, not an error (R7.100)
                        self.assertEqual(uc.sync_once(self.cfg(), now=at(0))["status"], uc.STATUS_UNAVAILABLE)
                    else:
                        with self.assertRaises(uc.UsageError):
                            uc.sync_once(self.cfg(), now=at(0))
                    self.assertIsNone(uc.sync_once(self.cfg(), background=True, now=at(600)))
                self.assertEqual(keychain.call_count, 1)
                self.assertEqual(uc._load_store()["syncError"], code)

    def test_network_failure_keeps_the_normal_schedule(self):
        def down(token):
            raise uc.UsageError("usage endpoint not reachable", uc.CODE_NET)

        with mock.patch.object(uc, "http_fetch", side_effect=down) as fetch:
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(0))
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), background=True, now=at(120))
        self.assertEqual(fetch.call_count, 2)
        stored = uc._load_store()
        self.assertEqual(stored["syncError"], uc.CODE_NET)
        self.assertNotIn("keychainRetryAfter", stored)

    def test_success_clears_the_code_and_the_backoff(self):
        with mock.patch.object(uc, "read_keychain_token", denied_keychain()):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(0))
        result = uc.sync_once(self.cfg(), background=True, now=at(6 * 3600 + 5))
        self.assertEqual(result["usage"]["weeklyPercent"], 62.4)
        stored = uc._load_store()
        self.assertIsNone(stored["syncError"])
        self.assertIsNone(stored["lastError"])
        self.assertIsNone(stored["keychainRetryAfter"])

    def test_failure_keeps_the_last_good_values(self):
        uc.sync_once(self.cfg())
        with mock.patch.object(uc, "read_keychain_token", denied_keychain()):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(7200))
        view = uc.show(self.cfg())
        self.assertEqual(view["weeklyPercent"], 62.4)
        self.assertEqual(view["fiveHourPercent"], 17)
        self.assertEqual(view["syncError"], uc.CODE_DENIED)

    def test_view_exposes_only_the_code_and_the_text(self):
        with mock.patch.object(uc, "read_keychain_token", denied_keychain()):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(self.cfg(), now=at(0))
        view = uc.show(self.cfg())
        self.assertEqual(view["syncError"], uc.CODE_DENIED)
        self.assertIn("denied", view["lastError"])
        self.assertNotIn("keychainRetryAfter", view)
        self.assertNotIn("manualAttemptAt", view)
        self.assertNotIn(FAKE_TOKEN, json.dumps(view))

    def test_loop_reads_the_keychain_once_across_many_cycles(self):
        keychain = denied_keychain()
        waits = iter([False] * 5 + [True])
        with mock.patch.object(uc, "read_keychain_token", keychain):
            uc.run_loop(threading.Event(), config=self.cfg(), wait=lambda seconds: next(waits))
        self.assertEqual(keychain.call_count, 1)


class UsageSetTests(CmdCase):
    def config_with(self):
        return {"usage": {"intervalS": 120, "mirrorToProjects": True}, "projects": []}

    def setUp(self):
        super().setUp()
        self.keychain = mock.Mock(return_value=FAKE_TOKEN)
        self.fetch = mock.Mock(return_value=fresh_reply())
        for patcher in (mock.patch.object(uc, "read_keychain_token", self.keychain),
                        mock.patch.object(uc, "http_fetch", self.fetch)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def set_usage(self, args, source="gui", now=None):
        return commands.run("usage.set", args, source, self.data, now=now)

    def stored(self):
        return uc.stored_record()

    def test_stores_a_manual_entry_and_returns_the_view(self):
        reply = self.set_usage({"weekly": 61, "fiveHour": 12, "weeklyResetsAt": MANUAL_WEEKLY_RESET})
        self.assertTrue(reply["ok"])
        view = reply["data"]["usage"]
        self.assertEqual(view["weeklyPercent"], 61)
        self.assertEqual(view["fiveHourPercent"], 12)
        self.assertEqual(view["source"], "manual entry")
        self.assertEqual(view["weeklyResetsAt"], MANUAL_WEEKLY_RESET)
        self.assertIsNone(view["syncError"])
        self.assertIsNone(view["lastError"])
        self.assertIsNotNone(self.stored()["updated"])
        self.keychain.assert_not_called()
        self.fetch.assert_not_called()

    def test_omitted_five_hour_window_keeps_its_value(self):
        self.set_usage({"weekly": 61, "fiveHour": 12})
        self.set_usage({"weekly": 70})
        stored = self.stored()
        self.assertEqual(stored["weeklyPercent"], 70)
        self.assertEqual(stored["fiveHourPercent"], 12)

    def test_clears_an_earlier_sync_error(self):
        with mock.patch.object(uc, "read_keychain_token", denied_keychain()):
            with self.assertRaises(uc.UsageError):
                uc.sync_once(config=self.config_with(), now=at(0))
        self.assertEqual(self.stored()["syncError"], uc.CODE_DENIED)
        self.set_usage({"weekly": 40})
        self.assertIsNone(self.stored()["syncError"])
        self.assertIsNone(self.stored()["lastError"])

    def test_writes_one_activity_line(self):
        reply = self.set_usage({"weekly": 61})
        lines = self.read_lines("activity.jsonl")
        self.assertEqual(lines[-1]["id"], reply["activity"])
        self.assertIn("usage week 61%", json.dumps(lines[-1]))

    def test_undo_puts_the_previous_values_back(self):
        self.set_usage({"weekly": 61, "fiveHour": 12})
        second = self.set_usage({"weekly": 70, "fiveHour": 30})
        self.assertTrue(second["undo"])
        self.op("undo", {"activity": second["activity"]})
        stored = self.stored()
        self.assertEqual(stored["weeklyPercent"], 61)
        self.assertEqual(stored["fiveHourPercent"], 12)

    def test_undo_of_the_first_entry_leaves_no_weekly_value(self):
        first = self.set_usage({"weekly": 61})
        self.op("undo", {"activity": first["activity"]})
        self.assertIsNone(uc.show(self.config_with())["weeklyPercent"])

    def test_agent_source_is_allowed(self):
        reply = self.set_usage({"weekly": 50}, source="agent")
        self.assertEqual(reply["data"]["usage"]["weeklyPercent"], 50)

    def test_bad_arguments_are_refused_and_write_nothing(self):
        bad = [
            {}, {"weekly": 101}, {"weekly": -1}, {"weekly": "50"}, {"weekly": True}, {"weekly": None},
            {"weekly": 50, "fiveHour": 200}, {"weekly": 50, "fiveHour": False},
            {"weekly": 50, "weeklyResetsAt": "tomorrow"}, {"weekly": 50, "fiveHourResetsAt": 5},
            {"weekly": float("nan")},
        ]
        for args in bad:
            with self.subTest(args=args):
                with self.assertRaises(RoadmapError) as cm:
                    self.set_usage(args)
                self.assertEqual(cm.exception.code, "usage")
        self.assertEqual(self.stored(), {})
        self.assertEqual(self.read_lines("activity.jsonl"), [])

    def test_internal_restore_op_is_not_callable(self):
        with self.assertRaises(RoadmapError):
            self.op("usage.restore", {"weeklyPercent": 1})


if __name__ == "__main__":
    unittest.main()
