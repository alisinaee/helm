"""POST /api/v1/cmd on the main listener: CSRF and origin (403), size (413), unknown op (404), invalid args (422),
rate limit (429), a valid round trip reflected by the CLI, undo, and the snapshot control key after control.stop."""

import json
import os
import subprocess
import sys
from unittest import mock

from roadmap.services import tasks
from roadmap.store import config as config_store
from tests.api.support import PROJECT_ID, REPO, ServerCase


class CmdCase(ServerCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)  # the test runs from an agent shell too; gui calls must not be refused
        self.data_dir = tasks.resolve(PROJECT_ID)[1]
        self.start_status = tasks.get(self.data_dir, "P1.1")["status"]

    def post(self, body, headers=None, raw=None):
        payload = raw if raw is not None else json.dumps(body).encode("utf-8")
        sent = self.write_headers()
        sent["Origin"] = "http://127.0.0.1:%d" % self.port  # the browser proof a page's own write carries (WP22)
        if headers is not None:
            sent = headers
        return self.request("POST", "/api/v1/cmd", headers=sent, body=payload)

    def status_of(self, task_id):
        return tasks.get(self.data_dir, task_id).get("status")


class GuardTests(CmdCase):
    def test_missing_csrf_is_403(self):
        headers = self.write_headers()
        del headers["X-Roadmap-CSRF"]
        res = self.post({"op": "task.status", "args": {"id": "P1.1", "status": "done"}}, headers=headers)
        self.assertEqual(res.status, 403)
        self.assertEqual(self.status_of("P1.1"), self.start_status)

    def test_wrong_csrf_is_403(self):
        res = self.post({"op": "task.status", "args": {"id": "P1.1", "status": "done"}},
                        headers=self.write_headers(**{"X-Roadmap-CSRF": "wrong"}))
        self.assertEqual(res.status, 403)

    def test_wrong_origin_is_403(self):
        res = self.post({"op": "task.status", "args": {"id": "P1.1", "status": "done"}},
                        headers=self.write_headers(Origin="http://evil.example"))
        self.assertEqual(res.status, 403)

    def test_cross_site_is_403(self):
        res = self.post({"op": "task.status", "args": {"id": "P1.1", "status": "done"}},
                        headers=self.write_headers(**{"Sec-Fetch-Site": "cross-site"}))
        self.assertEqual(res.status, 403)

    def test_body_over_4kb_is_413(self):
        res = self.post(None, raw=b'{"op":"comment.add","args":{"text":"' + b"x" * 5000 + b'"}}')
        self.assertEqual(res.status, 413)

    def test_non_json_content_type_is_415(self):
        res = self.post({"op": "undo", "args": {}}, headers=self.write_headers(**{"Content-Type": "text/plain"}))
        self.assertEqual(res.status, 415)


class ShapeTests(CmdCase):
    def test_unknown_op_is_404(self):
        res = self.post({"op": "task.teleport", "args": {}})
        self.assertEqual(res.status, 404)
        self.assertEqual(res.json()["error"]["code"], "unknown_op")

    def test_invalid_args_are_422_with_the_problem(self):
        res = self.post({"op": "task.status", "args": {"id": "P1.1", "status": "bogus"}})
        self.assertEqual(res.status, 422)
        body = res.json()["error"]
        self.assertEqual(body["code"], "invalid_args")
        self.assertTrue(body["problems"] and "bogus" in body["problems"][0])

    def test_args_that_are_not_an_object_are_422(self):
        res = self.post({"op": "undo", "args": ["A1"]})
        self.assertEqual(res.status, 422)

    def test_rate_limit_is_429_after_ten_ops_in_a_second(self):
        statuses = [self.post({"op": "task.status", "args": {"id": "P1.1", "status": "todo"}}).status
                    for _ in range(11)]
        self.assertEqual(statuses[:10], [200] * 10)
        self.assertEqual(statuses[10], 429)


class RoundTripTests(CmdCase):
    def test_valid_op_returns_200_and_the_cli_shows_the_change(self):
        res = self.post({"op": "task.status", "args": {"id": "P1.1", "status": "done"}})
        self.assertEqual(res.status, 200)
        reply = res.json()
        self.assertTrue(reply["ok"])
        self.assertTrue(reply["activity"].startswith("A"))
        self.assertTrue(reply["undo"])
        env = dict(os.environ, ROADMAP_HOME=os.environ["ROADMAP_HOME"])
        env.pop("CLAUDECODE", None)
        shown = subprocess.run([sys.executable, "-m", "roadmap", "task", "show", "P1.1", "--project", PROJECT_ID],
                               cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("done", shown.stdout)

    def test_undo_reverses_the_change(self):
        reply = self.post({"op": "task.status", "args": {"id": "P1.1", "status": "done"}}).json()
        self.assertEqual(self.status_of("P1.1"), "done")
        undone = self.post({"op": "undo", "args": {"activity": reply["activity"]}})
        self.assertEqual(undone.status, 200)
        self.assertEqual(self.status_of("P1.1"), self.start_status)

    def test_control_stop_fills_the_snapshot_control_key(self):
        res = self.post({"op": "control.stop", "args": {}})
        self.assertEqual(res.status, 200)
        snap = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID).json()
        self.assertTrue(snap["control"]["stopped"])
        self.assertEqual(snap["control"]["reason"], "stopped by user")
        resumed = self.post({"op": "control.resume", "args": {}})
        self.assertEqual(resumed.status, 200)
        snap = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID).json()
        self.assertFalse(snap["control"]["stopped"])


class OtherRoutesTests(CmdCase):
    def test_usage_sync_is_still_the_only_other_write_route(self):
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"{}")
        self.assertEqual(res.status, 200)
        self.assertEqual(self.sync.calls, 1)
        self.assertEqual(self.request("POST", "/api/v1/meta", headers=self.write_headers(), body=b"{}").status, 405)


class DefaultProjectTests(CmdCase):
    def test_unknown_project_is_404(self):
        res = self.post({"op": "undo", "args": {"activity": "A1"}, "project": "nope"})
        self.assertEqual(res.status, 404)
        self.assertEqual(config_store.list_projects()[0]["id"], PROJECT_ID)
