"""R7.30 (B-2): the Map opens full screen in its own tab at #/full/<pid>/workflow.

The route is parsed by routes.js fullRouteOf() (checked in node). The Map toolbar links the tab (source check), and
app.js renders the diagram alone (no nav, no top bar) into #full-view. The side panel opens on a tap or Enter on a node
and closes on Escape or its close button; those handlers are checked in views/workflow.js source.
"""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
NODE = shutil.which("node")
ROUTES = os.path.join(WEB, "js", "routes.js")


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        return fh.read()


@unittest.skipIf(NODE is None, "node is not installed")
class FullRouteTest(unittest.TestCase):
    def match(self, hashes):
        script = ("import { fullRouteOf } from " + json.dumps("file://" + ROUTES) + ";\n"
                  "process.stdout.write(JSON.stringify(" + json.dumps(hashes) + ".map((h) => fullRouteOf(h))));\n")
        proc = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True,
                              check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("routes.js failed: " + proc.stderr[-600:])
        return json.loads(proc.stdout)

    def test_full_hash_yields_the_project_id(self):
        self.assertEqual(["rb-site", "p1"], self.match(["#/full/rb-site/workflow", "#/full/p1/workflow?x=1"]))

    def test_other_hashes_are_not_the_full_route(self):
        got = self.match(["#/p/rb-site/workflow", "#/full/rb-site", "#/full/Bad_Id/workflow", "#/full/a/work", ""])
        self.assertEqual([None, None, None, None, None], got)


class FullScreenSourceTest(unittest.TestCase):
    def test_map_toolbar_opens_the_full_route_in_a_new_tab(self):
        src = read("web/js/views/workflow.js")
        self.assertIn('return "#/full/" + pid + "/workflow";', src)
        self.assertIn('target="_blank" rel="noopener">Open full screen</a>', src)

    def test_app_renders_the_map_alone_without_the_shell(self):
        src = read("web/js/app.js")
        self.assertIn("fullRouteOf(window.location.hash)", src)
        self.assertIn("root.hidden = true;", src)
        self.assertIn('import("./views/workflow.js").then(function (mod) {', src)
        self.assertIn("mod.mountFull(host, pid);", src)

    def test_panel_opens_on_tap_or_enter_and_closes_on_escape_or_close(self):
        src = read("web/js/views/workflow.js")
        self.assertIn("openPanel(el.getAttribute(\"data-wf-item\"));", src)
        self.assertIn('e.key === "Enter" ? closestEl(e.target, "[data-wf-item]")', src)
        self.assertIn('if (e.key === "Escape" && full.panel && !full.panel.hidden) closePanel();', src)
        self.assertIn("[data-wf-full-close]", src)
        self.assertIn("Open in Work", src)

    def test_pan_and_zoom_survive_a_refresh(self):
        src = read("web/js/views/workflow.js")
        self.assertIn("const view = same && full.api ? full.api.view() : undefined;", src)


if __name__ == "__main__":
    unittest.main()
