"""The snapshot route with ?since=<rev> (R9.19): a since that matches the current revision gives 304 with no body and no
build; a stale or unknown since gives the normal 200 snapshot; If-None-Match keeps working as before. Runs against a
real server in a temp ROADMAP_HOME (the split-net fixture)."""

import json
import os

from tests.api.support import PROJECT_ID, ServerCase

SNAP = "/api/v1/projects/%s/snapshot" % PROJECT_ID


class SnapshotSince(ServerCase):
    def setUp(self):
        super().setUp()
        # a running job's duration moves with the clock, so the project here has no jobs.json
        os.remove(os.path.join(self.project_root, "docs", "jobs.json"))

    def current_rev(self):
        res = self.request("GET", SNAP)
        self.assertEqual(res.status, 200)
        return res.json()["rev"]

    def test_matching_since_gives_304_without_body(self):
        rev = self.current_rev()
        res = self.request("GET", SNAP + "?since=" + rev)
        self.assertEqual(res.status, 304)
        self.assertEqual(res.body, b"")
        self.assertEqual(res.header("ETag"), '"%s"' % rev)

    def test_quoted_since_matches_too(self):
        rev = self.current_rev()
        res = self.request("GET", SNAP + "?since=%22" + rev + "%22")
        self.assertEqual(res.status, 304)

    def test_stale_since_gives_full_snapshot(self):
        res = self.request("GET", SNAP + "?since=not-the-current-rev")
        self.assertEqual(res.status, 200)
        self.assert_schema(res, "snapshot")
        self.assertEqual(res.json()["rev"], self.current_rev())

    def test_empty_since_gives_full_snapshot(self):
        res = self.request("GET", SNAP + "?since=")
        self.assertEqual(res.status, 200)

    def test_since_changes_answer_when_data_changes(self):
        rev = self.current_rev()
        path = os.path.join(self.project_root, "docs", "tasks.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["updated"] = "2031-02-02"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        res = self.request("GET", SNAP + "?since=" + rev)
        self.assertEqual(res.status, 200)
        self.assertNotEqual(res.json()["rev"], rev)
        self.assertEqual(res.json()["tasks_updated"], "2031-02-02")

    def test_if_none_match_still_works_with_since_present(self):
        rev = self.current_rev()
        res = self.request("GET", SNAP + "?since=other", headers={"If-None-Match": '"%s"' % rev})
        self.assertEqual(res.status, 304)

    def test_unrelated_query_keys_are_ignored(self):
        rev = self.current_rev()
        res = self.request("GET", SNAP + "?x=1&since=" + rev)
        self.assertEqual(res.status, 304)
