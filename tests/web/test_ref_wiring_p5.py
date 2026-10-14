"""Checks for the copy-reference buttons in the home views (R7.12, package P5): the Overview cards and blocker rows, and
the Needs you and Next up sections. A small node script (written to a temp dir) renders the views from the golden
snapshot, with one blocked task that needs the person, and prints the HTML. Each copy button must carry a
data-action="copy-ref", a valid rb: ref, an aria-label, a summary with no absolute path or "~", and must not sit inside
another button or link. The node checks are skipped when node is not installed.
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
GOLDEN = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
REF_RE = re.compile(r"^rb:[a-z0-9-]+(/[a-z]+/[A-Za-z0-9._-]+)?$")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track",
        "wbr", "use", "path", "rect", "circle", "line", "polyline", "polygon"}

NODE_SCRIPT = """
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const web = process.argv[2];
const raw = JSON.parse(readFileSync(process.argv[3], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const overview = await load("views/overview.js");
const home = await load("views/home.js");
const now = Date.parse("2026-10-13T12:00:00Z");
const s = state.createStore();
s.projects = [{ id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 0, need_user: 1,
  errors_count: 0, stale: false }];
s.snapshots.splitnet = state.normalizeSnapshot(Object.assign({ project: { id: "splitnet", title: "split-net" } }, raw),
  now);
s.usage = state.normalizeUsage({ weeklyPercent: 62, source: "fixture", ageS: 60 }, now);
const prefs = { mode: null, open: {} };
const vmOf = (r) => {
  const vm = state.buildViewModel(s, r, prefs, now);
  const all = (s.projects || []).map((p) => s.snapshots[p.id]).filter(Boolean);
  vm.snapshotList = r.name === "project" ? [s.snapshots[r.id]].filter(Boolean) : all;
  vm.control = null;
  return vm;
};
const route = (name, id) => ({ name: name, id: id, section: "overview", view: null, item: null, filters: {} });
console.log(JSON.stringify({
  overview: overview.sectionView(vmOf(route("project", "splitnet"))),
  project: home.projectView(vmOf(route("project", "splitnet"))),
  all: overview.sectionView(vmOf(route("home", null))),
}));
"""


class CopyButtons(HTMLParser):
    """Collects every copy-ref button with its attributes, and whether it sits inside a button or a link."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        attrs = dict(attrs)
        if attrs.get("data-action") == "copy-ref":
            nested = "button" in self.stack or "a" in self.stack
            self.buttons.append({"attrs": attrs, "nested": nested})
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        return

    def handle_endtag(self, tag):
        if tag in VOID or tag not in self.stack:
            return
        while self.stack and self.stack.pop() != tag:
            pass


def scan(html):
    parser = CopyButtons()
    parser.feed(html)
    parser.close()
    return parser.buttons


def render():
    node = shutil.which("node")
    with tempfile.TemporaryDirectory() as tmp:
        with open(GOLDEN, encoding="utf-8") as fh:
            raw = json.load(fh)
        # One open task that needs the person and is blocked, so the blocker row and Needs you have a task.
        task = next(t for t in raw["tasks"] if t.get("state") != "done")
        task["state"] = "doing"
        task["needsUser"] = True
        task["title"] = "Planner filters"
        raw["blocked"] = [task["id"]]
        data = os.path.join(tmp, "snapshot.json")
        with open(data, "w", encoding="utf-8") as fh:
            json.dump(raw, fh)
        script = os.path.join(tmp, "render_ref_p5.mjs")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(NODE_SCRIPT)
        proc = subprocess.run([node, script, WEB, data], capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("render failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout), task["id"]


class RefWiringP5Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the view render checks are skipped")
        cls.out, cls.task_id = render()

    def assertGoodButtons(self, name, html):
        buttons = scan(html)
        for button in buttons:
            attrs = button["attrs"]
            with self.subTest(view=name, ref=attrs.get("data-ref")):
                self.assertFalse(button["nested"], "copy button sits inside a button or link")
                self.assertRegex(attrs.get("data-ref", ""), REF_RE)
                self.assertTrue(attrs.get("data-ref", "").startswith("rb:splitnet/"))
                self.assertTrue(attrs.get("aria-label", "").startswith("Copy reference to "))
                self.assertNotIn("/Users/", attrs.get("data-ref", ""))
                self.assertNotIn("~", attrs.get("data-ref", ""))
                self.assertNotIn("/Users/", attrs.get("data-sum", ""))
                self.assertNotIn("~", attrs.get("data-sum", ""))
                self.assertIn("ref-copy", attrs.get("class", ""))
        return buttons

    def refs(self, name):
        return {b["attrs"]["data-ref"] for b in self.assertGoodButtons(name, self.out[name])}

    def test_overview_cards_are_section_refs(self):
        refs = self.refs("overview")
        for card in ("inbox", "meters", "blockers", "activity"):
            self.assertIn("rb:splitnet/section/overview." + card, refs)

    def test_overview_next_up_is_a_section_ref(self):
        self.assertIn("rb:splitnet/section/next.next", self.refs("overview"))

    def test_blocker_row_has_a_task_ref_with_the_state_summary(self):
        buttons = scan(self.out["overview"])
        task = [b for b in buttons if b["attrs"].get("data-ref") == "rb:splitnet/task/" + self.task_id]
        self.assertEqual(len(task), 1)
        self.assertIn('status=doing', task[0]["attrs"]["data-sum"])
        self.assertIn('"Planner filters"', task[0]["attrs"]["data-sum"])
        self.assertIn('Copy reference to Planner filters', task[0]["attrs"]["aria-label"])

    def test_project_view_needs_you_and_next_are_section_refs(self):
        refs = self.refs("project")
        self.assertIn("rb:splitnet/section/needsyou.needs", refs)
        self.assertIn("rb:splitnet/section/next.next", refs)

    def test_all_projects_overview_has_no_copy_buttons(self):
        # No single project slug there, so no ref can be formed (the spec gives none for the All view).
        self.assertEqual(scan(self.out["all"]), [])

    def test_no_copy_button_is_nested_in_a_toggle_or_link(self):
        for name, html in self.out.items():
            self.assertFalse(any(b["nested"] for b in scan(html)), name)


if __name__ == "__main__":
    unittest.main()
