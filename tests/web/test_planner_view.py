"""The Planner v2 plan tree (R7.13 H5): rendered in node from a fake 3-level snapshot by tests/web/render_planner.mjs,
plus static checks on the CSS and the markup rules.

The checks: one grid row per plan item with the outline label, the indent only inside the title cell, the ask marker,
the progress and count cells, the gaps and state chips, the toggle with aria-expanded and aria-controls ids, the Work
link of an item (f=feat:<id>), the "waiting for your OK" list, orphan tasks with one small Assign button each and a
button popover (no native select), the menu items, the inline edit forms, the filters, the removed Est/Spent/Pri/Phase
filter, the empty state, and planner.css within its budget with no raw colours. Skipped when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_planner.mjs")
CSS = os.path.join(WEB, "css", "planner.css")
INDEX = os.path.join(WEB, "index.html")
sys.path.insert(0, os.path.join(REPO, "tools"))

ITEM = re.compile(r'<li id="pl-feat-([^"]+)" class="pl-item')
CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
ROW = re.compile(r'<div class="pl-row row-grid">(.*?)</div>', re.S)


def node_or_skip():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    return node


def run_section(vm):
    """sectionView(vm) run in node (no DOM, so no scroll). Returns the HTML string."""
    code = ("import(process.argv[1]).then(function (m) {"
            " console.log(JSON.stringify({html: m.sectionView(JSON.parse(process.argv[2]))})); });")
    module = os.path.join(WEB, "js", "views", "planner.js")
    proc = subprocess.run([node_or_skip(), "-e", code, Path(module).as_uri(), json.dumps(vm)],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError("sectionView failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)["html"]


def render_all():
    proc = subprocess.run([node_or_skip(), RENDER, WEB], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError("render_planner.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def item(html, fid):
    """The markup of the item row (the grid div) of one plan item."""
    start = html.index('<li id="pl-feat-%s" ' % fid)
    return html[start:html.index('<ul class="pl-sub"', start)]


class PlannerViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = render_all()

    def test_every_case_renders_and_controls_resolve(self):
        for name, html in self.out.items():
            self.assertTrue(html, name)
            ids = set(IDS.findall(html))
            for target in CONTROLS.findall(html):
                self.assertIn(target, ids, name + ": " + target)

    def test_no_inline_style_handler_script_or_native_select(self):
        for name, html in self.out.items():
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("<script", html, name)
            self.assertNotIn("<select", html, name)
            self.assertNotIn('role="button"', html, name)

    def test_tree_has_one_item_per_plan_row_in_order_with_outline_labels(self):
        html = self.out["defaultView"]
        self.assertEqual(ITEM.findall(html), ["F1", "F4", "F5", "F6", "F7", "F8", "F9", "F10"])
        for label in ("P0", "P1", "P1.0", "P1.1", "P2", "P2.0", "P2.0.0", "P3"):
            self.assertIn('<span class="rg-t pl-lb">%s</span>' % label, html)
        self.assertLess(html.index('id="pl-feat-F5"'), html.index('id="pl-feat-F6"'))

    def test_every_row_is_one_grid_with_twelve_cells_and_the_header_matches(self):
        html = self.out["defaultView"]
        head = re.search(r'<div class="pl-row row-grid pl-head rg-head" aria-hidden="true">(.*?)</div>', html, re.S)
        self.assertEqual(head.group(1).count("<span"), 12)
        row = item(html, "F4")
        self.assertEqual(row.count('<div class="pl-row row-grid">'), 1)
        for cls in ("pl-lb", "pl-id", "pl-main", "pl-ph", "pl-bar", "pl-ct", "pl-gp", "pl-ok", "pl-more", "ref-copy"):
            self.assertIn(cls, row)
        self.assertNotIn("<select", row)

    def test_indent_class_is_on_the_title_cell_only(self):
        html = self.out["allOpen"]
        self.assertIn('class="pl-main lvl0"', item(html, "F4"))
        self.assertIn('class="pl-main lvl1"', item(html, "F5"))
        self.assertIn('class="pl-main lvl2"', item(html, "F9"))
        self.assertEqual(len(re.findall(r"lvl[12]", html.replace("pl-main lvl", "X"))), 0)

    def test_columns_est_spent_pri_and_the_phase_filter_are_gone(self):
        for name, html in self.out.items():
            for word in ("Est K", "Spent K", ">Pri<", "filter-phase", "Phase</label>"):
                self.assertNotIn(word, html, name)

    def test_ask_marker_progress_count_gaps_and_state(self):
        html = self.out["defaultView"]
        f5 = item(html, "F5")
        self.assertIn('aria-label="you asked"', f5)
        self.assertNotIn("you asked", item(html, "F4"))
        self.assertIn("edits merge on reconnect", f5)
        self.assertIn('data-pct="0"', f5)
        self.assertIn('data-pct="100"', item(html, "F1"))
        self.assertIn(">0/2<", f5)
        f4 = item(html, "F4")
        self.assertIn('<span class="rg-num pl-gp">1</span>', f4)
        self.assertIn('chip chip-warning">gap<', f4)
        self.assertIn(">uncovered<", item(html, "F6"))
        self.assertIn('<span class="rg-num pl-gp"></span>', item(html, "F1"))

    def test_item_and_count_link_to_work_filtered_to_the_subtree(self):
        f4 = item(self.out["defaultView"], "F4")
        self.assertEqual(f4.count('href="#/p/demo/work?f=feat%3AF4"'), 2)

    def test_toggle_has_aria_and_opens_by_default_only_at_the_top_level(self):
        html = self.out["defaultView"]
        self.assertIn('aria-expanded="true" aria-controls="pl-sub-F4"', html)
        self.assertIn('aria-expanded="false" aria-controls="pl-sub-F5"', html)
        self.assertIn('<ul class="pl-sub" id="pl-sub-F5" aria-label="Inside F5" hidden>', html)
        self.assertNotIn('id="pl-sub-F4" aria-label="Inside F4" hidden', html)
        opened = self.out["allOpen"]
        self.assertIn('<ul class="pl-sub" id="pl-sub-F5" aria-label="Inside F5">', opened)
        self.assertIn('data-task="R1.1"', opened)

    def test_shared_task_is_listed_under_each_of_its_features(self):
        html = self.out["allOpen"]
        self.assertEqual(html.count('data-pl="unlink" data-task="R2.1"'), 3)

    def test_waiting_for_your_ok_lists_done_and_unaccepted_only(self):
        html = self.out["defaultView"]
        panel = html[html.index('id="pl-panel-wait"'):]
        panel = panel[:panel.index("</ul>")]
        self.assertIn("P0 F1", panel)
        self.assertIn('data-pl="accept-btn" data-id="F1"', panel)
        self.assertEqual(panel.count("pl-li"), 1)
        self.assertIn("1 waiting for your OK", html)
        self.assertNotIn("F10", panel)

    def test_orphans_have_one_small_assign_button_each(self):
        html = self.out["defaultView"]
        self.assertEqual(html.count('data-pl="assign-open"'), 2)
        self.assertIn('aria-haspopup="true" aria-expanded="false"', html)
        self.assertNotIn('aria-controls="pl-pop"', html)

    def test_assign_opens_a_button_popover_of_plan_items(self):
        html = self.out["assign"]
        self.assertEqual(len(re.findall(r'id="pl-pop"', html)), 1)
        pop = html[html.index('id="pl-pop"'):]
        pop = pop[:pop.index("Close</button>")]
        self.assertEqual(pop.count('data-pl="pick"'), 8)
        self.assertIn('data-val="F9"', pop)
        self.assertIn('aria-controls="pl-pop"', html)
        self.assertIn('data-focus="pl-pop-first"', pop)

    def test_link_popover_lists_unlinked_tasks_with_room_and_skips_full_ones(self):
        html = self.out["link"]
        pop = html[html.index('id="pl-pop"'):]
        self.assertIn('data-val="R1.2"', pop)
        self.assertNotIn('data-val="R2.1"', pop)

    def test_menu_has_every_action_and_disables_by_rule(self):
        html = self.out["menu"]
        menu = html[html.index('id="pl-menu-F5"'):]
        menu = menu[:menu.index("</div>")]
        for text in ("Add sub plan", "Rename", "Edit acceptance", "Not asked", "Link tasks", "Move up", "Move down",
                     "Hold", "Remove"):
            self.assertIn(">" + text + "<", menu)
        self.assertIn('data-dir="up" disabled', menu)
        self.assertIn('data-dir="down">', menu)
        self.assertIn('aria-controls="pl-menu-F5"', html)
        self.assertNotIn('id="pl-menu-F4"', html)
        first = self.out["menuFirst"]
        self.assertIn('data-dir="up" disabled', first)
        self.assertIn('data-dir="down">', first)
        deep = self.out["menuDeep"]
        self.assertIn('data-pl="add" data-id="F9" disabled>Add sub plan', deep)
        self.assertRegex(first, r'data-pl="rm" data-id="F1"[^>]* disabled>Remove')

    def test_inline_forms_exist_only_while_editing(self):
        self.assertNotIn("pl-edit", self.out["defaultView"])
        rename = self.out["rename"]
        self.assertIn('value="Offline sync"', rename)
        self.assertIn('maxlength="80"', rename)
        self.assertIn('data-pl-form="edit"', self.out["addTop"])
        self.assertIn('name="ask"', self.out["addTop"])
        sub = self.out["addSub"]
        self.assertLess(sub.index('id="pl-sub-F4"'), sub.index("pl-edit"))
        self.assertLess(sub.index("pl-edit"), sub.index('id="pl-feat-F5"'))

    def test_status_chips_and_unaccepted_filter(self):
        html = self.out["defaultView"]
        self.assertEqual(html.count('data-pl="status"'), 6)
        self.assertIn('data-val="" aria-pressed="true"', html)
        self.assertIn('data-pl="unaccepted"', html)
        doing = self.out["doingFilter"]
        self.assertIn('data-val="doing" aria-pressed="true"', doing)
        self.assertEqual(ITEM.findall(doing), ["F7", "F8", "F9"])
        self.assertEqual(ITEM.findall(self.out["unaccepted"])[0], "F1")
        self.assertNotIn('id="pl-feat-F10"', self.out["unaccepted"])

    def test_no_match_and_empty_state(self):
        self.assertIn("No plan items match these filters.", self.out["noMatch"])
        empty = self.out["empty"]
        self.assertIn("No plan yet. Ask your agent to create the roadmap.", empty)
        self.assertIn('data-pl="add"', empty)
        self.assertNotIn("pl-item", empty)

    def test_accept_box_reflects_the_stored_acceptance(self):
        html = self.out["defaultView"]
        self.assertNotIn(" checked", item(html, "F1"))
        self.assertIn(" checked", item(html, "F10"))
        self.assertIn('data-state="done"', item(html, "F1"))

    def test_focus_opens_ancestors_and_highlights_the_named_item(self):
        vm = {"route": {"name": "project", "id": "demo", "filters": {"f": "F9"}, "section": "planner"},
              "project": {"snapshot": json.loads(self.snapshot_json())}}
        html = run_section(vm)
        self.assertIn('class="pl-item is-doing is-focus"', html)
        self.assertEqual(html.count("is-focus"), 1)
        self.assertIn('aria-expanded="true" aria-controls="pl-sub-F8"', html)
        self.assertIn('href="#/p/demo/work?f=feat%3AF9"', html)

    def test_focus_ignores_a_bad_id(self):
        vm = {"route": {"name": "project", "id": "demo", "filters": {"f": "F9<x>"}, "section": "planner"},
              "project": {"snapshot": json.loads(self.snapshot_json())}}
        self.assertNotIn("is-focus", run_section(vm))

    @staticmethod
    def snapshot_json():
        rows = [{"id": "F7", "label": "P0", "title": "Core", "state": "doing", "done": 0, "total": 1, "blocked": 0},
                {"id": "F8", "label": "P0.0", "title": "Store", "parent": "F7", "state": "doing", "done": 0,
                 "total": 1, "blocked": 0},
                {"id": "F9", "label": "P0.0.0", "title": "Schema", "parent": "F8", "state": "doing", "done": 0,
                 "total": 1, "blocked": 0}]
        return json.dumps({"tasks": [], "features": {"rows": rows, "uncovered": [], "orphans": []}})

    def test_all_projects_scope_picks_a_project(self):
        vm = {"route": {"name": "home", "id": None, "filters": {}, "section": "planner"},
              "projects": [{"id": "splitnet", "name": "Split net"}, {"id": "roadmap", "name": "Roadmap"}]}
        html = run_section(vm)
        self.assertIn("Pick a project", html)
        self.assertIn('href="#/p/splitnet/planner"', html)

    def test_planner_css_is_small_and_uses_tokens_only(self):
        with open(CSS, encoding="utf-8") as fh:
            css = fh.read()
        self.assertLessEqual(len(css.encode("utf-8")), 4608)
        self.assertIsNone(HEX.search(css))
        self.assertIn("--rg: 24px 56px 40px minmax(0, 1fr) 48px 120px 64px 40px 76px 40px 32px", css)
        self.assertIn(".lvl1", css)
        self.assertIn(".lvl2", css)
        self.assertIn("max-width: 639px", css)

    def test_index_links_the_stylesheet_once(self):
        with open(INDEX, encoding="utf-8") as fh:
            index = fh.read()
        self.assertEqual(index.count('href="/css/planner.css"'), 1)

    def test_lint_is_clean_for_the_planner(self):
        import importlib
        lint_js = importlib.import_module("lint_js")
        issues = [issue for issue in lint_js.run(REPO) if "planner" in issue]
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
