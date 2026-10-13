"""Collector tests, ported from tools/roadmap-web/test_usage_collector.py. Fakes only: no keychain, no network.

The route tests of the old file (POST /api/usage/sync through a server) belong to the HTTP package (WP5).
Their behaviours at service level are in test_usage_store.py.
"""

import contextlib
import io
import json
import subprocess
import unittest
import urllib.error
from unittest import mock

from roadmap.services import usage as uc

FAKE_TOKEN = "sk-ant-oat01-FAKE-TOKEN-DO-NOT-LEAK"

GOOD_REPLY = {
    "five_hour": {"utilization": 17, "resets_at": "2026-10-13T16:50:00+00:00"},
    "seven_day": {"utilization": 62.4, "resets_at": "2026-10-16T08:00:00+00:00"},
}


class ParseTests(unittest.TestCase):
    def test_utilization_variant(self):
        r = uc.parse_usage(GOOD_REPLY)
        self.assertEqual(r["weeklyPercent"], 62.4)
        self.assertEqual(r["fiveHourPercent"], 17)
        self.assertEqual(r["weeklyResetsAt"], "2026-10-16T08:00:00+00:00")
        self.assertEqual(r["fiveHourResetsAt"], "2026-10-13T16:50:00+00:00")

    def test_percent_used_variant(self):
        r = uc.parse_usage({"five_hour": {"percent_used": 5}, "seven_day": {"percent_used": 40.0}})
        self.assertEqual((r["fiveHourPercent"], r["weeklyPercent"]), (5, 40))

    def test_missing_resets_is_none(self):
        r = uc.parse_usage({"five_hour": {"utilization": 1}, "seven_day": {"utilization": 2}})
        self.assertIsNone(r["weeklyResetsAt"])
        self.assertIsNone(r["fiveHourResetsAt"])

    def test_epoch_resets_converted_to_iso_with_offset(self):
        r = uc.parse_usage({"five_hour": {"utilization": 1, "resets_at": 1792000000},
                            "seven_day": {"utilization": 2, "resets_at": 1792000000}})
        self.assertRegex(r["weeklyResetsAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

    def test_out_of_range_percent_rejected(self):
        with self.assertRaises(uc.UsageError):
            uc.parse_usage({"five_hour": {"utilization": 150}, "seven_day": {"utilization": 1}})

    def test_missing_window_rejected(self):
        with self.assertRaisesRegex(uc.UsageError, "5-hour"):
            uc.parse_usage({"seven_day": {"utilization": 1}})
        with self.assertRaisesRegex(uc.UsageError, "weekly"):
            uc.parse_usage({"five_hour": {"utilization": 1}})

    def test_wrong_shape_rejected(self):
        with self.assertRaises(uc.UsageError):
            uc.parse_usage(["not", "a", "dict"])


class KeychainTests(unittest.TestCase):
    def _run(self, returncode=0, stdout=""):
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")

    def test_token_read_from_json(self):
        body = json.dumps({"claudeAiOauth": {"accessToken": FAKE_TOKEN}})
        with mock.patch.object(uc.subprocess, "run", return_value=self._run(0, body)) as run:
            self.assertEqual(uc.read_keychain_token(), FAKE_TOKEN)
        args, kwargs = run.call_args
        self.assertEqual(args[0][:2], ["security", "find-generic-password"])
        self.assertNotIn("shell", kwargs)

    def test_item_not_found(self):
        with mock.patch.object(uc.subprocess, "run", return_value=self._run(44)):
            with self.assertRaisesRegex(uc.UsageError, "not found"):
                uc.read_keychain_token()

    def test_access_denied(self):
        with mock.patch.object(uc.subprocess, "run", return_value=self._run(128)):
            with self.assertRaisesRegex(uc.UsageError, "denied or failed"):
                uc.read_keychain_token()

    def test_bad_json_does_not_echo_data(self):
        body = '{"claudeAiOauth": "' + FAKE_TOKEN + '"'  # truncated JSON that contains the token
        with mock.patch.object(uc.subprocess, "run", return_value=self._run(0, body)):
            with self.assertRaises(uc.UsageError) as cm:
                uc.read_keychain_token()
        self.assertNotIn(FAKE_TOKEN, str(cm.exception))

    def test_missing_token_key(self):
        with mock.patch.object(uc.subprocess, "run", return_value=self._run(0, '{"other": 1}')):
            with self.assertRaisesRegex(uc.UsageError, "no usable token"):
                uc.read_keychain_token()


class FetchTests(unittest.TestCase):
    def test_request_headers_and_host(self):
        seen = {}

        def fake_open(req):
            seen["req"] = req
            return json.dumps(GOOD_REPLY).encode("utf-8")

        with mock.patch.object(uc, "_open", side_effect=fake_open):
            payload = uc.http_fetch(FAKE_TOKEN)
        req = seen["req"]
        self.assertEqual(payload["seven_day"]["utilization"], 62.4)
        self.assertEqual(req.full_url, "https://api.anthropic.com/api/oauth/usage")
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.get_header("Authorization"), "Bearer " + FAKE_TOKEN)
        self.assertEqual(req.get_header("Anthropic-beta"), "oauth-2025-04-20")
        self.assertEqual(req.get_header("User-agent"), "roadmap-dashboard")

    def test_http_error_mapped_without_token(self):
        err = urllib.error.HTTPError("https://api.anthropic.com/x", 401, "Unauthorized", {}, None)
        with mock.patch.object(uc, "_open", side_effect=err):
            with self.assertRaises(uc.UsageError) as cm:
                uc.http_fetch(FAKE_TOKEN)
        self.assertEqual(str(cm.exception), "usage endpoint answered HTTP 401")

    def test_timeout_and_network_errors(self):
        with mock.patch.object(uc, "_open", side_effect=TimeoutError("slow " + FAKE_TOKEN)):
            with self.assertRaisesRegex(uc.UsageError, "timed out") as cm:
                uc.http_fetch(FAKE_TOKEN)
        self.assertNotIn(FAKE_TOKEN, str(cm.exception))
        with mock.patch.object(uc, "_open", side_effect=urllib.error.URLError("no route " + FAKE_TOKEN)):
            with self.assertRaisesRegex(uc.UsageError, "not reachable") as cm:
                uc.http_fetch(FAKE_TOKEN)
        self.assertNotIn(FAKE_TOKEN, str(cm.exception))

    def test_bad_json_reply(self):
        with mock.patch.object(uc, "_open", return_value=b"<html>oops</html>"):
            with self.assertRaisesRegex(uc.UsageError, "not valid JSON"):
                uc.http_fetch(FAKE_TOKEN)


class CollectTests(unittest.TestCase):
    def test_collect_with_fakes(self):
        r = uc.collect(get_token=lambda: FAKE_TOKEN, fetch=lambda t: GOOD_REPLY)
        self.assertEqual(set(r), {"weeklyPercent", "fiveHourPercent", "weeklyResetsAt", "fiveHourResetsAt"})

    def test_fetch_receives_token(self):
        got = []
        uc.collect(get_token=lambda: FAKE_TOKEN, fetch=lambda t: got.append(t) or GOOD_REPLY)
        self.assertEqual(got, [FAKE_TOKEN])

    def test_unexpected_error_hides_message_and_token(self):
        def bad_token():
            raise RuntimeError("boom " + FAKE_TOKEN)

        buf_out, buf_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            with self.assertRaises(uc.UsageError) as cm:
                uc.collect(get_token=bad_token, fetch=lambda t: GOOD_REPLY)
        self.assertEqual(str(cm.exception), "unexpected failure (RuntimeError)")
        self.assertNotIn(FAKE_TOKEN, str(cm.exception))
        self.assertNotIn(FAKE_TOKEN, buf_out.getvalue() + buf_err.getvalue())

    def test_usage_error_from_fetch_passes_through(self):
        def fetch(t):
            raise uc.UsageError("usage endpoint answered HTTP 500")

        with self.assertRaisesRegex(uc.UsageError, "HTTP 500"):
            uc.collect(get_token=lambda: FAKE_TOKEN, fetch=fetch)

    def test_usage_record_has_offset(self):
        rec = uc.usage_record(uc.parse_usage(GOOD_REPLY), "src")
        self.assertEqual(rec["source"], "src")
        self.assertRegex(rec["updated"], r"[+-]\d{2}:\d{2}$")


class WaitTests(unittest.TestCase):
    def test_backoff_after_three_failures(self):
        self.assertEqual(uc.usage_wait_s(0), 120)
        self.assertEqual(uc.usage_wait_s(2), 120)
        self.assertEqual(uc.usage_wait_s(3), 600)


if __name__ == "__main__":
    unittest.main()
