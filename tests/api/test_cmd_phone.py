"""POST /api/v1/cmd on the phone listener: refused (403) by default; with phoneWrites true only the phone allowlist
runs, with the cookie and the phone's own csrf value (from the cookie-authenticated /api/v1/meta). Resuming, raising
limits and undoing into a resume are never allowed over the phone."""

import json
import os
from unittest import mock

from roadmap.http import security
from roadmap.services import tasks
from roadmap.store import config as config_store
from tests.api import test_security_phone as phone_tests
from tests.api.support import PROJECT_ID


class PhoneCmd(phone_tests.PhoneCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def set_phone_writes(self, value):
        config_store._update(lambda cfg: cfg.update(phoneWrites=value))

    def cookie_headers(self):
        return {"Cookie": "%s=%s" % (security.PHONE_COOKIE, self.good_cookie()), "Sec-Fetch-Site": "same-origin",
                "Content-Type": "application/json"}

    def phone_csrf(self):
        res = self.phone_get("/api/v1/meta", cookie=self.good_cookie())
        return res.json()["csrf"]

    def post(self, body, csrf=None, extra=None):
        headers = self.cookie_headers()
        headers["X-Roadmap-CSRF"] = self.phone_csrf() if csrf is None else csrf
        headers.update(extra or {})
        return self.request("POST", "/api/v1/cmd", headers=headers, body=json.dumps(body).encode("utf-8"),
                            port=self.phone_port)


class PhoneOff(PhoneCmd):
    def test_cmd_is_403_by_default_even_with_cookie_and_csrf(self):
        res = self.post({"op": "control.stop", "args": {}})
        self.assertEqual(res.status, 403)
        self.assertEqual(res.json()["error"]["code"], "forbidden")

    def test_the_phone_csrf_is_not_the_main_token(self):
        self.assertNotEqual(self.phone_csrf(), self.token)


class PhoneAllowlist(PhoneCmd):
    def setUp(self):
        super().setUp()
        self.set_phone_writes(True)

    def test_allowed_op_runs(self):
        res = self.post({"op": "task.status", "args": {"id": "P1.1", "status": "done"}})
        self.assertEqual(res.status, 200)
        self.assertEqual(tasks.get(self.data_dir, "P1.1")["status"], "done")

    def test_control_stop_is_allowed(self):
        self.assertEqual(self.post({"op": "control.stop", "args": {}}).status, 200)

    def test_resume_and_limit_raises_are_refused(self):
        self.assertEqual(self.post({"op": "control.resume", "args": {}}).status, 403)
        self.assertEqual(self.post({"op": "limit.set", "args": {"pct": 50}}).status, 403)
        self.assertEqual(self.post({"op": "budget.set", "args": {"scope": "project", "value": 5}}).status, 403)

    def test_undo_that_would_resume_is_refused(self):
        stopped = self.post({"op": "control.stop", "args": {}}).json()
        res = self.post({"op": "undo", "args": {"activity": stopped["activity"]}})
        self.assertEqual(res.status, 403)
        snap = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID).json()
        self.assertTrue(snap["control"]["stopped"])

    def test_wrong_phone_csrf_is_403(self):
        self.assertEqual(self.post({"op": "control.stop", "args": {}}, csrf="nope").status, 403)

    def test_without_the_cookie_is_401(self):
        headers = {"X-Roadmap-CSRF": self.phone_csrf(), "Sec-Fetch-Site": "same-origin",
                   "Content-Type": "application/json"}
        res = self.request("POST", "/api/v1/cmd", headers=headers, body=b'{"op":"control.stop","args":{}}',
                           port=self.phone_port)
        self.assertEqual(res.status, 401)
