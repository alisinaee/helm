"""Checks for the Roadmap section, and the Overview sections restored in WP32.

The views are plain functions that return HTML strings. tests/web/render_plan.mjs renders them in node from the golden
snapshot and from a synthetic one that carries a blocker, an approved phase, an unapproved phase with a budget, a
deferred task and a title that needs escaping. The checks: lanes list open tasks in plan order; the Approve button only
shows on unapproved phases; a blocker marks its task Blocked; the Up and Down buttons are disabled at the ends and
every draggable card has them (drag is never the only path); the timeline bar widths follow the estimates; the empty
states use the spec words; the Overview has the restored sections; every data-action these views emit is handled by app.js; and the
plan.css budget and the route, dispatch and Alt-key wiring hold. The node checks are skipped when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_plan.mjs")
GOLDEN = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
PLAN_CSS = os.path.join(WEB, "css", "plan.css")
CSS_BUDGET = 4096  # R10.38 lanes redesign

CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
DATA_ACTION = re.compile(r'data-action=\\?"([a-z-]+)')

SYNTH = {
    "project": {"id": "splitnet", "title": "split-net"},
    "phases": [
        {"id": "P1", "name": "Foundations", "state": "partial", "done": 1, "total": 3, "progress": 0.33,
         "only_deferred": False, "deferred": 0, "deferred_k": 0, "remaining_k": 45, "running": [], "recent": [],
         "approved": False},
        {"id": "P2", "name": "Routing <b>live</b>", "state": "todo", "done": 0, "total": 2, "progress": 0.0,
         "only_deferred": False, "deferred": 1, "deferred_k": 10, "remaining_k": 80, "running": [], "recent": [],
         "approved": True},
        {"id": "P3", "name": "Later", "state": "todo", "done": 0, "total": 0, "progress": None,
         "only_deferred": True, "deferred": 2, "deferred_k": 30, "remaining_k": None, "running": [], "recent": [],
         "approved": False},
    ],
    "tasks": [
        {"id": "P1.1", "title": "Scaffold", "phase": "P1", "state": "done", "model": "haiku", "thinking": "low",
         "tokensK": 20.0, "check": "none", "checkK": 0.0, "needsUser": False, "note": ""},
        {"id": "P1.2", "title": "Data model", "phase": "P1", "state": "partial", "model": "sonnet",
         "thinking": "medium", "tokensK": 40.0, "check": "none", "checkK": 0.0, "needsUser": False, "note": ""},
        {"id": "P1.3", "title": "Hosting account", "phase": "P1", "state": "todo", "model": "haiku",
         "thinking": "low", "tokensK": 5.0, "check": "none", "checkK": 0.0, "needsUser": True, "note": ""},
        {"id": "P2.1", "title": "Router <i>core</i>", "phase": "P2", "state": "todo", "model": "opus",
         "thinking": "high", "tokensK": 80.0, "check": "none", "checkK": 0.0, "needsUser": False, "note": ""},
        {"id": "P2.2", "title": "Parked item", "phase": "P2", "state": "deferred", "model": "haiku",
         "thinking": "low", "tokensK": 10.0, "check": "none", "checkK": 0.0, "needsUser": False, "note": ""},
    ],
    "blocked": ["P2.1"],
    "issues": [
        {"id": "I1", "title": "Missing fixture", "kind": "blocker", "sev": 1, "status": "open", "tasks": ["P2.1"]},
        {"id": "I2", "title": "Slow sync", "kind": "bug", "sev": 2, "status": "doing", "tasks": []},
    ],
    "budget": {"limits": {}, "total": {}, "tasks": {}, "models": {}, "spent": {},
               "phases": {"P1": {"spent": 30.0, "limit": 100.0, "pct": 30.0},
                          "P2": {"spent": 0.0, "limit": None, "pct": None}}},
    "summary": {"tokens_left_k": 125.0},
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
        raise AssertionError("render_plan.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class PlanRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the Roadmap render checks are skipped")
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

    def test_every_data_action_is_handled_by_app_js(self):
        app = read(os.path.join(WEB, "js", "app.js"))
        emitted = set()
        for html in self.out.values():
            emitted.update(DATA_ACTION.findall(html))
        self.assertIn("plan-move", emitted)
        for action in sorted(emitted):
            self.assertIn('"' + action + '"', app, action)

    def test_lanes_list_open_tasks_in_plan_order(self):
        html = self.out["lanesSynth"]
        self.assertIn('data-task="P1.2"', html)
        self.assertLess(html.index('data-task="P1.2"'), html.index('data-task="P1.3"'))
        self.assertNotIn('data-task="P1.1"', html)  # done tasks are not listed, as in `roadmap plan view`

    def test_approve_only_on_unapproved_phases(self):
        html = self.out["lanesSynth"]
        self.assertIn('data-action="phase-approve" data-phase="P1"', html)
        self.assertNotIn('data-action="phase-approve" data-phase="P2"', html)
        self.assertIn("Approved", html)

    def test_blocked_task_carries_the_badge(self):
        html = self.out["lanesSynth"]
        self.assertIn('class="rc is-todo is-blocked" draggable="true" tabindex="0" data-task="P2.1"', html)
        self.assertIn('class="rc is-partial" draggable="true" tabindex="0" data-task="P1.2"', html)
        self.assertIn(">blocked</span>", html)

    def test_drag_has_a_button_path_for_every_card(self):
        html = self.out["lanesSynth"]
        cards = html.count('draggable="true"')
        self.assertEqual(cards, 4)
        self.assertEqual(html.count('data-dir="up"'), cards)
        self.assertEqual(html.count('data-dir="down"'), cards)

    def test_move_buttons_disabled_at_the_ends_of_a_phase(self):
        html = self.out["lanesSynth"]
        self.assertIn('data-task="P1.2" data-dir="up" aria-label="Move P1.2 up" disabled', html)
        self.assertIn('data-task="P1.3" data-dir="down" aria-label="Move P1.3 down" disabled', html)
        self.assertNotIn('data-task="P1.3" data-dir="up" aria-label="Move P1.3 up" disabled', html)

    def test_timeline_bar_is_proportional_and_spent_is_filled(self):
        html = self.out["timelineSynth"]
        # Estimates: P1 = 20 + 40 + 5 = 65k, P2 = 80k (deferred excluded), the largest bar is P2.
        self.assertIn('data-pct="81.25"', html)
        self.assertIn('data-pct="100"', html)
        self.assertIn('data-pct="46.15', html)
        self.assertIn("est ~65k · spent 30k", html)
        self.assertLess(html.index("Foundations"), html.index("Routing"))

    def test_timeline_phase_without_estimate_has_no_bar(self):
        html = self.out["timelineSynth"]
        self.assertIn("no estimate", html)

    def test_lane_stats_show_counts_not_money(self):
        html = self.out["lanesSynth"]
        self.assertIn(" open</span>", html)
        self.assertNotIn("budget 100k", html)  # estimates and spend live in the Timeline only (R7.110)

    def test_phase_name_is_escaped(self):
        html = self.out["lanesSynth"]
        self.assertIn("Routing &lt;b&gt;live&lt;/b&gt;", html)
        self.assertNotIn("<b>live", html)

    def test_task_title_is_escaped(self):
        self.assertIn("Router &lt;i&gt;core&lt;/i&gt;", self.out["lanesSynth"])

    def test_empty_states_use_the_spec_words(self):
        self.assertIn("No plan yet. Ask the lead to run plan import.", self.out["lanesEmpty"])
        self.assertIn("The roadmap belongs to one project.", self.out["roadmapAll"])

    def test_loading_roadmap_shows_a_skeleton(self):
        self.assertIn('aria-busy="true"', self.out["roadmapLoading"])

    def test_overview_restores_the_dropped_sections(self):
        html = self.out["overviewGolden"]
        for title in ("Phases", "Next up", "Recent progress", "Legend", "Open Roadmap"):
            self.assertIn(title, html)
        self.assertIn("Extras", html)

    def test_overview_sections_fold_like_the_rest(self):
        html = self.out["overviewGolden"]
        self.assertIn('data-action="toggle-section" data-section="next"', html)
        self.assertIn('data-action="toggle-section" data-section="legend"', html)


class PlanStaticTests(unittest.TestCase):

    def test_plan_css_is_within_budget(self):
        self.assertLessEqual(os.path.getsize(PLAN_CSS), CSS_BUDGET)

    def test_routes_register_both_modules(self):
        routes = read(os.path.join(WEB, "js", "routes.js"))
        self.assertIn('"./views/roadmap.js"', routes)
        self.assertNotIn('"./views/issues.js"', routes)
        for name in ("roadmap.js",):
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", "views", name)), name)

    def test_app_dispatches_the_roadmap_actions(self):
        app = read(os.path.join(WEB, "js", "app.js"))
        self.assertIn('"plan-move"', app)
        self.assertIn('"phase-approve"', app)
        self.assertIn('"./views/roadmap.js"', app)

    def test_alt_arrow_keys_are_bound_by_the_roadmap(self):
        keys = read(os.path.join(WEB, "js", "keys.js"))
        self.assertIn('"Alt+" + event.key', keys)
        roadmap = read(os.path.join(WEB, "js", "views", "roadmap.js"))
        self.assertIn('bindKey("Alt+ArrowUp"', roadmap)
        self.assertIn('bindKey("Alt+ArrowDown"', roadmap)

    def test_reorder_uses_plan_move_only(self):
        roadmap = read(os.path.join(WEB, "js", "views", "roadmap.js"))
        self.assertIn('run("plan.move"', roadmap)
        self.assertIn('run("phase.approve"', roadmap)
        self.assertNotIn("plan.import", roadmap)


if __name__ == "__main__":
    unittest.main()
