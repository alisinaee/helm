"""The System map side panel (R10.24, A6): web/js/views/system-panel.js renders the facts and routed links."""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(os.path.dirname(TESTS), "web")
NODE = shutil.which("node")
SCRIPT = r"""
const { pathToFileURL } = await import("node:url");
const m = await import(pathToFileURL(process.argv[1] + "/js/views/system-panel.js").href);
const comp = { id: "api", name: "HTTP <API>", layer: "api", notes: "Routes.", entry: "r/s.py", fileCount: 12,
  files: ["roadmap/http/**"], heat: { commits30: 3 } };
console.log(JSON.stringify({ full: m.panelHtml("my pid", comp, { commits30: 5, lastAt: "2026-10-01T10:00:00Z",
  runningJobs: 1, openWork: 2, bugs: 1 }), none: m.panelHtml("p", null, null), bare: m.panelHtml("p", { id: "x" }, null) }));
"""


@unittest.skipIf(NODE is None, "node is not installed")
class SystemPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run([NODE, "--experimental-default-type=module", "-e", SCRIPT, WEB],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        cls.out = json.loads(proc.stdout)

    def test_facts(self):
        html = self.out["full"]
        for text in ("HTTP &lt;API&gt;", "Routes.", "r/s.py", "roadmap/http/**", "2026-10-01", "Open Work", "Bugs"):
            self.assertIn(text, html)
        self.assertNotIn("<API>", html)
        self.assertRegex(html, r"Commits \(30 days\)</dt><dd>5</dd>")
        self.assertRegex(html, r"Running jobs</dt><dd>1</dd>")

    def test_links_route_to_work_and_git(self):
        html = self.out["full"]
        self.assertIn('href="#/p/my%20pid/work"', html)
        self.assertIn('href="#/p/my%20pid/git"', html)

    def test_close_and_empty(self):
        self.assertIn('data-sys-op="close"', self.out["full"])
        self.assertEqual(self.out["none"], "")
        self.assertIn("none", self.out["bare"])

    def test_wired_into_view(self):
        with open(os.path.join(WEB, "js", "views", "system.js"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("system-panel.js", src)
        self.assertRegex(src, r'"Escape"')
        self.assertIn("api.fit()", src)
        with open(os.path.join(WEB, "js", "views", "system-panel.js"), encoding="utf-8") as f:
            panel = f.read()
        self.assertIsNone(re.search(r"\sstyle\s*=|innerHTML|<script", panel))
        self.assertTrue(all(len(line) <= 120 for line in panel.splitlines()))


if __name__ == "__main__":
    unittest.main()
