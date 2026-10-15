"""HEAD-SPEC H7: GET /api/v1/projects/{pid}/head. Checks: the rows and counts for f=open|all and n, bad query values give
400, an unregistered project gives 404, full=H.. needs the same-origin page (403 otherwise) and then gives the verbatim
text and history, an unknown id gives 404, and the phone listener never gets text or history. Runs on an ephemeral
port in a temp ROADMAP_HOME; the head store is written with the H3 service."""

import json
import os
import re
from types import SimpleNamespace

from roadmap.http import routes
from roadmap.services import head as head_service
from tests.api.support import PROJECT_ID, ServerCase

SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


def walk_keys(value):
    if isinstance(value, dict):
        for key, sub in value.items():
            yield key
            yield from walk_keys(sub)
    elif isinstance(value, list):
        for sub in value:
            yield from walk_keys(sub)


class HeadRoute(ServerCase):
    def setUp(self):
        super().setUp()
        self.data_dir = os.path.join(self.project_root, "docs")
        self.path = "/api/v1/projects/%s/head" % PROJECT_ID
        self.first = head_service.capture(self.data_dir, "Please fix the broken export button", session_id="s1",
                                          src="cli", acct="A")
        self.second = head_service.capture(self.data_dir, "Always use the staging host for checks", session_id="s1",
                                           src="hook", acct="A")
        self.same_origin = {"Origin": "http://127.0.0.1:%d" % self.port, "Sec-Fetch-Site": "same-origin"}

    def get(self, query="", headers=None):
        path = self.path + ("?" + query if query else "")
        return self.request("GET", path, headers=headers)

    def test_open_rows_by_default_with_counts(self):
        res = self.get()
        self.assertEqual(res.status, 200)
        body = res.json()
        self.assertEqual((body["f"], body["n"], body["total"]), ("open", 100, 2))
        self.assertEqual([row["id"] for row in body["rows"]], [self.first["id"], self.second["id"]])
        self.assertEqual(body["rows"][0]["kind"], "bug")
        self.assertNotIn("text", set(walk_keys(body)))

    def test_done_rows_leave_the_open_list_and_stay_in_all(self):
        head_service.update(self.data_dir, self.first["id"], by="person", sets={"status": "done"})
        self.assertEqual(self.get("f=open").json()["total"], 1)
        everything = self.get("f=all").json()
        self.assertEqual((everything["f"], everything["total"]), ("all", 2))

    def test_n_keeps_the_newest_rows(self):
        body = self.get("n=1").json()
        self.assertEqual(body["n"], 1)
        self.assertEqual([row["id"] for row in body["rows"]], [self.second["id"]])
        self.assertEqual(body["total"], 2)

    def test_bad_query_values_give_400(self):
        for query in ("f=bogus", "n=0", "n=201", "n=ten", "x=1", "f=open&f=all", "full=12", "full=H1x"):
            with self.subTest(query=query):
                self.assertEqual(self.get(query).status, 400)

    def test_unregistered_project_gives_404(self):
        res = self.request("GET", "/api/v1/projects/nope/head")
        self.assertEqual(res.status, 404)

    def test_full_needs_the_same_origin_page(self):
        res = self.get("full=%s" % self.first["id"])
        self.assertEqual(res.status, 403)
        self.assertNotIn(b"Please fix", res.body)

    def test_full_gives_text_and_history_on_the_same_origin_page(self):
        head_service.update(self.data_dir, self.first["id"], by="head", sets={"kind": "bug", "sum": "Fix export"},
                            note="triaged")
        res = self.get("full=%s" % self.first["id"], headers=self.same_origin)
        self.assertEqual(res.status, 200)
        full = res.json()["full"]
        self.assertEqual(full["id"], self.first["id"])
        self.assertEqual(full["text"], "Please fix the broken export button")
        self.assertEqual([line["by"] for line in full["history"]], ["cli", "head"])
        self.assertEqual(full["history"][1]["note"], "triaged")

    def test_full_accepts_a_browser_same_origin_get_without_origin(self):
        # A browser sends no Origin on a same-origin GET, only Sec-Fetch-Site: same-origin (the page's own fetch).
        res = self.get("full=%s" % self.first["id"], headers={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(res.status, 200)
        self.assertEqual(res.json()["full"]["text"], "Please fix the broken export button")

    def test_full_refuses_cross_site_and_foreign_origin_reads(self):
        cross = self.get("full=%s" % self.first["id"], headers={"Sec-Fetch-Site": "cross-site"})
        foreign = self.get("full=%s" % self.first["id"],
                           headers={"Origin": "http://evil.example", "Sec-Fetch-Site": "same-origin"})
        self.assertEqual((cross.status, foreign.status), (403, 403))
        self.assertNotIn(b"Please fix", cross.body + foreign.body)

    def test_full_gives_reply_and_assets_on_the_same_origin_page(self):
        # HEAD-SPEC section 13: the reply and the attachment names come with the text, same guard as the text.
        head_service.set_reply(self.data_dir, self.second["id"], "Fixed the staging check.")
        shot = head_service.capture(self.data_dir, "Please check the board shot and @docs/plan.md", session_id="s2",
                                    src="hook", assets=["shot.png", "docs/plan.md"])
        self.assertEqual(self.get("full=%s" % self.second["id"]).status, 403)
        full = self.get("full=%s" % self.second["id"], headers=self.same_origin).json()["full"]
        self.assertEqual(full["reply"], "Fixed the staging check.")
        self.assertEqual(full["assets"], [])
        full = self.get("full=%s" % shot["id"], headers=self.same_origin).json()["full"]
        self.assertEqual(full["assets"], ["shot.png", "docs/plan.md"])
        head_service.set_reply(self.data_dir, self.first["id"], "Reply to the export.")
        self.assertEqual(self.get("full=%s" % self.first["id"], headers=self.same_origin).json()["full"]["reply"],
                         "Reply to the export.")

    def test_full_unknown_id_gives_404(self):
        res = self.get("full=H999", headers=self.same_origin)
        self.assertEqual(res.status, 404)


class PhoneView(ServerCase):
    """The phone listener is a different app object (cmd_source "phone"); called here with its source, no token."""

    def setUp(self):
        super().setUp()
        self.data_dir = os.path.join(self.project_root, "docs")
        head_service.capture(self.data_dir, "Please fix the broken export button", session_id="s1", src="cli")
        self.phone = SimpleNamespace(cmd_source="phone", port=0)

    def test_phone_body_has_rows_and_no_text_or_history(self):
        req = SimpleNamespace(query="full=H1", headers={})
        match = re.fullmatch(r"/api/v1/projects/(?P<pid>[a-z0-9][a-z0-9-]{0,39})/head",
                             "/api/v1/projects/%s/head" % PROJECT_ID)
        reply = routes.project_head(self.phone, req, match)
        self.assertEqual(reply.status, 200)
        body = json.loads(reply.body.decode("utf-8"))
        self.assertEqual(body["full"], {"id": "H1"})
        self.assertEqual(body["rows"][0]["id"], "H1")
        self.assertNotIn("text", set(walk_keys(body)))
        self.assertNotIn("history", set(walk_keys(body)))
        self.assertNotIn("Please fix", reply.body.decode("utf-8"))
