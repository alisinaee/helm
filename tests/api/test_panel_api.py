"""R11.2 panel to head over HTTP: a proven browser write, a Mark and a usage Update each append a panel line; an
unproven (agent) write does not; the cmd reply names the panel line; GET .../panel reports sent and seen; the hook
then hands the lines to the head. Temp ROADMAP_HOME and a port-0 server only."""

import json
import os
from unittest import mock

from roadmap.services import headpanel, hooks, tasks
from tests.api.support import PROJECT_ID, ServerCase


class PanelApiTests(ServerCase):
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

    def op(self, op, args, headers=None):
        body = json.dumps({"op": op, "args": args, "project": PROJECT_ID}).encode("utf-8")
        return self.request("POST", "/api/v1/cmd", headers=headers or self.proven(), body=body)

    def panel(self):
        res = self.request("GET", "/api/v1/projects/%s/panel" % PROJECT_ID)
        self.assertEqual(res.status, 200)
        return res.json()

    def test_person_writes_mark_and_update_reach_the_panel_ledger(self):
        asked = self.op("question.ask", {"text": "Ship now?", "opts": ["yes", "no"]}).json()
        self.assertEqual(asked["panel"]["id"], "P1")
        self.assertIn(asked["panel"]["head"], ("watching", "open", "none"))
        self.op("question.answer", {"id": asked["data"]["id"], "value": "yes"})
        logged = self.op("head.log", {"text": "check the panel path today please"}).json()
        self.op("head.set", {"id": logged["data"]["id"], "note": "my comment in head chat"})
        self.op("limit.set", {"pct": 80})
        mark = self.request("POST", "/api/v1/log", headers=self.proven(), body=json.dumps(
            {"sid": "abcdef12", "events": [{"ev": "ui.mark", "msg": "m", "ref": "P1.1",
                                            "route": "#/p/" + PROJECT_ID + "/head"}]}).encode("utf-8"))
        self.assertEqual(mark.status, 204)
        sync = self.request("POST", "/api/v1/usage/sync", headers=self.proven(), body=b"{}")
        self.assertEqual(sync.status, 200)
        sums = [o["sum"] for o in headpanel.read(self.data_dir)]
        self.assertEqual(len(sums), 7)
        self.assertIn("Q1 answered yes", sums[1])
        self.assertIn('"my comment in head chat"', sums[3])
        self.assertIn("80", sums[4])
        self.assertTrue(sums[5].startswith("Mark: I am seeing a bug here"))
        self.assertTrue(sums[6].startswith("usage Update pressed"))
        body = self.panel()
        self.assertEqual(body["counts"], {"sent": 7, "seen": 0, "acted": 0})
        self.assertEqual(body["rows"][0]["id"], "P7")

    def test_an_unproven_write_is_not_a_panel_action(self):
        headers = self.write_headers()  # no Origin: labelled agent, not the person
        res = self.op("question.ask", {"text": "Ship now?"}, headers=headers)
        self.assertEqual(res.status, 200, res.body[:200])
        self.assertNotIn("panel", res.json())
        self.assertEqual(headpanel.read(self.data_dir), [])

    def test_an_unproven_mark_or_update_is_not_a_panel_action(self):
        mark = self.request("POST", "/api/v1/log", headers=self.write_headers(), body=json.dumps(
            {"sid": "abcdef12", "events": [{"ev": "ui.mark", "msg": "m", "ref": "P1.1",
                                            "route": "#/p/" + PROJECT_ID + "/head"}]}).encode("utf-8"))
        self.assertEqual(mark.status, 204)
        sync = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"{}")
        self.assertEqual(sync.status, 200)
        self.assertEqual(headpanel.read(self.data_dir), [])

    def test_the_hook_hands_the_lines_to_the_head_and_the_route_shows_seen(self):
        self.op("question.ask", {"text": "Ship now?", "opts": ["yes", "no"]})
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": self.project_root, "session_id": "s1",
                   "prompt": "what next"}
        reply = hooks.run_hook(json.dumps(payload))
        self.assertIn("panel P1 ", reply["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.panel()["rows"][0]["state"], "seen")
