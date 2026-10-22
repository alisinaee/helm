"""R10.29: the usage source chain. OAuth refresh (keychain and file), the 401 retry, the status line command and the
transcript estimate. Fakes only: `security` and the network are stubbed; HOME, ROADMAP_HOME and CLAUDE_CONFIG_DIR
are temp dirs.
"""

import argparse
import io
import json
import os
import stat
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from roadmap.commands import usage as usage_cmd
from roadmap.services import usage as uc
from roadmap.services import usage_sources as us
from tests.unit.test_store_support import HomeCase

OLD = "sk-ant-oat01-OLD-FAKE"
NEW = "sk-ant-oat01-NEW-FAKE"
REFRESH = "sk-ant-ort01-REFRESH-FAKE"
CONFIG = {"projects": []}
NOW_S = 2_000_000_000


def creds(expires_ms=None, refresh=REFRESH):
    oauth = {"accessToken": OLD, "refreshToken": refresh, "scopes": ["user:profile"]}
    if expires_ms is not None:
        oauth["expiresAt"] = expires_ms
    return json.dumps({"claudeAiOauth": oauth, "mcpOAuth": {"x": 1}})


def keychain(text):
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=text, stderr="")
    return run


class RefreshTests(HomeCase):

    def setUp(self):
        super().setUp()
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.tmp, "cfg")
        self.addCleanup(os.environ.pop, "CLAUDE_CONFIG_DIR", None)
        self.written = []
        self.posts = []

    def post(self, url, body):
        self.posts.append((url, body))
        return {"access_token": NEW, "refresh_token": "sk-ant-ort01-ROTATED", "expires_in": 3600}

    def write(self, place, text):
        self.written.append((place, text))

    def test_a_fresh_token_is_used_as_is(self):
        with mock.patch.object(us.subprocess, "run", keychain(creds((NOW_S + 3600) * 1000))):
            self.assertEqual(us.access_token(now_s=NOW_S, post=self.post, write=self.write), OLD)
        self.assertEqual(self.posts, [])

    def test_an_expiring_token_is_refreshed_and_written_back(self):
        with mock.patch.object(us.subprocess, "run", keychain(creds((NOW_S + 60) * 1000))):
            self.assertEqual(us.access_token(now_s=NOW_S, post=self.post, write=self.write, allow_refresh=True), NEW)
        url, body = self.posts[0]
        self.assertTrue(url.startswith("https://platform.claude.com/"))
        self.assertEqual(body["grant_type"], "refresh_token")
        self.assertEqual(body["client_id"], us.CLIENT_ID)
        place, text = self.written[0]
        self.assertEqual(place[0], "keychain")
        saved = json.loads(text)
        self.assertEqual(saved["claudeAiOauth"]["accessToken"], NEW)
        self.assertEqual(saved["claudeAiOauth"]["refreshToken"], "sk-ant-ort01-ROTATED")
        self.assertEqual(saved["claudeAiOauth"]["expiresAt"], (NOW_S + 3600) * 1000)
        self.assertEqual(saved["mcpOAuth"], {"x": 1})  # the rest of the item is kept

    def test_a_refused_refresh_is_expired_and_never_shows_a_token(self):
        def refuse(url, body):
            raise us.SourceError("token refresh answered HTTP 400", us.CODE_EXPIRED)
        with mock.patch.object(us.subprocess, "run", keychain(creds(0))):
            with self.assertRaises(us.SourceError) as cm:
                us.access_token(now_s=NOW_S, post=refuse, write=self.write, allow_refresh=True)
        self.assertEqual(cm.exception.code, us.CODE_EXPIRED)
        for secret in (OLD, REFRESH):
            self.assertNotIn(secret, str(cm.exception))
        self.assertEqual(self.written, [])

    def test_an_unreachable_host_falls_back_to_the_second_host(self):
        def flaky(url, body):
            if "platform" in url:
                raise us.SourceError("token endpoint not reachable", us.CODE_NET)
            return {"access_token": NEW}
        with mock.patch.object(us.subprocess, "run", keychain(creds(0))):
            self.assertEqual(us.access_token(now_s=NOW_S, post=flaky, write=self.write, allow_refresh=True), NEW)
        self.assertEqual(json.loads(self.written[0][1])["claudeAiOauth"]["refreshToken"], REFRESH)

    def test_desktop_only_item_is_no_token(self):
        with mock.patch.object(us.subprocess, "run", keychain('{"mcpOAuth": {}}')):
            with self.assertRaises(us.SourceError) as cm:
                us.access_token(now_s=NOW_S)
        self.assertEqual(cm.exception.code, us.CODE_NO_TOKEN)

    def test_the_credentials_file_is_used_and_rewritten_0600(self):
        folder = os.environ["CLAUDE_CONFIG_DIR"]
        os.makedirs(folder)
        path = os.path.join(folder, ".credentials.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(creds(0))
        missing = subprocess.CompletedProcess(args=[], returncode=44, stdout="", stderr="")
        with mock.patch.object(us.subprocess, "run", return_value=missing):
            self.assertEqual(us.access_token(now_s=NOW_S, post=self.post, allow_refresh=True), NEW)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["claudeAiOauth"]["accessToken"], NEW)

    def test_the_keychain_write_keeps_the_secret_out_of_argv(self):
        calls = []

        def run(args, **kwargs):
            calls.append((args, kwargs))
            out = '    "acct"<blob>="ali"\n' if "-i" not in args else ""
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=out, stderr="")
        with mock.patch.object(us.subprocess, "run", run):
            us._keychain_write(creds())
        args, kwargs = calls[-1]
        self.assertEqual(args, ["security", "-i"])
        self.assertNotIn(OLD, " ".join(args) + kwargs["input"])  # hex encoded on stdin
        self.assertIn(creds().encode("utf-8").hex(), kwargs["input"])
        self.assertIn('-a "ali"', kwargs["input"])


class RetryTests(unittest.TestCase):

    def test_a_401_is_retried_once_with_a_refreshed_token(self):
        seen = []

        def fetch(token):
            seen.append(token)
            if token == OLD:
                raise uc.UsageError("usage endpoint answered HTTP 401", status=401)
            return {"five_hour": {"utilization": 5}, "seven_day": {"utilization": 9}}
        reading = uc.collect(get_token=lambda: OLD, fetch=fetch, refresh=lambda: NEW)
        self.assertEqual(seen, [OLD, NEW])
        self.assertEqual(reading["weeklyPercent"], 9)


def line(moment, out=1000, mid="m"):
    return json.dumps({"type": "assistant", "timestamp": moment.isoformat().replace("+00:00", "Z"), "requestId": mid,
                       "message": {"id": mid, "usage": {"input_tokens": 0, "output_tokens": out}}})


class EstimateTests(HomeCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(uc, "_control_after_write")
        patcher.start()
        self.addCleanup(patcher.stop)
        us._cache.clear()
        self.root = os.path.join(os.environ["HOME"], ".claude", "projects", "p")
        os.makedirs(self.root)
        self.now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
        self.reset = self.now + timedelta(hours=2)          # the 5-hour window started at 09:00
        self.week_reset = self.now + timedelta(days=3)

    def transcript(self, rows):
        with open(os.path.join(self.root, "s.jsonl"), "a", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")

    def real_reading(self, at):
        uc.push(json.dumps({"rateLimits": [
            {"kind": "five_hour", "percentUsed": 10, "resetsAt": self.reset.isoformat()},
            {"kind": "seven_day", "percentUsed": 20, "resetsAt": self.week_reset.isoformat()}]}), CONFIG)
        uc._update_store({"updated": at.isoformat(), "lastReal": dict(uc._load_store()["lastReal"],
                                                                        updated=at.isoformat())})

    def test_sync_never_stores_an_estimate(self):
        # R10.40: estimates removed, site shows real readings only
        self.transcript([line(self.now - timedelta(hours=1), 10000, "a")])
        self.real_reading(self.now - timedelta(minutes=30))

        def no_login():
            raise uc.UsageError("keychain entry has no usable token", uc.CODE_NO_TOKEN)
        with mock.patch.object(uc, "estimate_once") as est:
            uc.sync_once(CONFIG, get_token=no_login, fetch=mock.Mock(), background=True, now=self.now)
        est.assert_not_called()
        self.assertFalse(uc._load_store().get("estimate"))

    def test_unknown_when_there_is_no_real_reading(self):
        self.transcript([line(self.now - timedelta(hours=1), 10000, "a")])

        def no_login():
            raise uc.UsageError("keychain entry has no usable token", uc.CODE_NO_TOKEN)
        uc.sync_once(CONFIG, get_token=no_login, fetch=mock.Mock(), background=True, now=self.now)
        store = uc._load_store()
        self.assertIsNone(store.get("fiveHourPercent"))
        self.assertNotEqual(store.get("source"), uc.SOURCE_ESTIMATE)

    def test_a_real_reading_is_not_marked_estimate(self):
        self.real_reading(self.now - timedelta(minutes=30))
        later = (self.now + timedelta(seconds=30)).astimezone()
        source = uc.auto_update({"rate_limits": {"five_hour": {"used_percentage": 33}}}, later, CONFIG)
        self.assertEqual(source, uc.SOURCE_HOOK)
        store = uc._load_store()
        self.assertFalse(store["estimate"])
        self.assertEqual(store["fiveHourPercent"], 33)


class StatuslineTests(HomeCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(uc, "_control_after_write")
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cmd(self, payload, then=None):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), mock.patch("sys.stdout", out):
            usage_cmd.handle_statusline(argparse.Namespace(then=then))
        return out.getvalue()

    def test_stores_the_rate_limits_and_prints_a_short_line(self):
        text = self.run_cmd({"rate_limits": {"five_hour": {"used_percentage": 12, "resets_at": 2000000000},
                                             "seven_day": {"used_percentage": 40}}})
        self.assertIn("5h 12%", text)
        store = uc._load_store()
        self.assertEqual(store["source"], uc.SOURCE_STATUSLINE)
        self.assertEqual(store["weeklyPercent"], 40)

    def test_the_wrapped_command_gets_the_same_stdin(self):
        text = self.run_cmd({"model": {"display_name": "X"}}, then="cat")
        self.assertIn('"display_name": "X"', text)

    def test_bad_input_still_prints(self):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("not json")), mock.patch("sys.stdout", out):
            usage_cmd.handle_statusline(argparse.Namespace(then=None))
        self.assertEqual(out.getvalue(), "\n")


CFG_OFF = {"projects": []}
CFG_ON = {"projects": [], "usage": {"usageTokenRefresh": True}}


class TokenRefreshOptInTests(HomeCase):
    """usageTokenRefresh is opt-in (default off). Off: an expired login is reported, never refreshed, never written.
    On: the existing refresh path runs and writes the rotated pair back."""

    def setUp(self):
        super().setUp()
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.tmp, "cfg")
        self.addCleanup(os.environ.pop, "CLAUDE_CONFIG_DIR", None)
        patcher = mock.patch.object(uc, "_control_after_write")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.post = mock.Mock(return_value={"access_token": NEW, "refresh_token": "sk-ant-ort01-ROTATED",
                                            "expires_in": 3600})
        self.keychain_write = mock.patch.object(us, "_keychain_write").start()
        self.file_write = mock.patch.object(us, "_file_write").start()
        self.addCleanup(mock.patch.stopall)

    def sync(self, cfg, expires_ms, fetch):
        with mock.patch.object(us.subprocess, "run", keychain(creds(expires_ms))), \
                mock.patch.object(us, "_post_json", self.post):
            return uc.sync_once(cfg, fetch=fetch, now=datetime(2030, 1, 1, tzinfo=timezone.utc))

    def test_flag_off_expired_login_is_not_refreshed_or_written(self):
        def never(token):
            raise AssertionError("the endpoint must not be called with an expired login")
        result = self.sync(CFG_OFF, 0, never)
        self.assertEqual(result["status"], "unavailable")
        self.post.assert_not_called()
        self.keychain_write.assert_not_called()
        self.file_write.assert_not_called()
        store = uc._load_store()
        self.assertEqual(store["syncError"], uc.CODE_EXPIRED)
        self.assertEqual(store["lastError"], us.EXPIRED_REASON)
        self.assertIn("then Sync now", store["lastError"])

    def test_flag_off_401_is_not_refreshed_or_written(self):
        def refused(token):
            raise uc.UsageError("usage endpoint answered HTTP 401", status=401)
        future = (NOW_S + 3600) * 1000
        with mock.patch.object(us.subprocess, "run", keychain(creds(future))), \
                mock.patch.object(us, "_post_json", self.post):
            uc.sync_once(CFG_OFF, fetch=refused, now=datetime.fromtimestamp(NOW_S, tz=timezone.utc))
        self.post.assert_not_called()
        self.keychain_write.assert_not_called()
        self.file_write.assert_not_called()
        self.assertEqual(uc._load_store()["syncError"], uc.CODE_EXPIRED)

    def test_flag_on_refreshes_and_writes_back(self):
        def ok(token):
            return {"five_hour": {"utilization": 5}, "seven_day": {"utilization": 9}}
        result = self.sync(CFG_ON, 0, ok)
        self.assertEqual(result["usage"]["weeklyPercent"], 9)
        self.post.assert_called_once()
        self.keychain_write.assert_called_once()
        saved = json.loads(self.keychain_write.call_args[0][0])
        self.assertEqual(saved["claudeAiOauth"]["accessToken"], NEW)

    def test_flag_must_be_exactly_true(self):
        for value in ("true", 1, None):
            cfg = {"projects": [], "usage": {"usageTokenRefresh": value}}
            self.assertFalse(uc.token_refresh_allowed(cfg), value)
        self.assertFalse(uc.token_refresh_allowed(CFG_OFF))
        self.assertTrue(uc.token_refresh_allowed(CFG_ON))


if __name__ == "__main__":
    unittest.main()
