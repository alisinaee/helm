"""The access log: method, path without the query string, status and milliseconds. A query string (even one with a
secret in it) must never reach the log."""

import re
import time

from tests.api.support import PROJECT_ID, ServerCase

SECRET = "SECRET-VALUE-123"


class AccessLog(ServerCase):
    def test_line_has_method_path_status_and_ms_but_no_query(self):
        with self.assertLogs("roadmap.http.access", level="INFO") as logs:
            res = self.request("GET", "/api/v1/health?k=" + SECRET + "&x=1")
            # the server thread writes the access line after the response is sent: wait for it
            deadline = time.monotonic() + 2
            while not logs.records and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(res.status, 200)
        self.assertEqual(len(logs.records), 1)
        line = logs.records[0].getMessage()
        self.assertRegex(line, r"^GET /api/v1/health 200 \d+ms$")
        self.assertNotIn("?", line)
        self.assertNotIn("k=", line)
        self.assertNotIn(SECRET, line)

    def test_no_roadmap_log_line_has_a_query_string_or_the_secret(self):
        with self.assertLogs("roadmap", level="INFO") as logs:
            self.request("GET", "/api/v1/projects/%s/snapshot?k=%s" % (PROJECT_ID, SECRET))
            self.request("GET", "/data.json?k=" + SECRET)
            self.request("POST", "/api/v1/usage/sync?k=" + SECRET, headers=self.write_headers(), body=b"{}")
            self.request("GET", "/index.html?k=" + SECRET, host="evil.example:%d" % self.port)
            self.request("GET", "/nope?k=" + SECRET)
        text = "\n".join(r.getMessage() for r in logs.records)
        self.assertGreaterEqual(len(logs.records), 5)
        self.assertNotIn("?", text)
        self.assertNotIn("k=", text)
        self.assertNotIn(SECRET, text)

    def test_access_line_shape_for_every_status(self):
        with self.assertLogs("roadmap.http.access", level="INFO") as logs:
            self.request("GET", "/api/v1/health", host="evil.example:%d" % self.port)
            self.request("POST", "/api/v1/health")
        pattern = re.compile(r"^(GET|POST) /api/v1/health (421|405) \d+ms$")
        for record in logs.records:
            self.assertRegex(record.getMessage(), pattern)
