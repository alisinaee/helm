"""R7.100: no claude.ai login in the keychain is unavailable, not an error. A manual sync returns ok with status
"unavailable", sets no lastError and names the one-time setup step; since R10.29 it no longer asks the head (no
request flag). A real failure stays an error.

The keychain reader and the endpoint are stubbed: nothing runs `security` and no network connection is opened.
ROADMAP_HOME and HOME are temp dirs.
"""

import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from roadmap.services import usage as uc
from roadmap.store import atomic, paths
from tests.unit.test_store_support import HomeCase

CONFIG = {"projects": []}


def no_login_token():
    raise uc.UsageError("keychain entry has no usable token", uc.CODE_NO_TOKEN)


class KeychainShapeTests(unittest.TestCase):

    def test_entry_without_a_claude_login_is_no_token(self):
        run = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"mcpOAuth": {}}', stderr="")
        with mock.patch.object(uc.subprocess, "run", return_value=run):
            with self.assertRaises(uc.UsageError) as cm:
                uc.read_keychain_token()
        self.assertEqual(cm.exception.code, uc.CODE_NO_TOKEN)


class UnavailableCase(HomeCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(uc, "_control_after_write")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = datetime.now(timezone.utc)
        self.fetch = mock.Mock(side_effect=AssertionError("the endpoint must not be called"))

    def sync(self, now=None, background=False):
        return uc.sync_once(CONFIG, get_token=no_login_token, fetch=self.fetch, background=background,
                            now=now or self.now)


class ManualSyncTests(UnavailableCase):

    def test_manual_sync_without_a_login_is_unavailable_not_an_error(self):
        result = self.sync()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("claude auth login", result["reason"])
        store = uc._load_store()
        self.assertIsNone(store.get("lastError"))
        self.assertEqual(store["syncError"], uc.CODE_NO_TOKEN)
        self.fetch.assert_not_called()

    def test_the_usage_view_carries_the_status(self):
        self.sync()
        view = uc.show(CONFIG, now=self.now)
        self.assertEqual(view["status"], "unavailable")
        self.assertIsNone(view["lastError"])

    def test_a_manual_sync_no_longer_asks_the_head(self):
        self.sync()
        self.assertFalse(uc.refresh_requested(self.now))

    def test_a_second_tap_inside_the_gap_is_still_unavailable(self):
        self.sync()
        result = self.sync(now=self.now + timedelta(seconds=10))
        self.assertEqual(result["status"], "unavailable")

    def test_background_sync_without_a_login_writes_no_flag(self):
        result = self.sync(background=True)
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(uc.refresh_requested(self.now))


class RequestFlagTests(UnavailableCase):

    def test_a_fresh_flag_is_a_request(self):
        atomic.write_json(uc.request_path(), {"at": (self.now - timedelta(minutes=5)).isoformat(timespec="seconds")})
        self.assertTrue(uc.refresh_requested(self.now))

    def test_an_old_flag_is_not_a_request(self):
        atomic.write_json(uc.request_path(), {"at": (self.now - timedelta(hours=2)).isoformat(timespec="seconds")})
        self.assertFalse(uc.refresh_requested(self.now))

    def test_a_damaged_flag_is_not_a_request(self):
        paths.ensure_dir(paths.state_dir())
        with open(uc.request_path(), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertFalse(uc.refresh_requested(self.now))

    def test_a_new_reading_clears_the_request(self):
        atomic.write_json(uc.request_path(), {"at": (self.now - timedelta(minutes=5)).isoformat(timespec="seconds")})
        self.assertTrue(uc.refresh_requested(self.now))
        uc.push(json.dumps({"rateLimits": [{"kind": "five_hour", "percentUsed": 10}]}), CONFIG)
        self.assertFalse(uc.refresh_requested(self.now))


class RealErrorTests(UnavailableCase):

    def test_a_network_failure_is_still_an_error(self):
        def down(token):
            raise uc.UsageError("usage endpoint not reachable", uc.CODE_NET)

        with self.assertRaises(uc.UsageError):
            uc.sync_once(CONFIG, get_token=lambda: "t", fetch=down, now=self.now)
        store = uc._load_store()
        self.assertEqual(store["syncError"], uc.CODE_NET)
        self.assertIn("not reachable", store["lastError"])
        self.assertEqual(uc.view(store, now=self.now)["status"], uc.STATUS_ERROR)
        self.assertFalse(uc.refresh_requested(self.now))

    def test_an_expired_token_is_still_an_error(self):
        def expired(token):
            raise uc.UsageError("usage endpoint answered HTTP 401")

        with self.assertRaises(uc.UsageError):
            uc.sync_once(CONFIG, get_token=lambda: "t", fetch=expired, now=self.now)
        self.assertIn("401", uc._load_store()["lastError"])


if __name__ == "__main__":
    unittest.main()
