"""R11.3 splitter util: static contract checks plus a node run of the clamp helpers."""

import os
import re
import shutil
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(REPO, "web")


def read(*p):
    with open(os.path.join(WEB, *p), encoding="utf-8") as f:
        return f.read()


class SplitterTest(unittest.TestCase):
    def test_util_contract(self):
        js = read("js", "splitter.js")
        for needle in ("pointerdown", "keydown", "dblclick", "aria-valuenow", "localStorage", "catch", "Home", "End"):
            self.assertIn(needle, js)
        self.assertIn("initSplitters", read("js", "app.js"))

    def test_git_has_separator(self):
        js = read("js", "views", "git.js")
        self.assertIn('data-splitter-host="git"', js)
        m = re.search(r'class="spl" role="separator" tabindex="0"[^;]*data-splitter="git"', js)
        self.assertTrue(m)
        self.assertIn("var(--split-git", read("css", "resize.css"))

    def test_css_hit_area(self):
        css = read("css", "resize.css")
        self.assertRegex(css, r"\.spl\{[^}]*width:6px")
        self.assertIn(".spl:focus-visible", css)
        self.assertIn(".spl:hover", css)

    def test_documented(self):
        with open(os.path.join(REPO, "docs", "UI-CHECKLIST.md"), encoding="utf-8") as f:
            self.assertIn("data-splitter-host", f.read())

    @unittest.skipUnless(shutil.which("node"), "node missing")
    def test_clamp(self):
        code = (
            "import('" + os.path.join(WEB, "js", "splitter.js") + "').then(m=>{"
            "const s={dataset:{min:'320',max:'720'}};"
            "console.log(m.clampWidth(s,1000,900),m.clampWidth(s,1000,100),m.clampWidth(s,2000,900),m.clampWidth(s,0,"
            "500));})"
        )
        out = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.stdout.split(), ["680", "320", "720", "500"], out.stderr)


if __name__ == "__main__":
    unittest.main()
