"""Checks for the right panel (WP29): the Projects and Details views, the panel's CSS budget, and the write ops it calls.

The views are plain functions that return HTML strings, so tests/web/render_panel.mjs (run in node) builds the view
models from tests/fixtures/golden_snapshot.json plus the issues, questions, comments, queue, subtasks and rules that the
snapshot adds, and prints the HTML of each case. The checks: the rows sort and badge as specified, the Details
branches (task, issue, question, project card, missing item) render their controls, no inline style or handler
appears, and every aria-controls names an element in the same output. Static checks read panel.js for the write ops it
sends and the CSS size. The node checks are skipped when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_panel.mjs")
SNAPSHOT = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
COMMANDS = os.path.join(REPO, "roadmap", "services", "commands.py")
CMDOPS = os.path.join(REPO, "roadmap", "services", "cmdops.py")
FEATOPS = os.path.join(REPO, "roadmap", "services", "featops.py")
PANEL_CSS_MAX = int(4.5 * 1024)

INLINE = re.compile(r"""\sstyle\s*=|\son[a-z]{3,}\s*=""", re.IGNORECASE)
CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')
RUN_OP = re.compile(r'run\(\s*"([a-z]+\.[a-z]+)"')
REGISTERED = re.compile(r'^\s*"([a-z]+\.[a-z]+)":\s*_Op\(', re.MULTILINE)
REGISTERED_HERE = re.compile(r'_register\("([a-z]+\.[a-z]+)"')


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def render():
    node = shutil.which("node")
    proc = subprocess.run(
        [node, "--experimental-default-type=module", RENDER, WEB, SNAPSHOT],
        capture_output=True, text=True, check=False, timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError("render failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def row_of(html, name):
    """The one project row (an <a class="p-row">) whose title is the project name."""
    match = re.search(r'<a class="p-row"[^>]*title="' + re.escape(name) + r'".*?</a>', html, re.S)
    return match.group(0) if match else ""


def badge_count(row, kind):
    match = re.search(r'data-kind="' + kind + r'"[^>]*>.*?</svg>(\d+)<', row, re.S)
    return int(match.group(1)) if match else None


class PanelRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the panel render check is skipped")
        cls.views = render()

    def test_every_case_renders_without_inline_markup(self):
        for name, html in self.views.items():
            self.assertGreater(len(html), 40, name)
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("<script", html, name)
            self.assertNotIn("javascript:", html, name)

    def test_every_aria_controls_names_an_element(self):
        for name, html in self.views.items():
            ids = set(IDS.findall(html))
            missing = [target for target in CONTROLS.findall(html) if target not in ids]
            self.assertEqual(missing, [], name)

    def test_all_projects_row_comes_first_and_is_current_in_all_scope(self):
        html = self.views["projectsHome"]
        self.assertLess(html.index("All projects"), html.index("split-net"))
        self.assertIn('p-row p-all" href="#/all/work" aria-current="page"', html)

    def test_rows_sort_needs_you_then_running_then_the_rest(self):
        html = self.views["projectsProject"]
        order = [html.index(name) for name in ("split-net", "rb-site", "Idle one")]
        self.assertEqual(order, sorted(order))

    def test_badges_match_the_fixture_counts(self):
        row = row_of(self.views["projectsProject"], "split-net")
        self.assertEqual(badge_count(row, "question"), 2)
        self.assertEqual(badge_count(row, "blocker"), 1)
        self.assertEqual(badge_count(row, "running"), 1)

    def test_rows_without_a_snapshot_show_no_question_or_blocker_badge(self):
        html = self.views["projectsHome"]
        self.assertEqual(html.count('data-kind="question"'), 1)
        self.assertEqual(html.count('data-kind="blocker"'), 1)

    def test_a_blocked_project_shows_the_locked_mark_and_its_state(self):
        html = self.views["projectsBlocked"]
        self.assertIn('data-state="blocked"', html)
        self.assertIn("Locked", html)
        self.assertIn("Blocked by limit", html)

    def test_no_projects_gives_an_empty_state(self):
        self.assertIn("No projects yet.", self.views["projectsNone"])

    def test_task_details_show_status_queue_cap_subtasks_and_comments(self):
        html = self.views["detailsTask"]
        self.assertIn('data-status="done" data-focus="st-done"', html)
        self.assertRegex(html, r'data-status="done"[^>]*aria-pressed="true"|aria-pressed="true"[^>]*data-status="done"')
        self.assertIn('data-side="start"', html)
        self.assertIn('data-side="stop"', html)
        self.assertIn('value="40"', html)
        self.assertIn('data-addr="P0.1/1"', html)
        self.assertIn('data-done="true"', html)
        self.assertIn("Write tests", html)
        self.assertIn("Looks right to me", html)
        self.assertIn('data-side-form="sub-add"', html)
        self.assertIn('data-side-form="comment"', html)

    def test_task_details_show_the_linked_issue_and_question(self):
        html = self.views["detailsTask"]
        self.assertIn("Queue stalls", html)
        self.assertIn("Keep the old API?", html)

    def test_rules_and_definition_of_done_are_hidden_when_absent(self):
        html = self.views["detailsTask"]
        self.assertNotIn("Rules that apply", html)
        self.assertNotIn("Definition of done", html)

    def test_rules_show_only_those_that_apply_to_the_task(self):
        html = self.views["detailsRules"]
        self.assertIn("Keep it small", html)
        self.assertNotIn("Not for this task", html)

    def test_issue_details_offer_close_and_question_details_offer_answers(self):
        self.assertIn('data-side="close-issue" data-id="I1"', self.views["detailsIssue"])
        question = self.views["detailsQuestion"]
        self.assertIn('data-side="answer" data-id="Q1" data-value="yes"', question)
        self.assertIn('data-side-form="answer"', question)

    def test_project_card_shows_when_nothing_is_selected(self):
        html = self.views["detailsCard"]
        self.assertIn("Tasks left", html)
        self.assertIn("Open Work for this project", html)

    def test_missing_item_says_it_is_not_open_and_offers_back(self):
        html = self.views["detailsMissing"]
        self.assertIn("not open in this project", html)
        self.assertIn('data-side="back"', html)

    def test_all_scope_details_ask_for_a_project(self):
        self.assertIn("Choose a project to see its details.", self.views["detailsHome"])


class PanelSourceTests(unittest.TestCase):

    def test_panel_files_exist(self):
        for name in ("panel.js", "projects.js", "details.js"):
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", "views", name)), name)

    def test_panel_css_is_within_budget(self):
        size = os.path.getsize(os.path.join(WEB, "css", "panel.css"))
        self.assertLessEqual(size, PANEL_CSS_MAX, "panel.css is %d bytes" % size)

    def test_aria_controls_in_the_panel_name_an_id_in_the_same_file(self):
        text = read(os.path.join(WEB, "js", "views", "panel.js"))
        self.assertIn('aria-controls="side-body"', text)
        self.assertIn('id="side-body"', text)

    def test_every_write_op_the_panel_sends_is_a_public_command(self):
        ops = set()
        for name in ("panel.js", "details.js", "projects.js"):
            ops.update(RUN_OP.findall(read(os.path.join(WEB, "js", "views", name))))
        ops.update(re.findall(r'queueTask\(el, "([a-z]+\.[a-z]+)"\)', read(os.path.join(WEB, "js", "views",
                                                                                         "panel.js"))))
        registered = set(REGISTERED.findall(read(COMMANDS))) | set(REGISTERED_HERE.findall(read(CMDOPS))) | set(REGISTERED_HERE.findall(read(FEATOPS)))
        self.assertTrue(ops, "the panel sends no ops")
        self.assertEqual(sorted(ops - registered), [], "ops missing from services/commands.py")


if __name__ == "__main__":
    sys.exit(unittest.main())
