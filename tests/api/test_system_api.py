"""R10.21 (SYSTEM-DESIGN A3): GET /api/v1/projects/{pid}/system. Checks: a 200 that matches the system schema, the ETag
and 304 on If-None-Match, a changed docs/system.json giving a new ETag, the same-origin read guard (cross-site and
no-header reads give 403; a same-origin GET with only Sec-Fetch-Site gives 200), path confinement (a symlinked
docs/system.json is refused and its target never shows), and an unregistered project gives 404. Runs on an ephemeral
port in a temp ROADMAP_HOME; the project folder is the split-net fixture copied into it."""

import json
import os
import subprocess

from tests.api.support import PROJECT_ID, ServerCase

SAME_PAGE = {"Sec-Fetch-Site": "same-origin"}


class SystemRoute(ServerCase):
    def setUp(self):
        super().setUp()
        self.path = "/api/v1/projects/%s/system" % PROJECT_ID

    def get(self, headers=None, path=None):
        return self.request("GET", path or self.path, headers=dict(SAME_PAGE, **(headers or {})))

    def test_200_matches_the_schema_and_carries_an_etag(self):
        res = self.get()
        self.assert_schema(res, "system")
        body = res.json()
        self.assertEqual(body["source"], "baseline")
        self.assertIsNone(body["sha"])  # the fixture is not a git repo
        self.assertTrue(body["components"])
        self.assertIn("heat", body)
        self.assertTrue(res.header("ETag").startswith('"'))

    def test_304_on_a_matching_if_none_match(self):
        etag = self.get().header("ETag")
        res = self.get({"If-None-Match": etag})
        self.assertEqual(res.status, 304)
        self.assertEqual(res.body, b"")
        self.assertEqual(res.header("ETag"), etag)

    def test_a_changed_system_json_gives_a_new_etag_and_the_file_source(self):
        etag = self.get().header("ETag")
        self._write(os.path.join(self.project_root, "docs", "system.json"), json.dumps({
            "version": 1, "layers": ["service"],
            "components": [{"id": "core", "name": "Core", "layer": "service", "kind": "module",
                            "files": ["docs/**"]}],
            "edges": []}))
        res = self.get({"If-None-Match": etag})
        self.assertEqual(res.status, 200)
        self.assertNotEqual(res.header("ETag"), etag)
        body = res.json()
        self.assertEqual(body["source"], "file")
        self.assertEqual([c["id"] for c in body["components"]], ["core"])
        self.assertEqual(body["components"][0]["heat"]["commits30"], 0)

    def test_cross_site_and_headerless_reads_are_refused(self):
        for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}, {}):
            with self.subTest(headers=headers):
                res = self.request("GET", self.path, headers=headers)
                self.assertEqual(res.status, 403)
                self.assertNotIn(b"components", res.body)

    def test_same_origin_get_with_only_sec_fetch_site_is_served(self):
        res = self.request("GET", self.path, headers={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(res.status, 200)
        self.assertIn("components", res.json())

    def test_a_symlinked_system_json_is_refused_and_never_shown(self):
        outside = os.path.join(self.tmp, "outside.json")
        self._write(outside, json.dumps({"version": 1, "components": [{"id": "leak", "name": "LEAKED-TEXT"}]}))
        link = os.path.join(self.project_root, "docs", "system.json")
        os.symlink(outside, link)
        res = self.get()
        self.assert_schema(res, "system")
        body = res.json()
        self.assertEqual(body["source"], "baseline")
        self.assertTrue(any("system.json" in w for w in body["warnings"]))
        self.assertNotIn(b"LEAKED-TEXT", res.body)

    def test_git_sha_is_the_head_commit(self):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.com")
        root = self.project_root
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "R10.21: fixture commit"], cwd=root, check=True, env=env)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True,
                              text=True).stdout.strip()
        res = self.get()
        self.assert_schema(res, "system")
        self.assertEqual(res.json()["sha"], head)
        self.assertIn(head, res.header("ETag"))

    def test_unregistered_project_gives_404(self):
        res = self.get(path="/api/v1/projects/nope/system")
        self.assertEqual(res.status, 404)

    def test_other_methods_are_refused(self):
        res = self.request("POST", self.path, headers=dict(SAME_PAGE))
        self.assertEqual(res.status, 405)
