"""Checks for the Overview, Inbox and Activity sections (WP30).

The views are plain functions that return HTML strings. tests/web/render_sections.mjs renders them in node from the
golden snapshot and from a synthetic snapshot that carries questions, needs-you rows, limits at 90 percent, activity
and blockers. The checks: the markup is CSP-safe and its aria-controls resolve; the question cards carry one button
per option with the default highlighted and a countdown; a limit at 80 percent or more gives the banner and an
Override button; undo is offered only on lines that can be undone; text from the data is escaped; the empty states
read as the spec says; the routes register the two new modules; and every data-action these views emit is handled
by app.js. The node checks are skipped when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_sections.mjs")
GOLDEN = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
VIEWS = ("overview.js", "inbox.js", "activity.js")

CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
DATA_ACTION = re.compile(r'data-action=\\?"([a-z-]+)')

SYNTH = {
    "project": {"id": "splitnet", "title": "split-net"},
    "questions": [
        {"id": "Q1", "task": "P0.8", "text": "Ship <b>now</b>?", "opts": ["yes", "no"],
         "def": "yes", "block": True, "timeoutS": 60, "status": "open", "asked": "2026-10-13T11:59:00Z",
         "answer": None, "answered": None},
        {"id": "Q2", "task": "", "text": "Keep the old file?", "opts": [], "def": None, "block": False,
         "timeoutS": None, "status": "open", "asked": None, "answer": None, "answered": None},
    ],
    "needsYou": [
        {"kind": "task", "id": "P1.2", "title": "Check the hardware"},
        {"kind": "question", "id": "Q1", "text": "Ship now?"},
    ],
    "activity": [
        {"id": "a1", "at": "2026-10-13T11:00:00Z", "src": "gui", "op": "control.stop", "sum": "stop", "undo": True},
        {"id": "a2", "at": "2026-10-13T11:30:00Z", "src": "cli", "op": "task.status", "sum": "P0.8 done",
         "undo": False},
    ],
    "blocked": ["P0.8"],
    "issues": [{"id": "I1", "kind": "blocker", "title": "Missing fixture", "sev": 1, "status": "open",
                "tasks": ["P0.8"]}],
    "control": {"stopped": False, "blocked": False, "reason": "", "warn": ["budget 80% used"]},
    "meters": {
        "limits": [
            {"id": "L1", "scope": "global", "window": "day", "kind": "pct", "used": 9.0, "limit": 10,
             "state": "warn", "est": False, "paceAt": "2026-10-13T16:40:00", "src": None},
            {"id": "L2", "scope": "project", "window": "week", "kind": "tok", "used": 120, "limit": 500,
             "state": "ok", "est": True, "paceAt": None, "src": "budget"},
        ],
        "today": {"pts": 9.0, "tokK": 120, "estPts": None},
        "week": {"pct": 62, "tokK": 300, "estPts": None},
    },
}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def render():
    node = shutil.which("node")
    with tempfile.TemporaryDirectory() as tmp:
        synth = os.path.join(tmp, "synthetic.json")
        with open(synth, "w", encoding="utf-8") as fh:
            json.dump(SYNTH, fh)
        proc = subprocess.run(
            [node, "--experimental-default-type=module", RENDER, WEB, GOLDEN, synth],
            capture_output=True, text=True, check=False, timeout=60,
        )
    if proc.returncode != 0:
        raise AssertionError("render_sections.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class SectionRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the section render checks are skipped")
        cls.out = render()

    def test_every_view_renders_non_empty(self):
        for name, html in self.out.items():
            self.assertGreater(len(html), 40, name)

    def test_no_inline_style_handlers_or_script(self):
        for name, html in self.out.items():
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("<script", html, name)

    def test_every_aria_controls_names_an_element(self):
        for name, html in self.out.items():
            ids = set(IDS.findall(html))
            missing = [target for target in CONTROLS.findall(html) if target not in ids]
            self.assertEqual(missing, [], name)

    def test_empty_states_use_the_spec_words(self):
        self.assertIn("All quiet. Nothing needs you.", self.out["inboxGolden"])
        self.assertIn("No open blockers.", self.out["overviewGolden"])
        self.assertIn("No activity yet.", self.out["activityGolden"])

    def test_loading_inbox_shows_a_skeleton_not_the_empty_text(self):
        self.assertIn('aria-busy="true"', self.out["inboxLoading"])
        self.assertNotIn("All quiet", self.out["inboxLoading"])

    def test_question_card_has_one_button_per_option_and_a_default(self):
        html = self.out["inboxProject"]
        self.assertEqual(html.count('data-action="inbox-answer"'), 2)
        self.assertEqual(html.count("btn-primary is-default"), 1)
        self.assertIn('data-value="yes"', html)
        self.assertIn('data-value="no"', html)
        self.assertIn('data-qid="Q1"', html)

    def test_countdown_carries_the_deadline_and_the_task_link(self):
        # The countdown text itself is written by the page's ticker from the real clock, so only the attributes are fixed.
        html = self.out["inboxProject"]
        self.assertIn('data-deadline-ms="', html)
        self.assertIn('data-word="Defaults to yes in "', html)
        self.assertIn('href="#/p/splitnet/work/i/P0.8"', html)

    def test_question_text_is_escaped(self):
        html = self.out["inboxProject"]
        self.assertIn("Ship &lt;b&gt;now&lt;/b&gt;?", html)
        self.assertNotIn("<b>", html)

    def test_question_without_options_has_no_answer_buttons(self):
        html = self.out["inboxProject"]
        self.assertIn("Keep the old file?", html)
        self.assertIn("This question has no options.", html)

    def test_global_inbox_is_grouped_by_project(self):
        html = self.out["inboxAll"]
        self.assertIn('<h3 class="grp-h"><a href="#/p/splitnet/inbox">split-net</a></h3>', html)

    def test_needs_you_tasks_are_listed_below_the_questions(self):
        html = self.out["inboxProject"]
        self.assertIn("Check the hardware", html)
        self.assertLess(html.index("inbox-answer"), html.index("Check the hardware"))

    def test_limit_banner_shows_at_eighty_percent_with_override(self):
        html = self.out["overviewProject"]
        self.assertIn("Usage across all projects is at 90% of the daily limit.", html)
        self.assertIn('data-action="override"', html)
        self.assertIn("Override for 1 hour", html)

    def test_limit_banner_is_not_shown_without_a_full_limit(self):
        self.assertNotIn("% of the ", self.out["overviewGolden"])
        self.assertNotIn("% of its ", self.out["overviewGolden"])

    def test_global_limit_banner_has_no_override_button(self):
        html = self.out["overviewAll"]
        self.assertIn("Usage across all projects is at 90% of the daily limit.", html)
        self.assertNotIn('data-action="override"', html)

    def test_running_banner_has_one_stop_button(self):
        html = self.out["overviewProject"]
        self.assertEqual(html.count('data-op="control.stop"'), 1)

    def test_meters_show_plain_words_and_the_pace_clock(self):
        html = self.out["overviewProject"]
        self.assertIn("Today: 9 points of your weekly allowance", html)
        self.assertIn("This week: 62% of your weekly allowance", html)
        self.assertIn("At this pace the limit is reached about 16:40", html)
        self.assertIn("≈ 120k of 500k tokens", html)

    def test_overview_shows_the_inbox_preview_and_the_blocker(self):
        html = self.out["overviewProject"]
        self.assertIn("Open Inbox", html)
        self.assertIn("Missing fixture", html)
        self.assertIn("(blocks P0.8)", html)

    def test_activity_offers_undo_only_on_undoable_lines(self):
        html = self.out["activityProject"]
        self.assertEqual(html.count('data-action="undo-line"'), 1)
        self.assertIn('data-activity="a1"', html)
        self.assertNotIn('data-activity="a2"', html)

    def test_global_activity_merges_projects_newest_first(self):
        html = self.out["activityAll"]
        self.assertIn("P0.8 done", html)
        self.assertLess(html.index("P0.8 done"), html.index(">stop<"))

    def test_global_overview_has_one_card_per_project(self):
        html = self.out["overviewAll"]
        self.assertIn('href="#/p/splitnet/overview"', html)
        self.assertIn('href="#/p/quiet/overview"', html)


class SectionStaticTests(unittest.TestCase):

    def test_section_modules_exist_and_are_registered(self):
        routes = read(os.path.join(WEB, "js", "routes.js"))
        self.assertIn('module: "./views/inbox.js"', routes)
        self.assertIn('module: "./views/activity.js"', routes)
        self.assertIn('module: "./views/overview.js"', routes)
        for name in VIEWS:
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", "views", name)), name)

    def test_every_data_action_the_views_emit_is_handled_by_app(self):
        app = read(os.path.join(WEB, "js", "app.js"))
        emitted = set()
        for name in VIEWS:
            emitted.update(DATA_ACTION.findall(read(os.path.join(WEB, "js", "views", name))))
        self.assertTrue(emitted, "no data-action found")
        missing = sorted(action for action in emitted if ('"%s"' % action) not in app)
        self.assertEqual(missing, [])

    def test_views_use_only_the_dom_helpers_for_markup(self):
        for name in VIEWS:
            text = read(os.path.join(WEB, "js", "views", name))
            self.assertNotIn(".innerHTML", text, name)
            self.assertNotIn("insertAdjacentHTML", text, name)

    def test_answer_keys_are_bound_once_on_import(self):
        text = read(os.path.join(WEB, "js", "views", "inbox.js"))
        for key in ('"a"', '"1"', '"2"', '"3"', '"4"'):
            self.assertIn("bindKey(" + key, text)


if __name__ == "__main__":
    sys.exit(unittest.main())
