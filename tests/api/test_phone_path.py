"""Phone listener privacy: the snapshot it serves has no project.path, and no absolute home path. The localhost app
keeps project.path (the GUI Copy command needs it). The phone server runs for real on port 0 with a fake token."""

import os

from roadmap.http import routes
from tests.api.support import PROJECT_ID, ServerCase
from tests.api.test_security_phone import PhoneCase

HOME = os.path.expanduser("~")


class PhonePathHelper(ServerCase):
    def test_scrub_drops_project_path_and_rewrites_home(self):
        snap = {"project": {"id": "x", "path": "/some/where"}, "meters": {"where": HOME + "/Works/app"},
                "list": [HOME, HOME + "2/x"]}
        out = routes._phone_public(snap)
        self.assertNotIn("path", out["project"])
        self.assertEqual(out["meters"]["where"], "~/Works/app")
        self.assertEqual(out["list"], ["~", HOME + "2/x"])
        self.assertIn("path", snap["project"], "the input must not be mutated")

    def test_localhost_app_keeps_project_path(self):
        res = self.request("GET", "/api/v1/projects/%s/snapshot" % PROJECT_ID)
        self.assertEqual(res.status, 200)
        self.assertIn("path", res.json()["project"])


class PhoneSnapshot(PhoneCase):
    def test_phone_snapshot_has_no_project_path(self):
        res = self.phone_get("/api/v1/projects/%s/snapshot" % PROJECT_ID, cookie=self.good_cookie())
        self.assertEqual(res.status, 200)
        body = res.json()
        self.assertNotIn("path", body["project"])
        self.assertNotIn(self.project_root, res.body.decode("utf-8"))
        self.assertNotIn(self.tmp, res.body.decode("utf-8"))

    def test_phone_legacy_alias_is_scrubbed_too(self):
        res = self.phone_get("/data.json", cookie=self.good_cookie())
        self.assertEqual(res.status, 200)
        self.assertNotIn("path", res.json()["project"])
        self.assertNotIn(self.project_root, res.body.decode("utf-8"))
