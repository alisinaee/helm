"""The Planner (R7.109): web/js/views/planner.js on the Head screen's layout and classes (.hd-* in head.css).

The markup comes from plannerHtml() and sectionView() run in node (no DOM) on a fake 3-level snapshot. The checks: one
table row per plan item (a tbody keyed by id) in plan order, the 7-cell header and rows, the indent only on the title
cell, the state chips and the done/total cell, the Accept button in its fixed column, the expandable toggle with
aria-expanded and aria-controls, the linked tasks as compact rows, the filter bar and the count line, the orphan tasks,
the pickers and the inline forms, the actions, the empty state, the in-place painting (parseOne and swapNode), and the
CSS rules (no new CSS, planner.css unchanged). Skipped when node is not installed.
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
MODULE = os.path.join(WEB, "js", "views", "planner.js")
HEAD_CSS = os.path.join(WEB, "css", "head.css")
sys.path.insert(0, os.path.join(REPO, "tools"))

ITEM = re.compile(r'<tbody class="hd-item[^"]*" id="pl-feat-([^"]+)"')
CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
ROW_CELLS = re.compile(r'<tr class="hd-row" data-id="[^"]+">(.*?)</tr>', re.S)

NODE_SCRIPT = ("import(process.argv[1]).then(function (m) {"
               " var cases = JSON.parse(process.argv[2]); var out = {};"
               " Object.keys(cases).forEach(function (k) {"
               " out[k] = cases[k].view ? m.sectionView(cases[k].vm)"
               " : m.plannerHtml(cases[k].snap, cases[k].state); });"
               " console.log(JSON.stringify(out)); });")


def node_or_skip():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed")
    return node


def run_cases(cases):
    proc = subprocess.run([node_or_skip(), "-e", NODE_SCRIPT, __import__("pathlib").Path(MODULE).as_uri(),
                           json.dumps(cases)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError("planner.js failed in node: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def row(fid, label, title, extra=None):
    base = {"id": fid, "label": label, "title": title, "phase": "R1", "done": 0, "total": 0, "blocked": 0,
            "state": "todo"}
    base.update(extra or {})
    return base


def snapshot():
    rows = [
        row("F1", "P0", "Research", {"state": "done", "done": 1, "total": 1, "acc": "brief and risks"}),
        row("F4", "P1", "Requirements", {"total": 2, "gaps": 1, "acc": "every ask has acceptance"}),
        row("F5", "P1.0", "Offline sync", {"parent": "F4", "ask": True, "total": 2, "acc": "edits merge"}),
        row("F6", "P1.1", "Export to PDF", {"parent": "F4", "ask": True, "state": "uncovered"}),
        row("F7", "P2", "Core engine", {"state": "doing", "total": 1}),
        row("F8", "P2.0", "Storage layer", {"parent": "F7", "state": "doing", "total": 1}),
        row("F9", "P2.0.0", "Schema and migrations", {"parent": "F8", "state": "doing", "total": 1}),
        row("F10", "P3", "Parked", {"state": "done", "accepted": "2026-10-01", "done": 1, "total": 1}),
    ]
    tasks = [
        {"id": "R1.1", "title": "Merge rules", "state": "todo", "phase": "R1", "feats": ["F5"]},
        {"id": "R1.2", "title": "Collect asks", "state": "todo", "phase": "R1", "feats": []},
        {"id": "R1.3", "title": "Wire export", "state": "todo", "phase": "R1", "feats": []},
        {"id": "R2.1", "title": "Schema", "state": "doing", "phase": "R1", "feats": ["F9", "F8", "F5"]},
        {"id": "R0.1", "title": "Write brief", "state": "done", "phase": "R1", "feats": ["F1"]},
    ]
    return {"tasks": tasks, "blocked": ["R2.1"], "features": {"rows": rows, "uncovered": ["F6"],
            "orphans": ["R1.2", "R1.3"], "counts": {}}}


def empty_snapshot():
    return {"tasks": [], "features": {"rows": [], "uncovered": [], "orphans": ["R1.2"], "counts": {}}}


STATE = {"status": "", "open": {}, "edit": None, "pick": None, "project": "demo", "focus": ""}


def st(**extra):
    out = dict(STATE)
    out["open"] = {}
    out.update(extra)
    return out


def body(html, fid):
    """The tbody of one plan item (its row and its detail)."""
    start = html.index('<tbody class="hd-item')
    start = html.index('id="pl-feat-%s"' % fid, start) if ('id="pl-feat-%s"' % fid) in html else -1
    if start < 0:
        return ""
    open_at = html.rindex("<tbody", 0, start)
    return html[open_at:html.index("</tbody>", start) + len("</tbody>")]


class PlannerViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        snap = snapshot()
        cls.out = run_cases({
            "defaultView": {"snap": snap, "state": st()},
            "allOpen": {"snap": snap, "state": st(open={"F1": True, "F4": True, "F5": True, "F7": True,
                                                        "F8": True, "F9": True})},
            "doing": {"snap": snap, "state": st(status="doing")},
            "waiting": {"snap": snap, "state": st(status="waiting")},
            "uncovered": {"snap": snap, "state": st(status="uncovered")},
            "rename": {"snap": snap, "state": st(edit={"kind": "rename", "id": "F5"},
                                                 open={"F4": True, "F5": True})},
            "addTop": {"snap": snap, "state": st(edit={"kind": "add", "id": ""})},
            "addSub": {"snap": snap, "state": st(edit={"kind": "add", "id": "F4"}, open={"F4": True})},
            "assign": {"snap": snap, "state": st(pick={"kind": "assign", "task": "R1.2"})},
            "link": {"snap": snap, "state": st(pick={"kind": "link", "id": "F6"}, open={"F4": True, "F6": True})},
            "focus": {"snap": snap, "state": st(focus="F9", open={"F7": True, "F8": True})},
            "empty": {"snap": empty_snapshot(), "state": st()},
            "noPick": {"view": True, "vm": {"route": {"name": "home", "id": None, "filters": {}, "section": "planner"},
                                            "projects": [{"id": "splitnet", "name": "Split net"}]}},
            "shell": {"view": True, "vm": {"route": {"name": "project", "id": "demo", "filters": {"f": "F9<x>"},
                                                     "section": "planner"}, "project": {"snapshot": snap}}},
        })

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

    def test_one_keyed_tbody_per_plan_item_in_plan_order(self):
        html = self.out["defaultView"]
        self.assertEqual(ITEM.findall(html), ["F1", "F4", "F5", "F6", "F7", "F8", "F10"])
        self.assertLess(html.index('id="pl-feat-F4"'), html.index('id="pl-feat-F5"'))

    def test_children_follow_only_when_their_parent_is_open(self):
        self.assertEqual(ITEM.findall(self.out["allOpen"]),
                         ["F1", "F4", "F5", "F6", "F7", "F8", "F9", "F10"])

    def test_header_has_the_head_columns_and_each_row_has_seven_cells(self):
        html = self.out["allOpen"]
        head = re.search(r"<thead><tr>(.*?)</tr></thead>", html, re.S).group(1)
        self.assertEqual(head.count("<th "), 7)
        for cls in ("hd-n", "hd-sumc", "hd-kind", "hd-stc", "hd-age", "hd-acc", "hd-cp"):
            self.assertIn('class="%s"' % cls, head)
        rows = ROW_CELLS.findall(html)
        self.assertEqual(len(rows), 8)
        for cells in rows:
            self.assertEqual(cells.count("<td "), 7)

    def test_indent_class_is_on_the_title_only(self):
        html = self.out["allOpen"]
        self.assertIn('<div class="hd-sum lvl0">', body(html, "F4"))
        self.assertIn('<div class="hd-sum lvl1">', body(html, "F5"))
        self.assertIn('<div class="hd-sum lvl2">', body(html, "F9"))

    def test_state_chips_gap_and_progress_cell(self):
        html = self.out["defaultView"]
        self.assertIn('chip chip-success">Done<', body(html, "F1"))
        self.assertIn('chip chip-warning">Gap<', body(html, "F4"))
        self.assertIn('<td class="hd-age rg-num"', body(html, "F4"))
        self.assertIn(">0/2</td>", body(html, "F4"))
        self.assertIn(">1/1</td>", body(html, "F1"))
        self.assertIn('chip chip-sonnet">Doing<', body(html, "F7"))

    def test_accept_button_only_on_done_unaccepted_items(self):
        html = self.out["defaultView"]
        self.assertIn('data-pl="accept-btn" data-id="F1"', body(html, "F1"))
        self.assertNotIn("accept-btn", body(html, "F4"))
        self.assertIn('aria-label="Accepted"', body(html, "F10"))
        self.assertNotIn("accept-btn", body(html, "F10"))

    def test_toggle_is_a_native_button_with_aria_and_controls(self):
        html = self.out["defaultView"]
        self.assertIn('class="hd-hit" data-pl="toggle" data-id="F4" aria-expanded="true" '
                      'aria-controls="pl-sub-F4"', html)
        self.assertIn('data-id="F7" aria-expanded="true"', html)
        self.assertNotIn('id="pl-feat-F9"', html)

    def test_linked_tasks_are_compact_rows_with_status_chips(self):
        html = self.out["allOpen"]
        self.assertEqual(html.count('data-pl="unlink" data-task="R2.1"'), 3)
        f5 = body(html, "F5")
        self.assertIn('<li class="hd-link">', f5)
        self.assertIn("chip chip-warning\">blocked<", f5)
        self.assertIn('href="#/p/demo/work/i/R1.1"', f5)

    def test_filter_bar_and_count_line(self):
        html = self.out["defaultView"]
        labels = ["All", "Doing", "Todo", "Done", "Waiting for your OK", "Uncovered"]
        self.assertEqual(html.count('data-pl="status"'), 6)
        for label in labels:
            self.assertIn("<span>%s</span>" % label, html)
        self.assertIn('data-val="" aria-pressed="true"', html)
        self.assertIn("Showing 7 of 8", html)
        self.assertIn("Showing 3 of 8", self.out["doing"])
        self.assertIn('data-val="doing" aria-pressed="true"', self.out["doing"])
        self.assertEqual(ITEM.findall(self.out["doing"]), ["F7", "F8", "F9"])
        self.assertEqual(ITEM.findall(self.out["waiting"]), ["F1"])
        self.assertIn('data-val="uncovered" aria-pressed="true"', self.out["uncovered"])
        self.assertEqual(ITEM.findall(self.out["uncovered"]), ["F4", "F6"])

    def test_orphans_have_one_assign_button_each_and_a_picker_on_demand(self):
        html = self.out["defaultView"]
        self.assertEqual(html.count('data-pl="assign-open"'), 2)
        self.assertNotIn('id="pl-pop"', html)
        pop = self.out["assign"]
        self.assertEqual(pop.count('data-pl="pick"'), 8)
        self.assertIn('data-val="F9"', pop)
        self.assertIn('data-focus="pl-pop-first"', pop)

    def test_link_picker_lists_unlinked_tasks_and_skips_full_ones(self):
        pop = self.out["link"][self.out["link"].index('id="pl-pop"'):]
        self.assertIn('data-val="R1.2"', pop)
        self.assertNotIn('data-val="R2.1"', pop)

    def test_every_item_action_is_in_the_detail(self):
        f5 = body(self.out["allOpen"], "F5")
        for text in ("Link tasks", "Add sub plan", "Rename", "Edit acceptance", "Not asked", "Move up",
                     "Move down", "Hold", "Remove"):
            self.assertIn(">" + text + "</button>", f5)
        self.assertIn('data-dir="up" disabled', f5)
        self.assertIn('data-dir="down">', f5)
        f4 = body(self.out["allOpen"], "F4")
        self.assertRegex(f4, r'data-pl="rm" data-id="F4"[^>]* disabled>Remove')
        self.assertIn('data-pl="add" data-id="F9" disabled>Add sub plan', self.out["allOpen"])

    def test_forms_exist_only_while_editing(self):
        self.assertNotIn("data-pl-form", self.out["defaultView"])
        rename = body(self.out["rename"], "F5")
        self.assertIn('value="Offline sync"', rename)
        self.assertIn('maxlength="80"', rename)
        self.assertIn('data-pl-form="edit"', self.out["addTop"])
        self.assertIn('name="ask"', self.out["addTop"])
        sub = self.out["addSub"]
        self.assertLess(sub.index('id="pl-feat-F4"'), sub.index("data-pl-form"))
        self.assertLess(sub.index("data-pl-form"), sub.index('id="pl-feat-F5"'))

    def test_focus_names_one_row_and_its_ancestors_stay_open(self):
        html = self.out["focus"]
        self.assertEqual(html.count("is-focus"), 1)
        self.assertIn('id="pl-feat-F9" data-id="F9"', html)
        self.assertIn('aria-expanded="true" aria-controls="pl-sub-F8"', html)

    def test_empty_state_and_no_table(self):
        empty = self.out["empty"]
        self.assertIn("No plan yet. Ask your agent to create the roadmap.", empty)
        self.assertIn('data-pl="add"', empty)
        self.assertNotIn("hd-tbl", empty)
        self.assertNotIn("pl-feat-", empty)

    def test_bad_focus_id_is_ignored_and_the_section_is_a_stable_shell(self):
        shell = self.out["shell"]
        self.assertIn('<section class="hd-screen" data-section="planner" data-project="demo"', shell)
        self.assertNotIn("is-focus", shell)

    def test_all_projects_scope_picks_a_project(self):
        html = self.out["noPick"]
        self.assertIn("Pick a project", html)
        self.assertIn('href="#/p/splitnet/planner"', html)

    def test_paint_is_in_place_by_id_with_parse_and_swap(self):
        with open(MODULE, encoding="utf-8") as fh:
            src = fh.read()
        for name in ("parseOne", "swapNode", "reconcileItems", "insertBefore", "data-section"):
            self.assertIn(name, src)
        self.assertNotIn("innerHTML", src)
        self.assertNotIn("<style", src)

    def test_no_new_css_and_head_css_stays_within_its_budget(self):
        self.assertLessEqual(os.path.getsize(HEAD_CSS), 6144)
        with open(os.path.join(WEB, "css", "planner.css"), encoding="utf-8") as fh:
            self.assertLessEqual(len(fh.read().encode("utf-8")), 4608)

    def test_lines_stay_within_120_columns(self):
        with open(MODULE, encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                self.assertLessEqual(len(line.rstrip("\n")), 120, number)

    def test_lint_is_clean_for_the_planner(self):
        import importlib
        lint_js = importlib.import_module("lint_js")
        issues = [issue for issue in lint_js.run(REPO) if "planner" in issue]
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
