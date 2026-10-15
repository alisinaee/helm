"""R7.62: the Workflow Map is the whole project and has no time range; the Timeline keeps the range (2 h, Today, Week,
All). The Map's diagram is re-mounted when the snapshot changes (data-wf-rev), so a refresh shows the new state, and
the diagram draws only the spec's edges (handoff, dependency, blocker) with the spec's node size and 4 statuses.

The node checks run web/js/views/workflow.js in node through tests/web/render_workflow.mjs and are skipped when node
is not installed. The source checks always run.
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


def read_text(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


class MapSourceTests(unittest.TestCase):

    def test_only_spec_edges_are_drawn(self):
        render_js = read_text("web", "js", "graph", "render.js")
        self.assertNotIn("concat(g.sequence", render_js)
        self.assertNotIn('"Sequence"', read_text("web", "js", "views", "workflow.js"))

    def test_legend_names_the_four_spec_statuses(self):
        source = read_text("web", "js", "views", "workflow.js")
        for word in ("Done", "Doing", "Todo", "Blocked"):
            self.assertIn('"' + word + '"', source)
        self.assertNotIn("Blocked or failed", source)

    def test_map_has_a_100_percent_control_and_a_revision_on_the_host(self):
        source = read_text("web", "js", "views", "workflow.js")
        self.assertIn('ctlHtml("Actual size", "actual", "100%")', source)
        self.assertIn('data-wf-rev="', source)
        self.assertIn('api.zoom(1 / api.view().k)', source)

    def test_node_size_is_the_spec_size(self):
        layout_js = read_text("web", "js", "graph", "layout.js")
        self.assertIn("export const NODE_W = 168;", layout_js)
        self.assertIn("export const NODE_H = 44;", layout_js)
        self.assertIn("export const PILL_W = 52;", layout_js)

    def test_stale_map_is_avoided_by_the_revision_check(self):
        source = read_text("web", "js", "views", "workflow.js")
        self.assertIn('host.getAttribute("data-wf-rev") === st.rev', source)
        self.assertIn("entry.stamp = stampOf(entry.raw);", source)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class MapRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        proc = subprocess.run([shutil.which("node"), "--experimental-default-type=module", RENDER, WEB, FIXTURE],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("render_workflow.mjs failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_the_map_has_no_time_range_and_the_timeline_keeps_it(self):
        self.assertNotIn('aria-label="Range"', self.out["sections"]["map"])

    def test_the_map_draws_the_whole_project_with_its_controls(self):
        mapped = self.out["sections"]["map"]
        self.assertIn('data-wf-map-op="actual"', mapped)
        self.assertIn('data-wf-rev="', mapped)
        self.assertIn("items</span>", mapped)

    def test_no_inline_style_in_the_map(self):
        self.assertIsNone(re.search(r'\sstyle\s*=', self.out["sections"]["map"]))


if __name__ == "__main__":
    unittest.main()
