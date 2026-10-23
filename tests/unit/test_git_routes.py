"""GIT-SPEC step 2: the read routes under /api/v1/projects/{pid}/git/ (status, log, branches, show, diff), and the
commit
and branch board refs (roadmap.core.refs). Checks: a non-repo folder gives 404 'Not a git repo'; log n is 1..100; show
and diff need the same-origin page (403 otherwise) and are refused on the phone listener; a secret name or a binary
file is skipped with its reason; a path that leaves the project gives 400; an unknown commit gives 404. Runs on an
ephemeral port in a temp ROADMAP_HOME with temp git repos; git runs with no global or system config."""

import os
import re
import subprocess
from types import SimpleNamespace
import unittest

from roadmap.core import refs
from roadmap.errors import RoadmapError
from roadmap.http import routes
from roadmap.store import config as config_store
from tests.api.support import ServerCase

SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}
GIT_ENV = {"PATH": os.environ.get("PATH", ""), "HOME": "/nonexistent", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C"}


def git(cwd, *args):
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"] + list(args), cwd=cwd,
                   env=GIT_ENV, check=True, capture_output=True)


class GitRoutes(ServerCase):
    def setUp(self):
        super().setUp()
        self.repo = os.path.join(os.path.realpath(self.tmp), "gitrepo")
        os.makedirs(os.path.join(self.repo, "docs"))
        git(self.repo, "init", "-q")
        self._write(os.path.join(self.repo, "docs", "a.txt"), "one\n")
        git(self.repo, "add", "--", "docs/a.txt")
        git(self.repo, "commit", "-q", "-m", "first", "-m", "Task: R7.1")
        self._write(os.path.join(self.repo, "docs", "a.txt"), "one\ntwo\n")
        self._write(os.path.join(self.repo, ".env"), "TOKEN=x\n")
        with open(os.path.join(self.repo, "img.bin"), "wb") as fh:
            fh.write(b"\0\1\2\3" * 16)
        git(self.repo, "add", "--", "docs/a.txt", ".env", "img.bin")
        git(self.repo, "commit", "-q", "-m", "second", "-m", "Task: R7.12\nJob: j12")
        self._write(os.path.join(self.repo, "untracked.txt"), "new\n")
        self.plain = os.path.join(os.path.realpath(self.tmp), "plain")
        os.makedirs(self.plain)
        config_store.add_project("git-repo", self.repo, project_id="gitrepo")
        config_store.add_project("plain", self.plain, project_id="plain")
        self.port_origin = {"Origin": "http://127.0.0.1:%d" % self.port, "Sec-Fetch-Site": "same-origin"}
        self.sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, env=GIT_ENV, capture_output=True,
                                  text=True, check=True).stdout.strip()

    def get(self, path, headers=None):
        return self.request("GET", "/api/v1/projects/gitrepo/git/" + path, headers=headers)

    def test_status_lists_the_changed_and_untracked_files(self):
        body = self.get("status").json()
        self.assertEqual(body["branch"], "main")
        self.assertEqual(body["ahead"], 0)
        self.assertIn("untracked.txt", body["untracked"])
        self.assertEqual(body["in_progress"], None)

    def test_log_rows_carry_the_task_and_job_links(self):
        body = self.get("log?n=1").json()
        self.assertEqual(body["n"], 1)
        self.assertEqual(len(body["rows"]), 1)
        self.assertEqual(body["rows"][0]["task"], "R7.12")
        self.assertEqual(body["rows"][0]["job"], "j12")
        self.assertEqual(body["rows"][0]["subject"], "second")
        self.assertEqual(len(body["rows"][0]["parents"]), 1)
        self.assertEqual(self.get("log?n=5").json()["rows"][-1]["parents"], [])

    def test_log_bad_n_gives_400(self):
        for query in ("n=0", "n=101", "n=ten", "x=1", "n=1&n=2"):
            with self.subTest(query=query):
                self.assertEqual(self.get("log?" + query).status, 400)

    def test_branches_flag_the_current_one(self):
        rows = self.get("branches").json()["branches"]
        self.assertEqual([(row["name"], row["current"]) for row in rows], [("main", True)])

    def test_a_folder_without_git_gives_404_not_a_repo(self):
        res = self.request("GET", "/api/v1/projects/plain/git/status")
        self.assertEqual(res.status, 404)
        self.assertIn(b"Not a git repo", res.body)

    def test_unknown_project_gives_404(self):
        self.assertEqual(self.request("GET", "/api/v1/projects/nope/git/status").status, 404)

    def test_writes_are_not_routes(self):
        res = self.request("POST", "/api/v1/projects/gitrepo/git/status", headers=self.write_headers())
        self.assertEqual(res.status, 405)

    def test_show_needs_the_same_origin_page(self):
        self.assertEqual(self.get("show/" + self.sha).status, 403)
        res = self.get("show/" + self.sha, headers=self.port_origin)
        self.assertEqual(res.status, 200)
        body = res.json()
        self.assertEqual(body["commit"]["task"], "R7.12")
        paths = {row["path"]: row for row in body["files"]}
        self.assertEqual(paths["docs/a.txt"]["added"], "1")
        self.assertIsNone(paths["img.bin"]["added"])

    def test_show_works_for_a_browser_get_without_origin_and_refuses_cross_site(self):
        ok = self.get("show/" + self.sha, headers=SAME_ORIGIN)
        self.assertEqual(ok.status, 200)
        for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"},
                        {"Sec-Fetch-Site": "same-origin", "Origin": "http://evil.example"}):
            self.assertEqual(self.get("show/" + self.sha, headers=headers).status, 403)
        self.assertEqual(self.get("diff/%s?path=docs/a.txt" % self.sha, headers=SAME_ORIGIN).status, 200)

    def test_workflow_reads_work_for_a_browser_get_without_origin(self):
        """The Workflow view's two reads (snapshot, git log) answer a same-origin browser GET (no Origin header)."""
        for path in ("/api/v1/projects/gitrepo/snapshot", "/api/v1/projects/gitrepo/git/log?n=100"):
            self.assertEqual(self.request("GET", path, headers=SAME_ORIGIN).status, 200)

    def test_show_bad_or_unknown_commit(self):
        self.assertEqual(self.get("show/zzzz", headers=self.port_origin).status, 400)
        self.assertEqual(self.get("show/" + "a" * 40, headers=self.port_origin).status, 404)

    def test_diff_shows_a_text_file_and_skips_secret_and_binary(self):
        text = self.get("diff/%s?path=docs/a.txt" % self.sha, headers=self.port_origin).json()
        self.assertIsNone(text["skipped"])
        self.assertIn("+two", text["diff"])
        secret = self.get("diff/%s?path=.env" % self.sha, headers=self.port_origin).json()
        self.assertEqual(secret["skipped"], "hidden (secret pattern)")
        self.assertIsNone(secret["diff"])
        binary = self.get("diff/%s?path=img.bin" % self.sha, headers=self.port_origin).json()
        self.assertTrue(binary["skipped"].startswith("binary"))
        self.assertIsNone(binary["diff"])

    def test_diff_refuses_globs_and_pathspec_magic(self):
        # a glob such as '*env*' or ':(glob)**/.env' could name a secret file without naming it
        for query in ("path=*", "path=*env*", "path=%3A%28glob%29**%2F.env", "path=%3A%2F", "path=a%5B1%5D.txt"):
            with self.subTest(query=query):
                res = self.get("diff/%s?%s" % (self.sha, query), headers=self.port_origin)
                self.assertEqual(res.status, 400)

    def test_diff_refuses_paths_outside_the_project(self):
        for query in ("path=../x", "path=/etc/passwd", "path=-x", ""):
            with self.subTest(query=query):
                res = self.get("diff/%s?%s" % (self.sha, query), headers=self.port_origin)
                self.assertEqual(res.status, 400)

    def test_diff_needs_the_same_origin_page(self):
        self.assertEqual(self.get("diff/%s?path=docs/a.txt" % self.sha).status, 403)


class PhoneGitRoutes(ServerCase):
    """The phone listener is a different app object (cmd_source "phone"); it gets status, branches and log only."""

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(os.path.realpath(self.tmp), "gitrepo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q")
        self._write(os.path.join(self.repo, "a.txt"), "x\n")
        git(self.repo, "add", "--", "a.txt")
        git(self.repo, "commit", "-q", "-m", "only")
        config_store.add_project("git-repo", self.repo, project_id="gitrepo")
        self.phone = SimpleNamespace(cmd_source="phone", port=0)

    def call(self, path, query=""):
        return routes.match(self.phone, SimpleNamespace(method="GET", path=path, query=query, headers={}))

    def test_status_log_and_branches_answer_without_the_project_path(self):
        for name in ("status", "log", "branches"):
            with self.subTest(route=name):
                reply = self.call("/api/v1/projects/gitrepo/git/" + name)
                self.assertEqual(reply.status, 200)
                self.assertNotIn(self.repo.encode("utf-8"), reply.body)

    def test_show_and_diff_are_refused(self):
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, env=GIT_ENV, capture_output=True,
                             text=True, check=True).stdout.strip()
        for path, query in (("show/" + sha, ""), ("diff/" + sha, "path=a.txt")):
            with self.subTest(route=path):
                with self.assertRaises(RoadmapError) as caught:  # the server maps this to 403
                    self.call("/api/v1/projects/gitrepo/git/" + path, query)
                self.assertEqual(caught.exception.code, "forbidden")

    def test_git_routes_are_listed_in_the_table(self):
        self.assertNotEqual(routes.route_template("/api/v1/projects/gitrepo/git/diff/abc1234"), "unmatched")
        self.assertEqual(routes.route_template("/api/v1/projects/gitrepo/git/log"),
                         "/api/v1/projects/{pid}/git/log")


class CommitAndBranchRefs(unittest.TestCase):
    def test_commit_and_branch_refs_round_trip(self):
        for kind, ident in (("commit", "1a2b3c4"), ("branch", "agent.R7.12")):
            with self.subTest(kind=kind):
                text = refs.format_ref("roadmap-board", kind, ident)
                self.assertRegex(text, refs.REF_RE)
                self.assertEqual(refs.parse(text), ("roadmap-board", kind, ident))

    def test_commit_record_lines_and_next(self):
        item = {"sha": "1a2b3c4d", "author": "ali", "time": 1700000000, "subject": "Add git reads",
                "task": "R7.12", "job": None}
        rows, next_cmd = refs.build({}, "roadmap-board", "commit", "1a2b3c4", item=item)
        self.assertEqual(next_cmd, "roadmap git show 1a2b3c4")
        lines = refs.lines("rb:roadmap-board/commit/1a2b3c4", rows, next_cmd)
        self.assertEqual(lines[0], "ref: rb:roadmap-board/commit/1a2b3c4")
        self.assertEqual(lines[1], "title: Add git reads")
        self.assertEqual(lines[3], "task: R7.12  job: -")
        self.assertEqual(lines[-1], "next: roadmap git show 1a2b3c4")

    def test_branch_record_without_item_is_none(self):
        self.assertIsNone(refs.build({}, "roadmap-board", "branch", "main"))



class WorktreeDiffRoutes(ServerCase):
    """GET .../git/diff?path=: the worktree diff of a changed file. A tracked file gives git diff, an untracked one
    all added; a path outside the status, a traversal or a secret name is refused or hidden."""

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(os.path.realpath(self.tmp), "wtrepo")
        os.makedirs(os.path.join(self.repo, "docs"))
        git(self.repo, "init", "-q")
        self._write(os.path.join(self.repo, "docs", "a.txt"), "one\n")
        self._write(os.path.join(self.repo, "keep.txt"), "still\n")
        git(self.repo, "add", "--", "docs/a.txt", "keep.txt")
        git(self.repo, "commit", "-q", "-m", "first")
        self._write(os.path.join(self.repo, "docs", "a.txt"), "one\ntwo\n")
        self._write(os.path.join(self.repo, "untracked.txt"), "new\n")
        self._write(os.path.join(self.repo, ".env"), "TOKEN=x\n")
        config_store.add_project("wt-repo", self.repo, project_id="wtrepo")
        self.origin = {"Origin": "http://127.0.0.1:%d" % self.port, "Sec-Fetch-Site": "same-origin"}

    def _write(self, path, text):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def diff(self, query, headers=None):
        return self.request("GET", "/api/v1/projects/wtrepo/git/diff?" + query, headers=headers or self.origin)

    def test_modified_file_is_a_git_diff(self):
        body = self.diff("path=docs/a.txt").json()
        self.assertEqual(body["path"], "docs/a.txt")
        self.assertEqual(body["status"], ".M")
        self.assertIsNone(body["skipped"])
        self.assertFalse(body["truncated"])
        self.assertEqual(body["lines"][0], {"t": "@", "text": "@@ -1 +1,2 @@"})
        self.assertIn({"t": " ", "text": "one"}, body["lines"])
        self.assertIn({"t": "+", "text": "two"}, body["lines"])
        self.assertNotIn("diff --git", str(body["lines"]))

    def test_untracked_file_is_all_added(self):
        body = self.diff("path=untracked.txt").json()
        self.assertEqual(body["status"], "??")
        self.assertEqual(body["lines"], [{"t": "@", "text": "@@ -0,0 +1,1 @@"}, {"t": "+", "text": "new"}])

    def test_untracked_output_is_capped_at_2000_lines(self):
        self._write(os.path.join(self.repo, "big.txt"), "x\n" * 2500)
        body = self.diff("path=big.txt").json()
        self.assertTrue(body["truncated"])
        self.assertEqual(sum(1 for row in body["lines"] if row["t"] == "+"), 2000)

    def test_a_secret_name_is_hidden(self):
        body = self.diff("path=.env").json()
        self.assertEqual(body["skipped"], "hidden (secret pattern)")
        self.assertEqual(body["lines"], [])

    def test_a_path_outside_the_status_gives_400(self):
        res = self.diff("path=keep.txt")
        self.assertEqual(res.status, 400)

    def test_traversal_absolute_and_empty_paths_give_400(self):
        for query in ("path=../x", "path=docs/../../etc/passwd", "path=/etc/passwd", "path=", "path=-x"):
            with self.subTest(query=query):
                self.assertEqual(self.diff(query).status, 400)

    def test_missing_path_and_extra_keys_give_400(self):
        self.assertEqual(self.request("GET", "/api/v1/projects/wtrepo/git/diff", headers=self.origin).status, 400)
        self.assertEqual(self.diff("path=docs/a.txt&x=1").status, 400)

    def test_needs_the_same_origin_page(self):
        self.assertEqual(self.request("GET", "/api/v1/projects/wtrepo/git/diff?path=docs/a.txt").status, 403)

    def test_route_is_listed_in_the_table(self):
        self.assertEqual(routes.route_template("/api/v1/projects/wtrepo/git/diff"),
                         "/api/v1/projects/{pid}/git/diff")


if __name__ == "__main__":
    unittest.main()
