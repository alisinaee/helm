"""The Workflow view (WP48), rendered in node by tests/web/render_workflow.mjs from
tests/fixtures/workflow_snapshot.json.

Checks: the four cases (empty, running, blocked, handoff) render their lanes, bars, arrows and cards; every bar and card
is a focusable button with an aria-label and an SVG title; the Table has one row per task; the empty state reads as
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
from tests.web.test_shell import CSS_TOTAL_MAX

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_workflow.mjs")
FIXTURE = os.path.join(TESTS, "fixtures", "workflow_snapshot.json")
MAP_CSS_MAX = 5.25 * 1024  # 5.25 KB since the phone-width rules (mahdi-mobile-optimize)
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
OPEN_TAG = re.compile(r"<(g|rect|path|a|button)\b[^>]*data-wf-item=[^>]*>")


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


with open(FIXTURE, encoding="utf-8") as _fh:
    FIXTURE_DATA = json.load(_fh)


class WorkflowViewTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed")
        cls.out = render()

    def test_the_four_cases_render_their_lanes(self):
        cases = self.out["cases"]
        self.assertTrue(cases["empty"]["empty"])
        self.assertEqual(cases["empty"]["lanes"], [])
        self.assertIn("haiku", cases["running"]["lanes"])
        self.assertIn("Queue", cases["running"]["lanes"])
        self.assertIn("agy", cases["blocked"]["lanes"])
        self.assertIn("cursor", cases["blocked"]["lanes"])
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

    def test_table_has_one_row_per_task(self):
        # The Table (R7.114) lists each task once: its rows are the distinct tasks of the case's jobs.
        for name in ("running", "blocked", "handoff"):
            case = self.out["cases"][name]
            raw = FIXTURE_DATA[name]
            tasks = {row[1] for row in raw["workflow"]["spans"] if row[1]}
            tasks |= {q["task"] for q in raw.get("queue", []) if q.get("task")}
            tasks |= {t for t in raw.get("blocked", []) if isinstance(t, str) and t}
            tasks = sorted(tasks)
            row_ids = re.findall(r'<tr><td class="wf-id">([^<]*)</td>', case["table"])
            self.assertEqual(sorted(row_ids), tasks, name)
            self.assertEqual(len(row_ids), len(set(row_ids)), name)

    def test_a_project_without_jobs_still_maps_its_tasks(self):
        # The Map is the default view and draws tasks, so a project with no job spans shows its flow, not the
        # "No jobs recorded yet." note (that note stays with the Timeline and the Table).
        empty = self.out["sections"]["empty"]
        self.assertIn('data-wf-view="map"', empty)
        self.assertIn("data-wf-map-host", empty)
        self.assertNotIn("No jobs recorded yet.", empty)

    def test_no_inline_style_or_handler_in_any_output(self):
        for html in markup(self.out):
            found = INLINE.search(html)
            self.assertIsNone(found, html[found.start():found.start() + 80] if found else "")

    def test_data_from_the_snapshot_is_escaped(self):
        found = " ".join(markup(self.out))
        self.assertNotIn("<b>core</b>", found)
        self.assertNotIn("<i>work</i>", found)

    def test_stop_and_start_use_the_command_path(self):
        # The Table's next action is a link (Open in Work, Answer, Retry). Stop and Start are in the strip and the
        # module source, so the source is checked for them.
        source = read_text(os.path.join(WEB, "js", "views", "workflow.js"))
        self.assertIn('"task.start"', source)
        self.assertIn('"task.stop"', source)
        self.assertNotIn("data-action=", "".join(markup(self.out)))

    def test_detail_strip_and_table_use_the_shared_row_grid(self):
        # The strip shows in the Table; the Map has none (a tap opens the right panel's Details instead).
        table = self.out["sections"]["table"]
        self.assertIn('class="wf-detail row-grid wf-cols"', table)
        self.assertNotIn('class="wf-detail', self.out["sections"]["map"])
        self.assertIn('class="rg-num num"', self.out["cases"]["running"]["table"])

    def test_the_map_is_the_default_view_and_views_are_links_in_the_url(self):
        # The harness renders the Map after the graph modules load (the second call), so the map section is checked.
        mapped = self.out["sections"]["map"]
        self.assertIn('aria-current="page">Map', mapped)
        self.assertIn("#/p/alpha/workflow/timeline?f=range%3Aweek", mapped)
        self.assertIn("#/p/alpha/workflow/table?f=range%3Aweek", mapped)
        self.assertIn("#/p/alpha/workflow/map?f=range%3Aweek", mapped)
        source = read_text(os.path.join(WEB, "js", "views", "workflow.js"))
        self.assertIn('return route.name === "project" ? "map" : "timeline";', source)

    def test_map_controls_are_labelled_buttons(self):
        mapped = self.out["sections"]["map"]
        for label in ("Zoom out", "Zoom in", "Fit to screen", "Centre on Now (N)", "Go to Start (S)",
                      "Show all phases"):
            self.assertIn('aria-label="' + label + '"', mapped)
        self.assertIn('data-wf-map-op="now"', mapped)
        self.assertIn('data-wf-map-op="start"', mapped)

    def test_map_state_is_in_the_f_param_and_the_breadcrumb_is_a_phase_list(self):
        source = read_text(os.path.join(WEB, "js", "views", "workflow.js"))
        self.assertIn("/^(st|ag|ph|all|x):(.*)$/", source)
        self.assertIn('data-wf-frame="', source)
        self.assertIn('(f.collapsed ? "+" : "-") + f.lane', source)
        self.assertIsNone(re.search(r"\bord:", source), "the old ord: token is gone")

    def test_legend_names_only_what_the_map_draws(self):
        mapped = self.out["sections"]["map"]
        self.assertNotIn("Sequence", mapped)
        self.assertIn("Dependency", mapped)
        self.assertIn("You are here (Now)", mapped)
        self.assertNotIn("Depends on", "".join(markup(self.out)))

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


class WorkflowMapTests(unittest.TestCase):
    """The Map (R7.14 E): the toolbar, the legend, the Now centring, the keys and the phase state in f=."""

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed")
        cls.out = render()
        cls.source = read_text(os.path.join(WEB, "js", "views", "workflow.js"))

    def test_toolbar_is_real_buttons_with_labels(self):
        mapped = self.out["sections"]["map"]
        for label, text in (("Fit to screen", "Fit"), ("Centre on Now (N)", "Now"), ("Go to Start (S)", "Start")):
            self.assertRegex(mapped, r'<button type="button" class="btn btn-small" data-wf-map-op="[a-z-]+" '
                                     r'aria-label="%s"[^>]*>%s</button>' % (re.escape(label), text))

    def test_map_legend_names_the_drawn_items_and_the_table_legend_has_no_edges(self):
        legend = re.search(r'<ul class="wf-legend".*?</ul>', self.out["sections"]["map"]).group(0)
        self.assertIn("You are here (Now)", legend)
        self.assertIn("Todo", legend)
        table = re.search(r'<ul class="wf-legend".*?</ul>', self.out["sections"]["table"]).group(0)
        self.assertNotIn("Handoff", table)
        self.assertNotIn("Sequence", table)

    def test_map_opens_centred_on_now_and_keeps_the_user_view_after(self):
        self.assertIn('api.centerOn("now", true)', self.source)
        self.assertIn("if (opening) openAtNow(api, st.flow);", self.source)
        self.assertIn("const view = opening ? undefined : store.view;", self.source)
        # The previous viewport is destroyed before the new one reads the live view.
        self.assertLess(self.source.index("activeMap.api.destroy()"), self.source.index("const view = opening"))

    def test_map_skips_the_timeline_model_and_builds_the_graph_once_without_filters(self):
        self.assertIn('const model = view === "map" ? { empty: false', self.source)
        self.assertIn("const graph = filtered ? kit.model.buildGraph(", self.source)

    def test_fold_taps_toggle_the_frame_through_the_node(self):
        self.assertIn('const fold = node.getAttribute("data-wf-fold");', self.source)

    def test_timeline_status_classes_go_through_esc(self):
        self.assertIn("'<g class=\"wf-bar wf-b-' + esc(it.status)", self.source)
        self.assertIn("'<g class=\"wf-mark wf-m-' + esc(m.status)", self.source)

    def test_n_and_s_keys_and_the_arrows_are_wired(self):
        self.assertIn("/^[nNsS]$/.test(e.key)", self.source)
        self.assertIn('mapOp(e.key === "n" || e.key === "N" ? "now" : "start")', self.source)
        self.assertIn('if (lastModel.view === "map") return;', self.source)

    def test_minimap_mounts_above_640_and_chips_replace_it_below(self):
        self.assertIn("mountMinimap(host.parentNode", self.source)
        self.assertIn('NARROW_Q = "(max-width: 640px)"', self.source)
        self.assertIn('<nav class="wfg-chips" aria-label="Phases">', self.source)
        self.assertIn('data-wf-frame="', self.source)

    def test_map_filters_and_phase_folds_ride_in_f(self):
        # The Status filter is a toolbar checkbox (R11.119); its token writes st: into the same f= hash.
        self.assertIn('data-tb-token="st:doing"', self.out["sections"]["map"])
        self.assertIn('class="tb" data-tb="wf"', self.out["sections"]["map"])
        self.assertIn('keep.push((f.collapsed ? "+" : "-") + f.lane);', self.source)
        self.assertIn("window.location.hash = mapHash(route, rangeOf(route), { x: keep.join(\"|\") });", self.source)

    def test_a_capped_or_folded_map_says_how_many_items_it_shows(self):
        self.assertIn('const countText = folded ? "Showing " + shown + " of " + matched + " items" +', self.source)
        self.assertIn('(flow.capped ? " (the view caps at " + flow.cap + ")" : "")', self.source)
        self.assertIn('mapTb = mapToolbarHtml(opts, phases, countText);', self.source)


if __name__ == "__main__":
    unittest.main()
