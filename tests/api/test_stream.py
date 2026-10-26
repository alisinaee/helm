"""GET /api/v1/stream (R7.82): Server-Sent Events of project revisions. Initial rev events, a new one after a write,
slot release on disconnect and 503 for the 9th stream."""

import http.client
import json
import os
import time

from tests.api.support import PROJECT_ID, ServerCase


class StreamCase(ServerCase):
    def open_stream(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=6)
        conn.request("GET", "/api/v1/stream", headers={"Host": "127.0.0.1:%d" % self.port})
        resp = conn.getresponse()
        self.addCleanup(conn.close)
        return conn, resp

    def read_event(self, resp):
        """The next `event: rev` as a dict, skipping comments."""
        name = None
        while True:
            line = resp.fp.readline().decode("utf-8").rstrip("\n")
            if not line and name is None:
                continue
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: ") and name == "rev":
                return json.loads(line[6:])
            elif line == "":
                name = None

    def test_initial_event_headers_and_change(self):
        conn, resp = self.open_stream()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(resp.getheader("Cache-Control"), "no-cache")
        first = self.read_event(resp)
        self.assertEqual(first["project"], PROJECT_ID)
        self.assertTrue(first["rev"])
        path = os.path.join(self.project_root, "docs", "jobs.json")
        stamp = time.time() + 5
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n")
        os.utime(path, (stamp, stamp))
        started = time.monotonic()
        second = self.read_event(resp)
        self.assertEqual(second["project"], PROJECT_ID)
        self.assertNotEqual(second["rev"], first["rev"])
        self.assertLess(time.monotonic() - started, 4)

    def test_ninth_stream_refused_and_disconnect_frees_slot(self):
        opened = [self.open_stream() for _ in range(8)]
        self.assertTrue(all(resp.status == 200 for _, resp in opened))
        res = self.request("GET", "/api/v1/stream")
        self.assertEqual(res.status, 503)
        self.assertIn("error", res.json())
        # other requests are still served while streams are open
        self.assertEqual(self.request("GET", "/api/v1/health").status, 200)
        conn, resp = opened[0]
        resp.close()
        conn.close()
        deadline = time.monotonic() + 5
        status = 503
        while status == 503 and time.monotonic() < deadline:
            time.sleep(0.2)
            conn2 = http.client.HTTPConnection("127.0.0.1", self.port, timeout=6)
            conn2.request("GET", "/api/v1/stream", headers={"Host": "127.0.0.1:%d" % self.port})
            r2 = conn2.getresponse()
            status = r2.status
            self.addCleanup(conn2.close)
        self.assertEqual(status, 200)
