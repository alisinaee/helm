"""GET /api/v1/log/report (R7.16 step 2b): the plain-text debug report for the Copy button. Localhost only (Host check,
phone refusal), n capped 1..100 with no other query accepted, the 6 KB cap, the redaction (no absolute path, no
token in any line) and the short report for an empty log."""

import os
import threading
import unittest
from unittest import mock

from roadmap import log as rlog
from roadmap.http import routes, security
from roadmap.http import server as http_server
from tests.api.support import ServerCase

PHONE_TOKEN = "FAKE-PHONE-TOKEN-report-0123456789abcdefghijklmnopqrstuvwxyzABCDEFG"
HINT = "next: roadmap logs --session last"
FAKE_PATH = "/opt/private-tree/billing/app.js"
FAKE_TOKEN = "SECRETTOKEN999"


def warn(msg, ev="core.exc", src="core", lvl="WARN", **extra):
    return rlog.debug_event(src, lvl, ev, msg=msg, route=extra.get("route", "/api/v1/cmd"))


class LogReport(ServerCase):
    def report(self, query="", **kwargs):
        target = "/api/v1/log/report" + ("?" + query if query else "")
        return self.request("GET", target, **kwargs)

    def lines(self, res):
        return res.body.decode("utf-8").splitlines()

    def test_empty_log_gives_a_short_no_events_report_with_the_hint(self):
        res = self.report()
        self.assertEqual(res.status, 200)
        self.assertEqual(res.header("content-type"), "text/plain; charset=utf-8")
        self.assertEqual(res.header("cache-control"), "no-store")
        body = res.body.decode("utf-8")
        self.assertIn("no events", body)
        self.assertEqual(self.lines(res)[-1], HINT)
        self.assertTrue(self.lines(res)[0].startswith("roadmap "))
        self.assertLess(len(res.body), 1024)

    def test_header_has_versions_and_no_path_or_user_name(self):
        with mock.patch.dict(os.environ, {"ROADMAP_PROJECT": "splitnet"}):
            res = self.report()
        head = self.lines(res)[:5]
        self.assertEqual([line.split(" ", 1)[0] for line in head], ["roadmap", "project", "time", "python", "os"])
        self.assertIn("project splitnet", head[1])
        self.assertNotIn("/", "".join(head).replace("time ", "").replace("+", ""))

    def test_n_defaults_to_30_and_keeps_the_newest_warnings(self):
        for i in range(40):
            warn("w%02d" % i)
        event_lines = [line for line in self.lines(self.report()) if " core.exc " in line]
        self.assertEqual(len(event_lines), 30)
        self.assertTrue(event_lines[-1].endswith(" w39"))

    def test_n_is_read_and_capped_between_1_and_100(self):
        for i in range(120):
            warn("n%03d" % i)
        self.assertEqual(len([line for line in self.lines(self.report("n=2")) if " core.exc " in line]), 2)
        self.assertEqual(len([line for line in self.lines(self.report("n=0")) if " core.exc " in line]), 1)
        big = [line for line in self.lines(self.report("n=500")) if " core.exc " in line]
        self.assertLessEqual(len(big), 100)

    def test_other_queries_and_bad_n_are_400(self):
        for query in ("n=abc", "n=", "x=1", "n=5&x=1", "n=5&n=6", "n=-3", "n=1.5"):
            res = self.report(query)
            self.assertEqual(res.status, 400, query)
            self.assertEqual(res.json()["error"]["code"], "invalid_input")

    def test_body_is_capped_at_6_kb_and_keeps_the_hint(self):
        for i in range(100):
            warn("long message %03d " % i + "x" * 300, route="/api/v1/projects/splitnet/snapshot")
        res = self.report("n=100")
        self.assertEqual(res.status, 200)
        self.assertLessEqual(len(res.body), 6 * 1024)
        self.assertEqual(self.lines(res)[-1], HINT)
        self.assertIn("older lines cut", res.body.decode("utf-8"))

    def test_ui_mark_events_are_the_last_five_and_not_repeated(self):
        for i in range(7):
            rlog.debug_event("ui", "INFO", "ui.mark", msg="mark%d" % i, route="#/tasks")
        warn("a real warning")
        body = self.report().body.decode("utf-8")
        self.assertNotIn("mark0", body)
        self.assertNotIn("mark1", body)
        for i in range(2, 7):
            self.assertIn("mark%d" % i, body)
        self.assertEqual(body.count("a real warning"), 1)

    def test_line_shape_is_time_src_ev_route_ref_msg(self):
        rlog.debug_event("ui", "ERROR", "ui.error", msg="it broke", route="#/tasks", ref="rb:splitnet/task/T1")
        line = [entry for entry in self.lines(self.report()) if " ui.error " in entry][0]
        clock, src, ev, route, ref, msg = line.split(" ", 5)
        self.assertRegex(clock, r"^\d{2}:\d{2}:\d{2}$")
        self.assertEqual((src, ev, route, ref, msg), ("ui", "ui.error", "#/tasks", "rb:splitnet/task/T1", "it broke"))

    def test_paths_and_tokens_in_messages_never_appear(self):
        warn("failed at %s with Bearer %s" % (FAKE_PATH, FAKE_TOKEN))
        warn("key sk-ant-%s and k=%s" % (FAKE_TOKEN, FAKE_TOKEN), ev="core.exc")
        body = self.report().body.decode("utf-8")
        self.assertNotIn(FAKE_TOKEN, body)
        self.assertNotIn("/opt/private-tree", body)
        self.assertIn("app.js", body)

    def test_message_is_capped_at_160_characters(self):
        warn("m" * 400)
        line = [entry for entry in self.lines(self.report()) if " core.exc " in entry][0]
        self.assertLessEqual(len(line.split(" ", 5)[5]), 160)

    def test_host_check_applies_and_post_is_405(self):
        self.assertEqual(self.report(host="evil.example:%d" % self.port).status, 421)
        self.assertEqual(self.request("POST", "/api/v1/log/report", headers=self.write_headers(), body=b"{}").status,
                         405)

    def test_route_template_is_the_plain_path(self):
        self.assertEqual(routes.route_template("/api/v1/log/report"), "/api/v1/log/report")


class PhoneRefusesReport(ServerCase):
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

    def test_phone_refuses_the_report_even_with_a_valid_cookie(self):
        cookie = {"Cookie": "%s=%s" % (security.PHONE_COOKIE, security.cookie_value(PHONE_TOKEN))}
        res = self.request("GET", "/api/v1/log/report", headers=cookie, port=self.phone_port)
        self.assertEqual(res.status, 403)


if __name__ == "__main__":
    unittest.main()
