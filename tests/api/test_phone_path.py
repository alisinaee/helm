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
        self.assertEqual(out["list"], ["~", "…/" + HOME.split("/")[-1] + "2/x"])
        self.assertIn("path", snap["project"], "the input must not be mutated")

    def test_other_absolute_paths_keep_only_their_last_two_segments(self):
        snap = {"a": "/Users/bob/app/src", "b": "/home/carol/proj", "c": "/private/var/folders/x/y/z",
                "d": "/tmp/run", "e": "open /Users/bob/app now", "f": "/var/x"}
        out = routes._phone_public(snap)
        self.assertEqual(out["a"], "…/app/src")
        self.assertEqual(out["b"], "…/carol/proj")
        self.assertEqual(out["c"], "…/y/z")
        self.assertEqual(out["d"], "…/tmp/run")
        self.assertEqual(out["e"], "open …/bob/app now")
        self.assertEqual(out["f"], "…/var/x")

    def test_home_inside_a_sentence_is_rewritten(self):
        out = routes._phone_public({"msg": "see " + HOME + "/Works/app, then stop"})
        self.assertEqual(out["msg"], "see ~/Works/app, then stop")

    def test_urls_numbers_relative_and_plain_text_are_unchanged(self):
        snap = {"u": "https://example.com/a/b", "n": 12, "f": 1.5, "t": True, "z": None,
                "r": "a/b", "frac": "1/2", "plain": "nothing here", "list": ["x/y", {"deep": "ok"}]}
        out = routes._phone_public(snap)
        self.assertEqual(out, snap)

    def test_nested_values_are_scrubbed_and_the_input_is_not_mutated(self):
        snap = {"project": {"id": "x", "path": "/tmp/p"}, "rows": [{"where": "/home/dev/app/x"}]}
        out = routes._phone_public(snap)
        self.assertEqual(out["rows"][0]["where"], "…/app/x")
        self.assertEqual(snap["rows"][0]["where"], "/home/dev/app/x")
        self.assertEqual(snap["project"]["path"], "/tmp/p")

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
