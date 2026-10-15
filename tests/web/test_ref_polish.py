"""Checks for the R7.12 polish (P9): the fixed copy column on every row grid, the row-grid fixes in roadmap, rules,
recent and research, the Tokens refs that name one project, and the rule and project summaries in ref.js.

The static checks read the CSS and the view files. The node check imports ref.js and prints refSummary for a rule and
a project; it is skipped when node is not installed.
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
CSS_DIR = os.path.join(WEB, "css")
VIEWS = os.path.join(WEB, "js", "views")
REF_JS = os.path.join(WEB, "js", "ref.js")
INLINE = re.compile(r"""\sstyle\s*=|\son[a-z]{3,}\s*=""", re.IGNORECASE)

NODE_SCRIPT = """
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.env.REF_JS).href);
const rule = { id: "R1", text: "Budget 40k per phase", kind: "budget", scope: "P2", value: 40 };
const project = { id: "roadmap-board", name: "Roadmap Board", state: "idle", running: 2 };
console.log(JSON.stringify({
  rule: m.refSummary("rule", rule, null),
  project: m.refSummary("project", project, null),
  none: m.refSummary("rule", null, null),
}));
"""


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class CopyColumnTests(unittest.TestCase):

    def setUp(self):
        self.css = read(CSS_DIR, "components.css")

    def test_every_row_grid_has_the_fixed_copy_track(self):
        self.assertIn("--ref-col: 1.5rem;", read(CSS_DIR, "tokens.css"))
        self.assertIn(".row-grid {\n  display: grid;\n  grid-template-columns: var(--rg) var(--ref-col);", self.css)
        self.assertIn(".act-row { display: grid; grid-template-columns: minmax(0, 1fr) 9.5rem;",
                      read(CSS_DIR, "flow.css"))

    def test_copy_button_sits_in_the_last_track_and_fades_until_hover(self):
        self.assertRegex(self.css, r"\.ref-copy\{grid-column:-1;")
        self.assertIn(".row-grid:hover .ref-copy{opacity:1}", self.css)
        self.assertIn("@media (pointer:coarse){.ref-copy{opacity:1}}", self.css)
        self.assertNotIn("hover:none", self.css)

    def test_phase_copy_sits_beside_the_phase_row(self):
        self.assertIn(".phase {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) var(--ref-col);", self.css)
        self.assertIn(".phase > .phase-body {\n  grid-column: 1 / -1;", self.css)

    def test_lists_that_are_not_rows_keep_their_own_tracks(self):
        self.assertIn("grid-template-columns: var(--rg); row-gap", read(CSS_DIR, "flow.css"))
        self.assertIn(".p-badges{--rg:3.5rem 3.5rem 3.5rem minmax(0,1fr);grid-template-columns:var(--rg);",
                      read(CSS_DIR, "panel.css"))

    def test_css_folder_stays_under_the_cap(self):
        total = 0
        for name in os.listdir(CSS_DIR):
            total += os.path.getsize(os.path.join(CSS_DIR, name))
        self.assertLessEqual(total, 72 * 1024)


class RowFixTests(unittest.TestCase):

    def test_roadmap_rows_are_grids(self):
        text = read(VIEWS, "roadmap.js")
        self.assertIn('<p class="rc-move row-grid">', text)
        self.assertIn('<div class="lane-act row-grid">', text)
        self.assertIn('<p class="tl-label row-grid">', text)
        self.assertIn('<span class="lane-name rg-t">', text)

    def test_rules_recent_and_research_rows(self):
        self.assertIn('<li class="rule-row row-grid">', read(VIEWS, "rules.js"))
        self.assertIn('<li class="log-row row-grid"><span class="log-date num rg-num">', read(VIEWS, "recent.js"))
        research = read(VIEWS, "research.js")
        self.assertIn('<li class="note-row row-grid">', research)
        self.assertIn(".note-row {\n  --rg: minmax(0, 1fr);", read(CSS_DIR, "components.css"))

    def test_views_have_no_inline_style_or_handlers(self):
        for name in ("roadmap.js", "research.js", "rules.js", "recent.js", "phases.js", "tokens.js"):
            self.assertIsNone(INLINE.search(read(VIEWS, name)), name)


class TokensRefTests(unittest.TestCase):

    def test_all_projects_refs_do_not_use_the_first_project(self):
        text = read(VIEWS, "tokens.js")
        # The reference project is the route's project only when the route is a project (never the first one).
        self.assertRegex(text, r"const refPid = pid;")
        self.assertRegex(text, r"const pid = isProject \? vm\.route\.id : null;")
        self.assertNotIn('{ project: pid, sum: refSummary("section", spendCount) }', text)
        self.assertIn('{ project: refPid, sum: refSummary("section", snaps.length) }', text)


class RefSummaryTests(unittest.TestCase):

    def test_rule_and_project_kinds_have_summaries(self):
        text = read(REF_JS)
        self.assertIn('if (kind === "rule") {', text)
        self.assertIn('if (kind === "project") {', text)

    def test_node_summaries_are_one_line_and_path_free(self):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node is not installed")
        env = dict(os.environ, REF_JS=REF_JS)
        proc = subprocess.run([node, "--input-type=module", "-e", NODE_SCRIPT], capture_output=True, text=True,
                              check=False, timeout=60, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        out = json.loads(proc.stdout)
        self.assertTrue(out["rule"].startswith('rule "Budget 40k per phase" kind=budget scope=P2'), out["rule"])
        self.assertTrue(out["project"].startswith('project "Roadmap Board" state=idle running=2'), out["project"])
        self.assertEqual(out["none"], "")
        for key in ("rule", "project"):
            self.assertNotIn("\n", out[key])
            self.assertNotIn("/Users/", out[key])


if __name__ == "__main__":
    unittest.main()
