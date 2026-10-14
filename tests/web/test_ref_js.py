"""Checks for the copy-reference helper (R7.12): web/js/ref.js builds the board ref and its one-line summary, caps the
clipboard text at 200 characters, and builds the copy button through esc(). tests/web/ref_js node check imports the
module in node (no DOM is needed for the pure functions) and prints the results as JSON. The static checks read the
icon, the one panel.js branch and the CSS block. The node checks are skipped when node is not installed.
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
REF_JS = os.path.join(WEB, "js", "ref.js")
PANEL_JS = os.path.join(WEB, "js", "views", "panel.js")
APP_JS = os.path.join(WEB, "js", "app.js")
ICONS = os.path.join(WEB, "icons.svg")
CSS = os.path.join(WEB, "css", "components.css")
REF_RE = re.compile(r"^rb:[a-z0-9-]+(/[a-z]+/[A-Za-z0-9._-]+)?$")
CSS_BLOCK_MAX = 400

NODE_SCRIPT = """
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.env.REF_JS).href);
const snap = { features: { orphans: ["R3.9"] } };
const task = { id: "R3.2", title: "Planner filters", state: "doing", feats: ["F7"],
  subs: [{ t: "a", d: true }, { t: "b", d: false }] };
const orphan = { id: "R3.9", title: "Loose", state: "todo", feats: [], subs: [] };
const long = "x".repeat(300);
const ref = m.refOf("roadmap-board", "task", "R3.2");
const out = {
  ref: ref,
  project: m.refOf("roadmap-board", "project", null),
  sub: m.refOf("roadmap-board", "sub", "R3.2.s1"),
  badId: m.refOf("roadmap-board", "task", "R3 2"),
  pathId: m.refOf("roadmap-board", "task", "/Users/ali/x"),
  noProject: m.refOf("", "task", "R3.2"),
  taskSum: m.refSummary("task", task, snap),
  orphanSum: m.refSummary("task", orphan, snap),
  orphanNoSnap: m.refSummary("task", orphan, null),
  longTitle: m.refSummary("task", Object.assign({}, task, { title: long }), null),
  quoteTitle: m.refSummary("task", Object.assign({}, task, { title: 'a "b" c' }), null),
  phaseSum: m.refSummary("phase", { name: "Spikes", state: "doing", done: 2, total: 5 }, null),
  jobSum: m.refSummary("job", { title: "Docker lab", status: "running", model: "haiku", tokensK: 12.5 }, null),
  sectionSum: m.refSummary("section", 4, null),
  noItem: m.refSummary("task", null, null),
  longText: m.refText(ref, "task " + long),
  shortText: m.refText(ref, "task \\"x\\" status=todo"),
  button: m.copyButton("task", "R3.2", "Planner <filters>", { project: "roadmap-board", sum: "task \\"x\\"" }),
  buttonNoProject: m.copyButton("task", "R3.2", "x"),
};
console.log(JSON.stringify(out));
"""


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def run_node():
    node = shutil.which("node")
    env = dict(os.environ, REF_JS=REF_JS)
    proc = subprocess.run(
        [node, "--experimental-default-type=module", "--input-type=module", "-e", NODE_SCRIPT],
        capture_output=True, text=True, check=False, timeout=60, env=env,
    )
    if proc.returncode != 0:
        raise AssertionError("ref.js failed in node: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class RefHelperTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the ref.js check is skipped")
        cls.out = run_node()

    def test_ref_format_matches_the_spec(self):
        self.assertEqual(self.out["ref"], "rb:roadmap-board/task/R3.2")
        self.assertEqual(self.out["project"], "rb:roadmap-board")
        self.assertEqual(self.out["sub"], "rb:roadmap-board/sub/R3.2.s1")
        self.assertRegex(self.out["ref"], REF_RE)

    def test_bad_ids_and_empty_project_give_no_ref(self):
        self.assertEqual(self.out["badId"], "")
        self.assertEqual(self.out["noProject"], "")

    def test_no_absolute_paths_in_refs_or_summaries(self):
        for key in ("ref", "project", "sub", "taskSum", "orphanSum", "longTitle", "button"):
            self.assertNotIn("/Users/", self.out[key], key)
            self.assertNotIn("~", self.out[key], key)
        self.assertEqual(self.out["pathId"], "")

    def test_task_summary_has_the_spec_keys(self):
        self.assertEqual(
            self.out["taskSum"],
            'task "Planner filters" status=doing feature=F7 orphan=no subs=1/2',
        )

    def test_orphan_flag_uses_the_snapshot_list(self):
        self.assertIn("orphan=yes", self.out["orphanSum"])
        self.assertIn("orphan=yes", self.out["orphanNoSnap"])
        self.assertIn("feature=none", self.out["orphanSum"])

    def test_other_kinds_summaries(self):
        self.assertEqual(self.out["phaseSum"], 'phase "Spikes" status=doing done=2/5')
        self.assertEqual(self.out["jobSum"], 'job "Docker lab" state=running model=haiku tokens=12.5K')
        self.assertEqual(self.out["sectionSum"], "section count=4")
        self.assertEqual(self.out["noItem"], "")

    def test_titles_are_quoted_and_cut_to_forty(self):
        content = re.search(r'"([^"]*)"', self.out["longTitle"]).group(1)
        self.assertEqual(len(content), 40)
        self.assertTrue(content.endswith("..."))
        self.assertEqual(self.out["quoteTitle"], 'task "a \'b\' c" status=doing feature=F7 orphan=no subs=1/2')

    def test_clipboard_text_is_two_lines_and_at_most_200_characters(self):
        text = self.out["longText"]
        self.assertLessEqual(len(text), 200)
        self.assertEqual(len(text), 200)
        ref, summary = text.split("\n", 1)
        self.assertEqual(ref, "rb:roadmap-board/task/R3.2")
        self.assertTrue(summary.endswith("..."))
        self.assertEqual(self.out["shortText"], 'rb:roadmap-board/task/R3.2\ntask "x" status=todo')

    def test_copy_button_markup(self):
        html = self.out["button"]
        self.assertIn('data-action="copy-ref"', html)
        self.assertNotIn("data-side=", html)
        self.assertIn('data-ref="rb:roadmap-board/task/R3.2"', html)
        self.assertIn('data-sum="task &quot;x&quot;"', html)
        self.assertIn('aria-label="Copy reference to Planner &lt;filters&gt;"', html)
        self.assertIn('href="/icons.svg#i-copy"', html)
        self.assertNotRegex(html, r"\sstyle\s*=|\son[a-z]{3,}\s*=")
        self.assertEqual(self.out["buttonNoProject"], "")


class RefStaticTests(unittest.TestCase):

    def test_ref_js_builds_markup_through_esc_only(self):
        source = read(REF_JS)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("execCommand", source)
        self.assertNotIn("console.log", source)
        self.assertIn('import { esc } from "./dom.js";', source)

    def test_app_dispatches_copy_ref_as_a_global_action(self):
        app = read(APP_JS)
        self.assertIn('import { copyRef } from "./ref.js";', app)
        self.assertEqual(app.count('action === "copy-ref"'), 1)
        self.assertIn('copyRef(el);', app)
        # the branch must not re-render: copying changes nothing on the page
        branch = app[app.index('action === "copy-ref"'):]
        branch = branch[:branch.index("\n  }", branch.index("copyRef(el);"))]
        self.assertNotIn("render()", branch)

    def test_panel_no_longer_handles_copy_ref(self):
        source = read(PANEL_JS)
        self.assertNotIn("copy-ref", source)
        self.assertNotIn("copyRef", source)

    def test_icon_symbol_exists(self):
        self.assertIn('<symbol id="i-copy"', read(ICONS))

    def test_css_block_is_small_and_present(self):
        css = read(CSS)
        start = css.index("/* Copy reference (R7.12)")
        end = css.index(".ref-text{", start)
        end = css.index("\n", end)
        block = css[start:end + 1]
        self.assertLess(len(block.encode("utf-8")), CSS_BLOCK_MAX)
        self.assertIn(".ref-copy", block)
        self.assertIn(".ref-col", block)


if __name__ == "__main__":
    unittest.main()
