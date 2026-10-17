"""The Git section (R7.29 W1.c, docs/GIT-SPEC.md section 5): web/js/views/git.js and web/css/git.css.

The rendered states come from tests/web/render_git.mjs (node, with stubbed reads). The source is checked for the rules
every view follows: no inline markup, no innerHTML, lines of 120 characters or fewer, and only the read routes and the
two writes the GUI is allowed (git.commit, git.push). No live service is needed.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
SOURCE = os.path.join(WEB, "js", "views", "git.js")
CSS = os.path.join(WEB, "css", "git.css")
RENDER = os.path.join(TESTS, "web", "render_git.mjs")
INDEX = os.path.join(WEB, "index.html")
ROUTES = os.path.join(WEB, "js", "routes.js")
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script|<style', re.IGNORECASE)
OPS = re.compile(r'send\("([a-z.]+)"')
DATA_GIT = re.compile(r'data-git="([a-z]+)"')
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def render():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed; the Git render check is skipped")
    proc = subprocess.run([node, "--experimental-default-type=module", RENDER, WEB],
                          capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("render_git.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class GitSource(unittest.TestCase):
    def setUp(self):
        self.src = read(SOURCE)

    def test_exports_the_section_view(self):
        self.assertRegex(self.src, r"export function sectionView\(vm\)")

    def test_only_read_routes_and_the_two_allowed_writes(self):
        self.assertEqual(sorted(set(OPS.findall(self.src))), ["git.commit", "git.push"])
        self.assertIn('"/api/v1/projects/" + encodeURIComponent(pid) + "/git/"', self.src)
        for path in ('base + "status"', 'base + "log?n=100"', 'base + "branches"'):
            self.assertIn(path, self.src)

    def test_only_the_four_controls_exist(self):
        # Discard, reset, merge, rebase and force push are named only in the help line, never as a control.
        self.assertEqual(sorted(set(DATA_GIT.findall(self.src))),
                         ["all", "commit", "file", "mode", "pick", "push", "refresh", "tab", "wfile"])

    def test_commit_never_takes_everything(self):
        self.assertNotIn("git add", self.src)
        self.assertIn('input[name="path"]:checked', self.src)

    def test_no_inline_markup_and_no_innerhtml(self):
        self.assertIsNone(INLINE.search(self.src))
        self.assertNotIn("innerHTML", self.src)

    def test_history_author_column_hides_on_phones(self):
        self.assertIn('class="rg-t git-au"', self.src)
        self.assertIn(".git-au{display:none}", read(CSS))

    def test_no_long_lines(self):
        self.assertTrue(all(len(line) <= 120 for line in self.src.split("\n")))

    def test_listeners_are_bound_once_on_the_document(self):
        self.assertIn('document.addEventListener("click", onClick)', self.src)
        self.assertIn('document.addEventListener("submit", onSubmit)', self.src)
        self.assertIn('document.addEventListener("keydown", onKey)', self.src)

    def test_writes_go_through_the_command_endpoint_with_a_project(self):
        self.assertIn('postJson("/api/v1/cmd", { op: op, args: args, project: pid })', self.src)


class GitLayout(unittest.TestCase):
    def test_vendor_licenses_and_lazy_load(self):
        lic = read(os.path.join(WEB, "vendor", "LICENSES.md"))
        self.assertIn("diff2html", lic)
        self.assertNotIn("vendor/", read(INDEX))


class GitStylesheet(unittest.TestCase):
    def test_stylesheet_is_small_and_has_no_colours(self):
        text = read(CSS)
        self.assertLessEqual(len(text.encode("utf-8")), 8192)
        self.assertIsNone(HEX.search(text))
        self.assertNotIn("style=", text)

    def test_index_links_the_stylesheet(self):
        self.assertIn('<link rel="stylesheet" href="/css/git.css">', read(INDEX))

    def test_components_css_is_not_touched_by_this_section(self):
        self.assertNotIn(".git-", read(os.path.join(WEB, "css", "components.css")))


class GitRoute(unittest.TestCase):
    def test_section_is_registered_with_its_module(self):
        text = read(ROUTES)
        self.assertIn('{ id: "git", label: "Git", icon: "workflow", module: "./views/git.js", bottom: false }', text)


class GitRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = render()

    def test_changes_shows_branch_banners_files_and_the_commit_form(self):
        html = self.out["changes"]
        self.assertIn("alpha", html)
        self.assertIn('class="git-chip git-branch">main<', html)
        self.assertIn("↑2 ↓0", html)
        self.assertIn("Push 2↑", html)
        self.assertIn('name="path" value="web/a.js"', html)
        self.assertIn('name="path" value="notes/new.txt"', html)
        self.assertIn('<span class="git-st git-st-m" title="M.">M</span>', html)
        self.assertIn('<span class="git-st git-st-u" title="??">U</span>', html)
        self.assertIn("Summary (required)", html)
        self.assertIn("Changes (3)", html)
        self.assertIn('data-git="commit"', html)
        self.assertIn('id="git-msg"', html)
        self.assertIn("Select a file", html)
        self.assertIn('data-git="push"', html)
        self.assertIn('aria-selected="true" data-focus="git-tab-changes"', html)

    def test_file_rows_are_buttons_beside_the_checkbox(self):
        html = self.out["changes"]
        self.assertIn('<button type="button" class="git-fb" data-git="wfile" data-path="docs/x.md"', html)
        self.assertIn('aria-current="false"', html)

    def test_diff_pane_has_name_status_pill_and_numbered_rows(self):
        html = self.out["diff"]
        self.assertIn('<span class="git-dname" title="docs/x.md">x.md</span>', html)
        self.assertIn('<span class="git-st git-st-m" title=".M">M</span>', html)
        self.assertIn('aria-current="true"', html)
        self.assertIn('<div class="gd-row gd-hunk"><span class="gd-no"></span><span class="gd-no"></span>'
                      '<span class="gd-tx">@@ -3,2 +3,3 @@</span></div>', html)
        self.assertIn('<div class="gd-row gd-ctx"><span class="gd-no">3</span><span class="gd-no">3</span>'
                      '<span class="gd-tx">keep</span></div>', html)
        self.assertIn('<div class="gd-row gd-del"><span class="gd-no">4</span><span class="gd-no"></span>'
                      '<span class="gd-tx">old</span></div>', html)
        self.assertIn('<div class="gd-row gd-add"><span class="gd-no"></span><span class="gd-no">4</span>'
                      '<span class="gd-tx">new &lt;b&gt;</span></div>', html)
        self.assertIn('<span class="gd-no"></span><span class="gd-no">5</span><span class="gd-tx">extra</span>', html)
        self.assertNotIn("new <b>", html)

    def test_diff_error_state_is_a_banner_with_the_reason(self):
        html = self.out["diffError"]
        self.assertIn("Diff could not be read.", html)
        self.assertIn("not in the status", html)
        self.assertNotIn('class="git-diff"', html)

    def test_history_draws_a_lane_graph_per_row(self):
        html = self.out["history"]
        self.assertIn('class="git-graph"', html)
        self.assertIn('data-git="pick" data-sha="1a2b3c4d5e6f"', html)

    def test_not_a_repo_is_an_empty_state_with_the_hint(self):
        html = self.out["notRepo"]
        self.assertIn("Not a git repo", html)
        self.assertIn("git init", html)
        self.assertNotIn('data-git="commit"', html)

    def test_history_rows_show_short_sha_task_and_relative_time(self):
        html = self.out["history"]
        self.assertIn('aria-selected="true" data-focus="git-tab-history"', html)
        self.assertIn(">1a2b3c4<", html)
        self.assertIn("R7.61 api: retry", html)
        self.assertIn("tokens: simple", html)
        self.assertIn("copy", html.lower())

    def test_branches_mark_the_current_branch_with_text(self):
        html = self.out["branches"]
        self.assertIn("agent/R7.29", html)
        self.assertIn(">current<", html)
        self.assertIn("↑2 ↓0", html)

    def test_all_projects_lists_each_project_with_its_git_link(self):
        html = self.out["all"]
        self.assertIn('href="#/p/alpha/git"', html)
        self.assertIn('href="#/p/beta/git"', html)

    def test_rendered_states_have_no_inline_markup(self):
        for key, html in self.out.items():
            self.assertIsNone(INLINE.search(html), key)


if __name__ == "__main__":
    unittest.main()
