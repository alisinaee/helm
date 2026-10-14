"""Flow 5: the HTTP security rules over real sockets. The main listener refuses a foreign Host (421), a write without
the page's CSRF token (403), a cross-site write (403), a body over 4 KB (413), an unknown op (404) and a burst over the
rate limit (429). The research notes route refuses traversal. The phone listener is read-only (405) and answers 503
when there is no token. Phone listener is built in-process with make_phone_server on port 0, with fake token sources."""

import json
import os
import threading
import unittest
from urllib import error, request
from unittest import mock

from roadmap.http.server import make_phone_server
from tests.integration.harness import Sandbox, stack

NOTE = "# Landscape\n\nThe short version.\n"


class MainListenerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.sandbox, self.server = stack(self)
        self.pid = self.sandbox.pid
        self.body = {"op": "comment.add", "args": {"on": "P0.1", "text": "hello", "by": "gui"}}

    def test_a_foreign_host_is_misdirected_and_loopback_names_are_served(self):
        status, _, body = self.server.request("GET", "/api/v1/projects", host="evil.example:%d" % self.server.port)
        self.assertEqual(status, 421)
        self.assertEqual(json.loads(body)["error"]["code"], "misdirected_request")
        status, _, _ = self.server.request("GET", "/api/v1/projects", host="localhost:%d" % self.server.port)
        self.assertEqual(status, 200)

    def test_a_write_without_the_csrf_token_is_forbidden(self):
        headers = self.server.write_headers(**{"X-Roadmap-CSRF": None})
        status, _, body = self.server.request("POST", "/api/v1/cmd", self.body, headers)
        self.assertEqual((status, json.loads(body)["error"]["code"]), (403, "forbidden"))

    def test_a_cross_site_or_foreign_origin_write_is_forbidden_even_with_the_token(self):
        status, _, _ = self.server.request("POST", "/api/v1/cmd", self.body,
                                           self.server.write_headers(**{"Sec-Fetch-Site": "cross-site"}))
        self.assertEqual(status, 403)
        status, _, _ = self.server.request("POST", "/api/v1/cmd", self.body,
                                           self.server.write_headers(Origin="http://evil.example"))
        self.assertEqual(status, 403)
        # the same write from the page's own origin goes through, so the refusals above are the rules at work
        self.assertTrue(self.server.cmd("comment.add", self.body["args"])["ok"])

    def test_a_body_over_4_kb_is_too_large(self):
        big = {"op": "comment.add", "args": {"on": "P0.1", "text": "x" * 5000, "by": "gui"}}
        status, _, body = self.server.request("POST", "/api/v1/cmd", big, self.server.write_headers())
        self.assertEqual((status, json.loads(body)["error"]["code"]), (413, "too_large"))

    def test_an_unknown_op_is_404_unknown_op(self):
        status, _, body = self.server.request("POST", "/api/v1/cmd", {"op": "no.such.op", "args": {}},
                                              self.server.write_headers())
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"]["code"], "unknown_op")

    def test_a_burst_of_writes_gets_429_after_the_limit(self):
        statuses = []
        for _ in range(12):
            status, _, _ = self.server.request("POST", "/api/v1/cmd", {"op": "undo", "args": {"activity": "bad"}},
                                               self.server.write_headers())
            statuses.append(status)
        self.assertIn(429, statuses)
        self.assertEqual(statuses[:10], [422] * 10)

    def test_notes_refuse_traversal_and_never_follow_a_symlink(self):
        research = os.path.join(self.sandbox.data_dir, "research")
        os.makedirs(research)
        with open(os.path.join(research, "01-landscape.md"), "w", encoding="utf-8") as fh:
            fh.write(NOTE)
        secret = os.path.join(self.sandbox.root, "secret.md")
        with open(secret, "w", encoding="utf-8") as fh:
            fh.write("# Secret\n")
        os.symlink(secret, os.path.join(research, "02-link.md"))

        base = "/api/v1/projects/%s/notes" % self.pid
        status, headers, body = self.server.request("GET", base + "/01-landscape.md")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        self.assertEqual(body.decode("utf-8"), NOTE)

        for path in (base + "/../../../../secret.md", base + "/..%2F..%2Fsecret.md", base + "/%2e%2e%2fsecret.md",
                     base + "/..", base + "/02-link.md", base + "/..%2F01-landscape.md"):
            status, _, _ = self.server.request("GET", path)
            self.assertIn(status, (400, 404), path)
        status, _, body = self.server.request("GET", base)
        names = [row["name"] for row in json.loads(body)["notes"]]
        self.assertEqual(names, ["01-landscape.md"])  # the symlink is not listed as a note


class PhoneListenerTests(unittest.TestCase):
    """The phone listener built in-process on port 0 with fake token sources. Its config reads come from a temp home."""

    def setUp(self):
        self.sandbox = Sandbox(self)
        self.env = mock.patch.dict(os.environ, {"ROADMAP_HOME": self.sandbox.home, "HOME": self.sandbox.user_home})
        self.env.start()
        self.addCleanup(self.env.stop)

    def start_phone(self, token):
        phone = make_phone_server(port=0, token_source=lambda: token, tunnel_host=lambda: None)
        self.addCleanup(phone.server_close)
        thread = threading.Thread(target=phone.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        self.addCleanup(lambda: (phone.shutdown(), thread.join(5)))
        return phone, "http://127.0.0.1:%d" % phone.server_address[1]

    def request(self, base, method, path, headers=None):
        """The status of one request to the phone listener (error statuses are returned, not raised)."""
        req = request.Request(base + path, data=b"{}" if method == "POST" else None, method=method)
        for name, value in (headers or {}).items():
            req.add_header(name, value)
        try:
            resp = request.urlopen(req, timeout=10)
            return resp.status
        except error.HTTPError as exc:
            return exc.code

    def test_the_phone_listener_is_read_only_and_needs_a_token(self):
        _, base = self.start_phone("phone-test-token")
        self.assertEqual(self.request(base, "POST", "/api/v1/usage/sync"), 405)
        self.assertEqual(self.request(base, "POST", "/"), 405)
        self.assertEqual(self.request(base, "GET", "/"), 401)  # a token exists, but no link or cookie came with it

    def test_without_a_phone_token_the_phone_listener_answers_503(self):
        _, base = self.start_phone(None)
        self.assertEqual(self.request(base, "GET", "/"), 503)
        self.assertEqual(self.request(base, "GET", "/api/v1/projects"), 503)


if __name__ == "__main__":
    unittest.main()
