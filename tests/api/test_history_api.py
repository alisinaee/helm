"""R11.4: GET /api/v1/projects/{pid}/history and GET /api/v1/history. A 200 with the page shape and an ETag, 304 on
If-None-Match, the cursor walks older pages, filters apply, bad queries give 400, an unknown project gives 404, and
head item text is only sent to this server's own page. Runs on an ephemeral port in a temp ROADMAP_HOME."""

import json
import os

from tests.api.support import PROJECT_ID, ServerCase

SAME_PAGE = {"Sec-Fetch-Site": "same-origin"}


class HistoryRoute(ServerCase):
    def setUp(self):
        super().setUp()
        self.path = "/api/v1/projects/%s/history" % PROJECT_ID
        docs = os.path.join(self.project_root, "docs")
        self._write(os.path.join(docs, "head.jsonl"), json.dumps(
            {"v": 1, "t": "e", "id": "H1", "ts": "2026-10-17T10:01:00Z", "src": "hook", "sum": "make history"}) + "\n")
        self._write(os.path.join(docs, "head-text.jsonl"), json.dumps({"id": "H1", "text": "SECRET-ish full text"}) +
                    "\n")

    def get(self, query="", headers=None, path=None):
        return self.request("GET", (path or self.path) + query, headers=headers if headers is not None else SAME_PAGE)

    def test_200_page_shape_and_etag(self):
        res = self.get()
        self.assertEqual(res.status, 200)
        body = res.json()
        for key in ("events", "next", "total", "counts", "actors", "hist"):
            self.assertIn(key, body)
        self.assertGreater(body["total"], 10)  # the fixture's jobs
        self.assertTrue(all(e["project"] == PROJECT_ID for e in body["events"]))
        etag = res.header("ETag")
        again = self.get(headers=dict(SAME_PAGE, **{"If-None-Match": etag}))
        self.assertEqual(again.status, 304)

    def test_cursor_and_filters(self):
        first = self.get("?limit=5&kind=job").json()
        self.assertEqual(len(first["events"]), 5)
        self.assertTrue(all(e["kind"] == "job" for e in first["events"]))
        older = self.get("?limit=5&kind=job&before=" + first["next"]).json()
        self.assertTrue(older["events"])
        self.assertLessEqual(older["events"][0]["ms"], first["events"][-1]["ms"])
        self.assertFalse({e["id"] for e in first["events"]} & {e["id"] for e in older["events"]})

    def test_text_only_for_the_own_page(self):
        own = self.get("?kind=head").json()
        self.assertEqual(own["events"][0]["detail"].get("text"), "SECRET-ish full text")
        other = self.get("?kind=head", headers={}).json()
        self.assertNotIn("text", other["events"][0]["detail"])

    def test_bad_query_and_unknown_project(self):
        self.assertEqual(self.get("?kind=nope").status, 400)
        self.assertEqual(self.get("?limit=9999").status, 400)
        self.assertEqual(self.get(path="/api/v1/projects/nope/history").status, 404)

    def test_all_projects_merge_carries_the_project(self):
        body = self.get(path="/api/v1/history", query="?limit=20").json()
        self.assertTrue(body["events"])
        self.assertTrue(all(e["pname"] == "split-net" for e in body["events"] if e["project"]))
