"""R11.126 limits over HTTP: GET both windows, a proven POST sets one and writes a panel line, an agent write is
refused, a bad value is a 4xx. Temp ROADMAP_HOME and a port-0 server only."""

import json
import os
from unittest import mock

from roadmap.services import headpanel, limits_v2, tasks
from tests.api.support import PROJECT_ID, ServerCase


class LimitsV2Api(ServerCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def proven(self):
        headers = self.write_headers()
        headers["Origin"] = "http://127.0.0.1:%d" % self.port
        return headers

    def put(self, body, headers=None):
        return self.request("PUT", "/api/v1/limits", headers=headers or self.proven(),
                            body=json.dumps(body).encode("utf-8"))

    def test_get_set_and_panel_line(self):
        got = self.request("GET", "/api/v1/limits")
        self.assertEqual(got.status, 200)
        self.assertEqual(set(got.json()["windows"]), {"five_hour", "week"})
        res = self.put({"window": "five_hour", "on": True, "mode": "cap", "value": 35})
        self.assertEqual(res.status, 200, res.body[:200])
        body = res.json()
        self.assertEqual(body["windows"]["five_hour"]["stop"], 35)
        self.assertEqual(body["panel"]["id"], "P1")
        self.assertIn("5 hours stop at 35%", headpanel.read(self.data_dir)[0]["sum"])
        self.assertEqual(limits_v2.load()["five_hour"]["value"], 35)

    def test_an_agent_write_is_refused_and_not_recorded(self):
        res = self.put({"window": "week", "on": True, "mode": "cap", "value": 90}, headers=self.write_headers())
        self.assertEqual(res.status, 403)
        self.assertEqual(headpanel.read(self.data_dir), [])
        self.assertFalse(limits_v2.load()["week"]["on"])

    def test_a_bad_value_is_rejected(self):
        res = self.put({"window": "week", "value": 500})
        self.assertGreaterEqual(res.status, 400)
        self.assertLess(res.status, 500)
