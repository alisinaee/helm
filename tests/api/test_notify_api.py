"""R11.163 notification settings over HTTP: GET the switches, a proven POST changes the master switch or one kind,
the test button sends one notification (replaced here), an unknown kind is a 4xx. Temp ROADMAP_HOME only."""

import json
import os
from unittest import mock

from roadmap.services import notify
from roadmap.store import config
from tests.api.support import ServerCase


class NotifyApi(ServerCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)

    def proven(self):
        headers = self.write_headers()
        headers["Origin"] = "http://127.0.0.1:%d" % self.port
        return headers

    def post(self, body, headers=None):
        return self.request("POST", "/api/v1/notify", headers=headers or self.proven(),
                            body=json.dumps(body).encode("utf-8"))

    def test_get_and_switches(self):
        got = self.request("GET", "/api/v1/notify")
        self.assertEqual(got.status, 200)
        self.assertTrue(got.json()["enabled"])
        res = self.post({"kind": "limit", "on": False})
        self.assertEqual(res.status, 200, res.body[:200])
        self.assertEqual([k["on"] for k in res.json()["kinds"] if k["id"] == "limit"], [False])
        self.assertEqual(config.load()["notifyKinds"], {"limit": False})
        res = self.post({"enabled": False})
        self.assertFalse(res.json()["enabled"])
        self.assertIs(config.load()["notify"], False)

    def test_test_button_only_when_enabled(self):
        with mock.patch.object(notify, "send_test", return_value=True) as sent:
            self.assertTrue(self.post({"test": True}).json()["shown"])
            self.post({"enabled": False})
            self.assertFalse(self.post({"test": True}).json()["shown"])
        self.assertEqual(sent.call_count, 1)

    def test_bad_bodies_and_agent_writes_are_refused(self):
        self.assertEqual(self.post({"kind": "nope", "on": True}).status, 400)
        self.assertEqual(self.post({"x": 1}).status, 400)
        self.assertEqual(self.post({"enabled": False}, headers=self.write_headers()).status, 403)
