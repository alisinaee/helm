"""The Workflow view (WP48), rendered in node by tests/web/render_workflow.mjs from
tests/fixtures/workflow_snapshot.json.

Checks: the four cases (empty, running, blocked, handoff) render their lanes, bars, arrows and cards; every bar and card
is a focusable button with an aria-label and an SVG title; the Table has one row per job bar; the empty state reads as
the spec says; no inline style or inline handler is emitted; the escaped data stays escaped; the Stop and Start buttons
use data-wf-op (cmd.js), never a page action; the route, the section list and the sprite carry the new section; and
map.css stays within its 4.5 KB budget with the CSS total under the shared cap. The node checks are skipped when node
is not installed.
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
RENDER = os.path.join(TESTS, "web", "render_workflow.mjs")
FIXTURE = os.path.join(TESTS, "fixtures", "workflow_snapshot.json")
MAP_CSS_MAX = 4.5 * 1024
CSS_TOTAL_MAX = 72 * 1024  # raised with the R7.12 copy column (see test_shell.py)
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
OPEN_TAG = re.compile(r"<(g|rect|path|a|button)\b[^>]*data-wf-item=[^>]*>")
BAR_KEY = re.compile(r'data-wf-item="j:')


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def render():
    node = shutil.which("node")
    proc = subprocess.run([node, "--experimental-default-type=module", RENDER, WEB, FIXTURE],
                          capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("render_workflow.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def markup(out):
    """Every HTML string the harness produced, for the checks that apply to all of them."""
    found = []
    for case in out["cases"].values():
        found.extend([case["timeline"], case["map"], case["mapStacked"], case["table"]])
    found.extend(out["sections"].values())
    return found


class WorkflowViewTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed")
        cls.out = render()

    def test_the_four_cases_render_their_lanes(self):
        cases = self.out["cases"]
        self.assertTrue(cases["empty"]["empty"])
        self.assertEqual(cases["empty"]["lanes"], ["Head", "Queue", "Blocked"])
        self.assertIn("haiku", cases["running"]["lanes"])
        self.assertIn("Queue", cases["running"]["lanes"])
        self.assertIn("agy", cases["blocked"]["lanes"])
        self.assertIn("other", cases["blocked"]["lanes"])
        self.assertEqual(cases["handoff"]["jobs"], 4)

    def test_running_case_shows_live_bars_and_queued_items(self):
        timeline = self.out["cases"]["running"]["timeline"]
        self.assertIn("wf-live", timeline)
        self.assertIn("wf-pulse", timeline)
        self.assertIn("wf-b-queued", timeline)
        self.assertIn("wf-b-doing", timeline)
        self.assertIn('class="wf-now"', timeline)

    def test_blocked_case_shows_hatched_failed_and_blocked_items(self):
        timeline = self.out["cases"]["blocked"]["timeline"]
        self.assertIn("wf-b-blocked", timeline)
        self.assertIn('data-wf-item="b:beta:P2.2"', timeline)
        self.assertIn("wf-e-block", timeline)

    def test_handoff_case_draws_parent_to_child_arrows(self):
        timeline = self.out["cases"]["handoff"]["timeline"]
        self.assertIn('class="wf-edge wf-e-handoff"', timeline)
        self.assertIn('marker-end="url(#wf-arrow)"', timeline)

    def test_every_bar_and_card_is_a_labelled_focusable_button_with_a_title(self):
        for html in markup(self.out):
            for match in re.finditer(r"<g\b[^>]*data-wf-item=\"[^\"]+\"[^>]*>", html):
                opening = match.group(0)
                self.assertIn("aria-label=", opening, opening[:160])
                self.assertIn('tabindex="0"', opening, opening[:160])
                self.assertIn('role="button"', opening, opening[:160])
                close = html.find("</g>", match.end())
                self.assertIn("<title>", html[match.end():close], opening[:160])

    def test_table_has_one_row_per_job_bar(self):
        for name in ("running", "blocked", "handoff"):
            case = self.out["cases"][name]
            timeline_bars = len(BAR_KEY.findall(case["timeline"]))
            table_rows = case["table"].count("<tr><td>")
            self.assertEqual(table_rows, timeline_bars, name)
            self.assertEqual(table_rows, case["jobs"], name)

    def test_empty_state_reads_as_the_spec_says(self):
        empty = self.out["sections"]["empty"]
        self.assertIn("No jobs recorded yet.", empty)
        self.assertIn("roadmap job start", empty)
        self.assertIn('href="#/p/empty/agents"', empty)

    def test_no_inline_style_or_handler_in_any_output(self):
        for html in markup(self.out):
            found = INLINE.search(html)
            self.assertIsNone(found, html[found.start():found.start() + 80] if found else "")

    def test_data_from_the_snapshot_is_escaped(self):
        found = " ".join(markup(self.out))
        self.assertNotIn("<b>core</b>", found)
        self.assertIn("&lt;b&gt;core&lt;/b&gt;", found)
        self.assertNotIn("<i>work</i>", found)

    def test_stop_and_start_use_the_command_path(self):
        # Running jobs in the Table carry Stop. Start only appears in the strip once a todo task is selected, so the
        # module source is checked for it.
        self.assertIn('data-wf-op="task.stop"', self.out["sections"]["table"])
        source = read_text(os.path.join(WEB, "js", "views", "workflow.js"))
        self.assertIn('"task.start"', source)
        self.assertIn('"task.stop"', source)
        self.assertNotIn("data-action=", "".join(markup(self.out)))

    def test_detail_strip_and_table_use_the_shared_row_grid(self):
        timeline = self.out["sections"]["timeline"]
        self.assertIn('class="wf-detail row-grid wf-cols"', timeline)
        self.assertIn('class="rg-num num"', self.out["cases"]["running"]["table"])

    def test_views_and_ranges_are_links_in_the_url(self):
        timeline = self.out["sections"]["timeline"]
        self.assertIn('aria-current="page">Timeline', timeline)
        self.assertIn("#/p/alpha/workflow/map?f=range%3Aweek", timeline)
        self.assertIn("#/p/alpha/workflow/timeline?f=range%3Aall", timeline)

    def test_global_scope_has_one_lane_per_project(self):
        all_html = self.out["sections"]["all"]
        for name in ("Alpha", "Beta", "Gamma", "Empty app"):
            self.assertIn('title="' + name + '"', all_html)
        self.assertEqual(all_html.count('data-wf-item="j:'), 16)
        self.assertEqual(self.out["served"].count("alpha"), 1)

    def test_routes_register_the_section_after_agents(self):
        routes = read_text(os.path.join(WEB, "js", "routes.js"))
        self.assertRegex(routes, r'id: "agents"[^\n]*\n\s*\{ id: "workflow", label: "Workflow", icon: "workflow", '
                                 r'module: "\./views/workflow\.js"')

    def test_sprite_has_the_workflow_icon(self):
        self.assertIn('id="i-workflow"', read_text(os.path.join(WEB, "icons.svg")))

    def test_map_css_stays_within_budget_and_the_total_under_the_cap(self):
        css_dir = os.path.join(WEB, "css")
        sizes = {name: os.path.getsize(os.path.join(css_dir, name)) for name in os.listdir(css_dir)
                 if name.endswith(".css")}
        self.assertLessEqual(sizes["map.css"], MAP_CSS_MAX, "map.css is %d bytes" % sizes["map.css"])
        self.assertLessEqual(sum(sizes.values()), CSS_TOTAL_MAX, "web/css totals %d bytes" % sum(sizes.values()))

    def test_index_links_the_stylesheet_once(self):
        self.assertEqual(read_text(os.path.join(WEB, "index.html")).count('href="/css/map.css"'), 1)


if __name__ == "__main__":
    unittest.main()
