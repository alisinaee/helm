"""Copy-reference wiring for the roadmap views (R7.12 P4): Board, List, Tree, Roadmap (lanes and timeline) and Phases.

The views are rendered in node from the golden snapshot (with subtasks added in a temporary copy, so the subtask refs
are covered). Each rendered row or section must carry a copy-reference button with a valid rb: ref and an aria-label,
no ref or summary may hold an absolute path or "~", and no copy button may sit inside another button or link.
Skipped with a message when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
SNAPSHOT = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
VIEW_FILES = ["board.js", "list.js", "tasks.js", "tree.js", "roadmap.js", "phases.js"]
PROJECT = "splitnet"
REF_RE = re.compile(r"^rb:[a-z0-9-]+(/[a-z]+/[A-Za-z0-9._-]+)?$")
SUB_REF_RE = re.compile(r"^rb:splitnet/sub/[A-Za-z0-9._-]+\.s[1-9][0-9]*$")

NODE_SCRIPT = """
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const web = process.argv[1];
const raw = JSON.parse(readFileSync(process.argv[2], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const work = await load("views/work.js");
const roadmap = await load("views/roadmap.js");
const phases = await load("views/phases.js");
const now = Date.parse("2026-10-13T12:00:00Z");
const snap = Object.assign({ project: { id: "splitnet", title: "split-net" } }, raw);
const store = state.createStore();
store.projects = [{ id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 0,
  need_user: 0, errors_count: 0, stale: false }];
store.snapshots.splitnet = state.normalizeSnapshot(snap, now);
function vmOf(route, mode) {
  return state.buildViewModel(store, Object.assign({ name: "project", id: "splitnet", section: "work",
    view: null, item: null, filters: {} }, route), { mode: mode, open: {} }, now);
}
const out = {
  board: work.sectionView(vmOf({ view: "board" }, null)),
  list: work.sectionView(vmOf({ view: "list", filters: { g: "phase" } }, null)),
  tree: work.sectionView(vmOf({ view: "tree" }, null)),
  lanes: roadmap.sectionView(vmOf({ section: "roadmap", view: null }, null)),
  timeline: roadmap.sectionView(vmOf({ section: "roadmap", view: "timeline" }, null)),
  phases: phases.phasesSection(vmOf({ section: "overview" }, "expanded")),
};
console.log(JSON.stringify(out));
"""


def augmented_snapshot(path):
    """Write a copy of the golden snapshot with subtasks on two live tasks; return the live task count."""
    with open(SNAPSHOT, encoding="utf-8") as fh:
        raw = json.load(fh)
    live = [t for t in raw["tasks"] if t.get("state") != "deferred"]
    live[0]["subs"] = [{"t": "step one", "d": True}, {"t": "step two", "d": False}]
    live[1]["subs"] = [{"t": "only step", "d": False}]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    return len(live)


class CopyScan(HTMLParser):
    """Collects every copy-reference button, and whether it sits inside a button or an anchor."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buttons = []
        self.button_depth = 0
        self.anchor_depth = 0

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "button" and attr.get("data-action") == "copy-ref":
            self.buttons.append({
                "ref": attr.get("data-ref", ""),
                "sum": attr.get("data-sum", ""),
                "label": attr.get("aria-label", ""),
                "nested": self.button_depth > 0 or self.anchor_depth > 0,
            })
        if tag == "button":
            self.button_depth += 1
        elif tag == "a":
            self.anchor_depth += 1

    def handle_endtag(self, tag):
        if tag == "button":
            self.button_depth = max(0, self.button_depth - 1)
        elif tag == "a":
            self.anchor_depth = max(0, self.anchor_depth - 1)


def scan(html):
    parser = CopyScan()
    parser.feed(html)
    parser.close()
    return parser.buttons


def kind_of(ref):
    parts = ref.split("/")
    return parts[1] if len(parts) > 1 else "project"


class RefWiringP4Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the P4 ref wiring render check is skipped")
        cls.tmp = tempfile.mkdtemp(prefix="ref-p4-")
        path = os.path.join(cls.tmp, "snapshot.json")
        cls.live = augmented_snapshot(path)
        node = shutil.which("node")
        proc = subprocess.run(
            [node, "--input-type=module", "-e", NODE_SCRIPT, WEB, path],
            capture_output=True, text=True, check=False, timeout=120,
        )
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)
        cls.buttons = {name: scan(html) for name, html in cls.out.items()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmp", ""), ignore_errors=True)

    def kinds(self, name):
        counts = {}
        for b in self.buttons[name]:
            counts[kind_of(b["ref"])] = counts.get(kind_of(b["ref"]), 0) + 1
        return counts

    def test_views_render_with_copy_buttons(self):
        for name in self.out:
            self.assertGreater(len(self.out[name]), 300, name)
            self.assertGreater(len(self.buttons[name]), 0, name)

    def test_every_button_has_a_valid_ref_and_label(self):
        for name, buttons in self.buttons.items():
            for b in buttons:
                self.assertRegex(b["ref"], REF_RE, name)
                self.assertTrue(b["ref"].startswith("rb:" + PROJECT + "/"), name + " " + b["ref"])
                self.assertTrue(b["label"].startswith("Copy reference to "), name + " " + b["label"])

    def test_no_absolute_path_or_home_in_refs_or_summaries(self):
        for name, buttons in self.buttons.items():
            for b in buttons:
                for text in (b["ref"], b["sum"]):
                    self.assertNotIn("/Users/", text, name)
                    self.assertNotIn("~", text, name)

    def test_no_copy_button_inside_another_button_or_link(self):
        for name, buttons in self.buttons.items():
            for b in buttons:
                self.assertFalse(b["nested"], name + " " + b["ref"])

    def test_board_has_a_card_ref_per_task_and_a_ref_per_column(self):
        kinds = self.kinds("board")
        self.assertEqual(kinds.get("task"), self.live)
        self.assertEqual(kinds.get("section"), 4)

    def test_list_has_a_row_ref_per_task_and_a_ref_per_group(self):
        html = self.out["list"]
        rows = len(re.findall(r'<tr class="[^"]*" data-wk-task=', html))
        groups = len(re.findall(r'<tr class="wk-group-head">', html))
        kinds = self.kinds("list")
        self.assertEqual(kinds.get("task"), rows)
        self.assertEqual(kinds.get("section"), groups)
        self.assertGreater(groups, 1)

    def test_tree_has_task_sub_and_phase_refs(self):
        html = self.out["tree"]
        kinds = self.kinds("tree")
        self.assertEqual(kinds.get("task"), len(re.findall(r'class="wk-tree-task"', html)))
        self.assertEqual(kinds.get("sub"), len(re.findall(r'data-wk="sub"', html)))
        self.assertEqual(kinds.get("sub"), 3)
        self.assertEqual(kinds.get("phase", 0) + kinds.get("section", 0),
                         len(re.findall(r'<section class="wk-phase">', html)))
        for b in self.buttons["tree"]:
            if kind_of(b["ref"]) == "sub":
                self.assertRegex(b["ref"], SUB_REF_RE)

    def test_roadmap_lanes_have_a_phase_ref_and_a_card_ref_per_task(self):
        html = self.out["lanes"]
        kinds = self.kinds("lanes")
        self.assertEqual(kinds.get("phase"), len(re.findall(r'<li class="lane">', html)))
        self.assertEqual(kinds.get("task"), len(re.findall(r'<li class="rc ', html)))

    def test_roadmap_timeline_has_a_phase_ref_per_row(self):
        html = self.out["timeline"]
        kinds = self.kinds("timeline")
        self.assertEqual(kinds.get("phase"), len(re.findall(r'<li class="tl-row"', html)))
        self.assertNotIn("task", kinds)

    def test_phases_have_a_phase_ref_and_a_task_ref_per_row(self):
        html = self.out["phases"]
        kinds = self.kinds("phases")
        self.assertEqual(kinds.get("phase"), len(re.findall(r'<button type="button" class="phase-row', html)))
        self.assertEqual(kinds.get("task"), len(re.findall(r'<div class="task-row ', html)))

    def test_view_files_are_lint_clean_and_free_of_raw_markup(self):
        import importlib
        import sys
        sys.path.insert(0, os.path.join(REPO, "tools"))
        try:
            lint_js = importlib.import_module("lint_js")
        finally:
            sys.path.pop(0)
        issues = [i for i in lint_js.run(REPO) if any(("views/" + n) in i for n in VIEW_FILES)]
        self.assertEqual(issues, [])
        for name in VIEW_FILES:
            with open(os.path.join(WEB, "js", "views", name), encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotIn("innerHTML", text, name)
            self.assertNotIn(" style=", text, name)
            for number, line in enumerate(text.splitlines(), 1):
                self.assertLessEqual(len(line), 120, name + ":" + str(number))

    def test_title_edit_hook_is_kept(self):
        with open(os.path.join(WEB, "js", "views", "tasks.js"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('data-tt-id="', text)
        self.assertIn('role="button"', text)
        self.assertIn('document.addEventListener("dblclick"', text)
        self.assertIn('event.key !== "F2"', text)


if __name__ == "__main__":
    unittest.main()
