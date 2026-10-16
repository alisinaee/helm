"""Copy-reference buttons in the item views (R7.12 P6): inbox, rules and projects.

The views are rendered in node from the golden snapshot with a few issues, questions and rules added
(tests/web/ref_wiring node script below, run with --input-type=module). The checks: each row (question, rule,
project) and each section header (inbox.questions, rules.list) carries a
data-action="copy-ref" button with a valid rb: ref and an aria-label; no ref or summary holds an absolute path or "~";
and no copy button sits inside another button or link. Skipped with a message when node is not installed.
"""

import html.parser
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
GOLDEN = os.path.join(TESTS, "fixtures", "golden_snapshot.json")
REF_RE = re.compile(r"^rb:[a-z0-9-]+(/[a-z]+/[A-Za-z0-9._-]+)?$")
COPY = re.compile(
    r'<button type="button" class="ref-copy" data-action="copy-ref" data-ref="([^"]*)" data-sum="[^"]*" '
    r'aria-label="Copy reference to [^"]*">'
)

NODE_SCRIPT = r"""
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const web = process.env.WEB;
const golden = JSON.parse(readFileSync(process.env.GOLDEN, "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const inbox = await load("views/inbox.js");
const rules = await load("views/rules.js");
const projects = await load("views/projects.js");

const now = Date.parse("2026-10-13T12:00:00Z");
const extra = {
  questions: [
    { id: "Q1", task: "", text: "Ship now?", opts: ["yes", "no"], def: "yes", block: true, timeoutS: null,
      status: "open", asked: null, answer: null, answered: null },
  ],
  rules: [
    { id: "R1", scope: "lead", kind: "do", text: "Keep the plan small", value: null },
    { id: "R2", scope: "haiku", kind: "budget", text: "Cap edits", value: 20 },
  ],
};
const raw = Object.assign({}, golden, extra, { project: { id: "splitnet", title: "split-net" } });
const store = state.createStore();
store.projects = [
  { id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 0, need_user: 1, errors_count: 0,
    stale: false },
  { id: "quiet", name: "Quiet app", progress: 0.1, tasks_left: 9, running: 0, need_user: 0, errors_count: 0,
    stale: false },
];
store.snapshots.splitnet = state.normalizeSnapshot(raw, now);
const prefs = { mode: null, open: {} };
const route = (name, id, section) => ({ name: name, id: id, section: section, view: null, item: null, filters: {} });
const vmOf = (r) => {
  const vm = state.buildViewModel(store, r, prefs, now);
  const all = (store.projects || []).map((p) => store.snapshots[p.id]).filter(Boolean);
  vm.snapshotList = r.name === "project" ? [store.snapshots[r.id]].filter(Boolean) : all;
  return vm;
};

const out = {};
out.inbox = inbox.sectionView(vmOf(route("project", "splitnet", "inbox")));
out.rules = rules.sectionView(vmOf(route("project", "splitnet", "rules")));
out.projects = projects.projectsView(vmOf(route("home", null, "overview")));

console.log(JSON.stringify(out));
"""


class _Nest(html.parser.HTMLParser):
    """Records each copy-ref button that opens inside a button or an anchor."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.bad = []
        self.copies = 0

    def handle_starttag(self, tag, attrs):
        if tag not in ("button", "a"):
            return
        values = dict(attrs)
        if tag == "button" and values.get("data-action") == "copy-ref":
            self.copies += 1
            if self.stack:
                self.bad.append(values.get("data-ref"))
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ("button", "a") and tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]


def nested_copies(markup):
    parser = _Nest()
    parser.feed(markup)
    return parser.bad, parser.copies


def run_node():
    node = shutil.which("node")
    tmp = tempfile.mkdtemp(prefix="p6-ref-")
    env = dict(os.environ, WEB=WEB, GOLDEN=GOLDEN)
    script = os.path.join(tmp, "wiring.mjs")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(NODE_SCRIPT)
    proc = subprocess.run([node, script], capture_output=True, text=True, check=False, timeout=120, env=env)
    if proc.returncode != 0:
        raise AssertionError("render failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class RefWiringP6Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the copy-reference wiring check is skipped")
        cls.out = run_node()

    def refs(self, name):
        return COPY.findall(self.out[name])

    def assert_refs_clean(self, name):
        for ref in self.refs(name):
            self.assertRegex(ref, REF_RE, name)
            self.assertNotIn("/Users/", ref, name)
            self.assertNotIn("~", ref, name)
        self.assertNotIn("/Users/", self.out[name], name)

    def test_inbox_question_row_and_section(self):
        refs = self.refs("inbox")
        self.assertIn("rb:splitnet/question/Q1", refs)
        self.assertIn("rb:splitnet/section/inbox.questions", refs)
        self.assert_refs_clean("inbox")

    def test_rule_rows_and_section(self):
        refs = self.refs("rules")
        self.assertIn("rb:splitnet/rule/R1", refs)
        self.assertIn("rb:splitnet/rule/R2", refs)
        self.assertIn("rb:splitnet/section/rules.list", refs)
        self.assert_refs_clean("rules")

    def test_project_rows_use_the_project_slug(self):
        refs = self.refs("projects")
        self.assertIn("rb:splitnet", refs)
        self.assertIn("rb:quiet", refs)
        self.assert_refs_clean("projects")

    def test_copy_buttons_have_labels(self):
        for name in ("inbox", "rules", "projects"):
            for match in re.finditer(r"<button[^>]*data-action=\"copy-ref\"[^>]*>", self.out[name]):
                self.assertIn('aria-label="Copy reference to ', match.group(0), name)

    def test_no_copy_button_sits_inside_another_button_or_link(self):
        for name in ("inbox", "rules", "projects"):
            bad, copies = nested_copies(self.out[name])
            self.assertGreater(copies, 0, name)
            self.assertEqual(bad, [], name)


if __name__ == "__main__":
    unittest.main()
