"""System v2 integration (R11.110): diagram kinds from the catalog, group toggles and the drill breadcrumb."""

import json
import os
import shutil
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(REPO, "web")
SCRIPT = """
import { pathToFileURL } from "node:url";
globalThis.document = { dispatchEvent() { return true; }, addEventListener() {}, getElementById() { return null; } };
const m = await import(pathToFileURL(process.argv[1] + "/js/views/system.js").href);
const g = { groups: [{ id: "k:a", label: "A" }], nodes: [{ id: "c:1", label: "one", kind: "component", group: "k:a" },
  { id: "c:2", label: "two", kind: "component", group: "k:a" }], edges: [] };
console.log(JSON.stringify({ svg: m.graphSvg(g, {}, "x"), shown: m.shownView(g).nodes.length }));
"""


class SystemIntegrationTest(unittest.TestCase):
    def test_group_band_has_a_keyboard_toggle(self):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node is not installed")
        proc = subprocess.run([node, "--experimental-default-type=module", "--input-type=module", "-e", SCRIPT, WEB],
                              capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        svg = json.loads(proc.stdout)["svg"]
        self.assertIn('data-sys-tog="k:a"', svg)
        self.assertIn('aria-expanded="true"', svg)

    def test_wiring_is_present(self):
        with open(os.path.join(WEB, "js", "views", "system.js"), encoding="utf-8") as fh:
            src = fh.read()
        for word in ("bindContextMenu", "collapseGroups", "subgraph", "data-sys-crumb", "erSvg", "classSvg"):
            self.assertIn(word, src)


if __name__ == "__main__":
    unittest.main()
