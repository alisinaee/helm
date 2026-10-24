"""R11.166: the active config-dir account refreshes its own expired token, and a rewritten login beats the gaps.

Token readers, stamps and the endpoint are fakes: no keychain, no network."""

import json
import unittest
from unittest import mock

from roadmap.services import usage as uc, usage_sources as src
from tests.unit.test_usage_backoff import at, denied_keychain
from tests.unit.test_usage_collector import GOOD_REPLY
from tests.unit.test_usage_store import UsageCase

WHERE = {"service": "Claude Code-credentials-deadbeef", "file": None}


def account(refreshable=True):
    return {"id": "noob", "location": WHERE, "connected": True, "refreshable": refreshable}


def expired_oauth(refresh="R"):
    return {"accessToken": "A", "refreshToken": refresh, "expiresAt": 1000}


class ActiveRefreshTests(UsageCase):
    def cfg(self):
        return self.config_with([])

    def test_expired_token_with_refresh_token_is_refreshed_and_stored(self):
        written = []
        posts = []

        def post(url, body):
            posts.append(body["grant_type"])
            return {"access_token": "NEW", "refresh_token": "R2", "expires_in": 3600}

        def token(allow_refresh=False, location=None):
            self.assertTrue(allow_refresh)  # refreshable account: refresh on without usageTokenRefresh
            with mock.patch.object(src, "load_credentials",
                                   return_value=(expired_oauth(), {"claudeAiOauth": expired_oauth()},
                                                 ("keychain", WHERE["service"]))):
                return src.access_token(allow_refresh=allow_refresh, location=location, post=post,
                                        write=lambda place, text: written.append((place, json.loads(text))),
                                        now_s=2000)

        seen = []
        with mock.patch.object(uc.usage_accounts, "active_for_sync", return_value=account()), \
                mock.patch.object(uc, "read_keychain_token", token), \
                mock.patch.object(uc, "http_fetch", lambda tok, *a, **k: seen.append(tok) or GOOD_REPLY):
            result = uc.sync_once(self.cfg(), now=at(0))
        self.assertEqual(posts, ["refresh_token"])
        self.assertEqual(written[0][0], ("keychain", WHERE["service"]))
        self.assertEqual(written[0][1]["claudeAiOauth"]["accessToken"], "NEW")
        self.assertEqual(seen[0], "NEW")
        self.assertIsNotNone(result)

    def test_live_login_is_not_refreshed_without_opt_in(self):
        flags = []
        with mock.patch.object(uc.usage_accounts, "active_for_sync", return_value=account(False)), \
                mock.patch.object(uc, "read_keychain_token",
                                  lambda allow_refresh=False, location=None: flags.append(allow_refresh)
                                  or (_ for _ in ()).throw(uc.UsageError("x", uc.CODE_EXPIRED))):
            try:
                uc.sync_once(self.cfg(), now=at(0))
            except uc.UsageError:
                pass
        self.assertEqual(flags, [False])


class LocationStampTests(UsageCase):
    def cfg(self):
        return self.config_with([])

    def fail(self, stamp):
        with mock.patch.object(uc.usage_accounts, "active_for_sync", return_value=account(False)), \
                mock.patch.object(uc, "read_keychain_token", denied_keychain()), \
                mock.patch.object(uc.usage_sources, "location_stamp", return_value=stamp):
            try:
                uc.sync_once(self.cfg(), now=at(0))
            except uc.UsageError:
                pass

    def second(self, stamp, **kw):
        keychain = denied_keychain()
        with mock.patch.object(uc.usage_accounts, "active_for_sync", return_value=account(False)), \
                mock.patch.object(uc, "read_keychain_token", keychain), \
                mock.patch.object(uc.usage_sources, "location_stamp", return_value=stamp):
            try:
                uc.sync_once(self.cfg(), now=at(10), **kw)
            except uc.UsageError:
                pass
        return keychain

    def test_rewritten_item_within_gap_is_retried(self):
        self.fail("t1")
        self.second("t2").assert_called()

    def test_rewritten_item_beats_background_backoff(self):
        self.fail("t1")
        self.second("t2", background=True).assert_called()

    def test_unchanged_item_within_gap_is_skipped(self):
        self.fail("t1")
        self.second("t1").assert_not_called()


if __name__ == "__main__":
    unittest.main()
