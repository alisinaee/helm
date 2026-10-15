"""POST /api/v1/log and GET /api/v1/log/status (R7.16 step 2), and the core emitters (core.api, core.guard, core.exc,
core.start, core.stop). Guard refusals (403, 415), the body cap (413), the rate limits (429), the batch cap (400), the
phone refusal (403), the closed event list, the no-echo rule and the fail-open rule (an unwritable log directory)."""

import json
import os
import shutil
import threading
import unittest

from roadmap import log as rlog
from roadmap.http import routes, security
from roadmap.http import server as http_server
from tests.api.support import FakeSync, ServerCase

PHONE_TOKEN = "FAKE-PHONE-TOKEN-log-0123456789abcdefghijklmnopqrstuvwxyz"
SID = "a1b2c3d4"
SECRET = "SECRET-VALUE-456"


def batch(events, sid=SID):
    return json.dumps({"sid": sid, "events": events}).encode("utf-8")


def ui_error(msg="boom", **extra):
    event = {"ev": "ui.error", "lvl": "ERROR", "msg": msg, "route": "#/tasks", "ref": "rb:splitnet/task/T1",
             "data": {"file": "app.js:3", "stack": "a\nb"}}
    event.update(extra)
    return event


class LogRoute(ServerCase):
    def post(self, body, headers=None, **kwargs):
        return self.request("POST", "/api/v1/log", headers=headers or self.write_headers(), body=body, **kwargs)

    def ui_events(self):
        return rlog.read_events(src="ui")

    def core_events(self, ev):
        return rlog.read_events(src="core", ev=ev)

    def test_start_event_is_written_when_the_server_starts(self):
        self.assertTrue(self.core_events("core.start"))
        self.assertEqual(self.core_events("core.start")[-1]["data"]["port"], self.port)

    def test_valid_batch_is_204_with_no_body_and_writes_ui_events(self):
        res = self.post(batch([ui_error()]))
        self.assertEqual(res.status, 204)
        self.assertEqual(res.body, b"")
        events = self.ui_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ev"], "ui.error")
        self.assertEqual(events[0]["src"], "ui")
        self.assertEqual(events[0]["sid"], SID)
        self.assertEqual(events[0]["ref"], "rb:splitnet/task/T1")

    def test_query_string_in_route_never_reaches_the_log(self):
        self.post(batch([ui_error(route="#/tasks?k=" + SECRET)]))
        self.assertNotIn(SECRET, json.dumps(self.ui_events()))

    def test_unknown_names_and_non_ui_names_are_dropped_silently(self):
        res = self.post(batch([{"ev": "ui.bogus", "lvl": "ERROR", "msg": "x"},
                               {"ev": "core.exc", "lvl": "ERROR", "msg": "forged"},
                               {"ev": "hook.error", "lvl": "ERROR", "msg": "forged"},
                               "not an object",
                               ui_error(msg="kept")]))
        self.assertEqual(res.status, 204)
        self.assertEqual([e["msg"] for e in self.ui_events()], ["kept"])
        self.assertEqual(self.core_events("core.exc"), [])

    def test_the_client_cannot_choose_the_source(self):
        self.post(batch([ui_error(src="core")]))
        self.assertEqual(self.ui_events()[0]["src"], "ui")

    def test_reply_never_echoes_the_logged_content(self):
        res = self.post(batch([ui_error(msg="visible " + SECRET)]))
        self.assertEqual(res.status, 204)
        self.assertNotIn(SECRET.encode("utf-8"), res.body)
        self.assertIsNone(res.header("content-length"))

    def test_guard_refusals_are_403_and_recorded_by_reason_only(self):
        cases = {
            "csrf": self.write_headers(**{"X-Roadmap-CSRF": "wrong"}),
            "origin": self.write_headers(**{"Sec-Fetch-Site": "cross-site"}),
            "no_headers": {"Content-Type": "application/json"},
        }
        for reason, headers in cases.items():
            res = self.post(batch([ui_error()]), headers=headers)
            self.assertEqual(res.status, 403, reason)
            self.assertEqual(res.json()["error"]["code"], "forbidden")
        reasons = [e["data"]["reason"] for e in self.core_events("core.guard") if e["route"] == "/api/v1/log"]
        self.assertEqual(sorted(reasons), ["csrf", "origin", "origin"])
        self.assertEqual(self.ui_events(), [])

    def test_wrong_content_type_is_415(self):
        res = self.post(batch([ui_error()]), headers=self.write_headers(**{"Content-Type": "text/plain"}))
        self.assertEqual(res.status, 415)
        self.assertEqual(self.core_events("core.guard")[-1]["data"]["reason"], "ctype")

    def test_body_over_16_kb_is_413(self):
        big = batch([ui_error(msg="x" * 200)] * 50)
        big = big + b" " * (security.LOG_BODY_BYTES + 1 - len(big))
        self.assertGreater(len(big), security.LOG_BODY_BYTES)
        res = self.post(big)
        self.assertEqual(res.status, 413)
        self.assertEqual(self.core_events("core.guard")[-1]["data"]["reason"], "body_cap")
        self.assertEqual(self.ui_events(), [])

    def test_bad_shapes_are_400(self):
        bodies = [
            b"not json",
            b"[]",
            json.dumps({"sid": "zzz", "events": []}).encode(),
            json.dumps({"sid": SID, "events": "nope"}).encode(),
            json.dumps({"sid": SID, "events": [ui_error()] * 51}).encode(),
        ]
        for body in bodies:
            res = self.post(body)
            self.assertEqual(res.status, 400, body[:30])
            self.assertEqual(res.json()["error"]["code"], "invalid_input")
        self.assertEqual(self.ui_events(), [])

    def test_fifty_events_is_the_most_in_one_batch(self):
        res = self.post(batch([ui_error(msg="n%d" % i) for i in range(50)]))
        self.assertEqual(res.status, 204)
        self.assertEqual(len(self.ui_events()), 50)

    def test_request_rate_is_429_with_retry_after(self):
        self.httpd.app.log_requests = security.RateLimiter(2, 60.0)
        self.assertEqual(self.post(batch([])).status, 204)
        self.assertEqual(self.post(batch([])).status, 204)
        res = self.post(batch([ui_error()]))
        self.assertEqual(res.status, 429)
        self.assertEqual(res.header("retry-after"), "1")
        self.assertEqual(self.ui_events(), [])

    def test_event_rate_is_429_per_event_not_per_request(self):
        self.httpd.app.log_events = security.EventBudget(limit=3, window_s=60.0)
        self.assertEqual(self.post(batch([ui_error()] * 2)).status, 204)
        res = self.post(batch([ui_error()] * 2))
        self.assertEqual(res.status, 429)
        self.assertEqual(res.header("retry-after"), "60")
        self.assertEqual(len(self.ui_events()), 2)

    def test_status_returns_only_enabled_bytes_and_file_count(self):
        self.post(batch([ui_error()]))
        res = self.request("GET", "/api/v1/log/status")
        self.assertEqual(res.status, 200)
        body = res.json()
        self.assertEqual(sorted(body), ["bytes", "enabled", "files"])
        self.assertIs(body["enabled"], True)
        self.assertGreater(body["bytes"], 0)
        self.assertGreaterEqual(body["files"], 1)
        self.assertNotIn("debug.jsonl", res.body.decode("utf-8"))

    def test_status_is_get_only_and_post_to_it_is_405(self):
        res = self.request("POST", "/api/v1/log/status", headers=self.write_headers(), body=b"{}")
        self.assertEqual(res.status, 405)

    def test_host_check_still_applies(self):
        res = self.post(batch([]), host="evil.example:%d" % self.port)
        self.assertEqual(res.status, 421)

    def test_unwritable_log_directory_never_breaks_a_request(self):
        logs = os.path.join(os.environ["ROADMAP_HOME"], "state", "logs")
        shutil.rmtree(logs, ignore_errors=True)  # the start event already made it; put a file in its place
        with open(logs, "w", encoding="utf-8") as fh:  # a file where the logs folder should be
            fh.write("in the way\n")
        res = self.post(batch([ui_error()]))
        self.assertEqual(res.status, 204)
        self.assertEqual(self.request("GET", "/api/v1/health").status, 200)
        self.assertEqual(self.request("GET", "/api/v1/log/status").status, 200)

    def test_route_template_names_the_parts_and_drops_the_ids(self):
        self.assertEqual(routes.route_template("/api/v1/projects/splitnet/snapshot"),
                         "/api/v1/projects/{pid}/snapshot")
        self.assertEqual(routes.route_template("/api/v1/log"), "/api/v1/log")
        self.assertEqual(routes.route_template("/data.json"), "/data.json")
        self.assertEqual(routes.route_template("/api/v1/nope"), "unmatched")


class LogEmitters(ServerCase):
    def test_a_500_writes_core_exc_with_type_and_frames_and_core_api_error(self):
        self.httpd.app._sync = FakeSync(error=RuntimeError("boom " + "x" * 400))
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"{}")
        self.assertEqual(res.status, 500)
        exc = rlog.read_events(src="core", ev="core.exc")
        self.assertEqual(len(exc), 1)
        self.assertEqual(exc[0]["data"]["type"], "RuntimeError")
        self.assertIn("stack", exc[0]["data"])
        self.assertLessEqual(len(exc[0]["data"]["message"]), 200)
        api = [e for e in rlog.read_events(src="core", ev="core.api") if e["data"]["status"] == 500]
        self.assertEqual(api[0]["lvl"], "ERROR")
        self.assertEqual(api[0]["route"], "/api/v1/usage/sync")
        self.assertEqual(api[0]["data"]["method"], "POST")

    def test_fast_successful_calls_are_not_logged(self):
        self.request("GET", "/api/v1/health")
        self.assertEqual([e for e in rlog.read_events(src="core", ev="core.api")
                          if e["route"] == "/api/v1/health"], [])

    def test_slow_calls_are_logged_as_warn_without_the_query(self):
        original = http_server._api_event
        calls = []

        def slow(method, path, status, elapsed_ms):
            calls.append((method, path, status))
            original(method, path, status, 1500)

        http_server._api_event = slow
        try:
            self.request("GET", "/api/v1/projects/splitnet/snapshot?k=" + SECRET)
        finally:
            http_server._api_event = original
        slow_rows = [e for e in rlog.read_events(src="core", ev="core.api") if e["lvl"] == "WARN"]
        self.assertEqual(slow_rows[-1]["route"], "/api/v1/projects/{pid}/snapshot")
        self.assertNotIn(SECRET, json.dumps(slow_rows))

    def test_guard_refusal_of_a_write_is_recorded(self):
        self.request("POST", "/api/v1/usage/sync", headers={"Content-Type": "application/json"}, body=b"{}")
        rows = rlog.read_events(src="core", ev="core.guard")
        self.assertEqual(rows[-1]["data"], {"reason": "origin"})
        self.assertEqual(rows[-1]["lvl"], "WARN")


class PhoneRefusesLog(ServerCase):
    def setUp(self):
        super().setUp()
        httpd = http_server.make_phone_server(0, token_source=lambda: PHONE_TOKEN, tunnel_host=lambda: None,
                                              web_root=self.web)
        thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)

        self.addCleanup(stop)
        self.phone_port = httpd.server_address[1]

    def test_phone_refuses_post_and_status_even_with_a_valid_cookie(self):
        cookie = {"Cookie": "%s=%s" % (security.PHONE_COOKIE, security.cookie_value(PHONE_TOKEN))}
        post = self.request("POST", "/api/v1/log", headers=dict(cookie, **{"Content-Type": "application/json"}),
                            body=batch([ui_error()]), port=self.phone_port)
        status = self.request("GET", "/api/v1/log/status", headers=cookie, port=self.phone_port)
        self.assertEqual(post.status, 403)
        self.assertEqual(status.status, 403)
        self.assertEqual(rlog.read_events(src="ui"), [])


if __name__ == "__main__":
    unittest.main()


class GuardLineBudgetTests(ServerCase):
    """core.guard lines share a per-minute budget, so a flood of refused writes cannot fill the debug log."""

    def test_refused_writes_past_the_guard_budget_write_no_more_guard_lines(self):
        self.httpd.app.guard_lines = security.EventBudget(limit=2, window_s=60.0)
        cross = self.write_headers(**{"Sec-Fetch-Site": "cross-site"})
        for _ in range(5):
            res = self.request("POST", "/api/v1/log", headers=cross, body=batch([ui_error()]))
            self.assertEqual(res.status, 403)
        rows = [e for e in rlog.read_events(src="core", ev="core.guard") if e["route"] == "/api/v1/log"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rlog.read_events(src="ui"), [])
