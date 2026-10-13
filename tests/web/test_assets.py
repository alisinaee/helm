"""Static checks on the browser sources under web/ (stdlib only, no browser needed).

Every asset named by index.html and every JavaScript import must exist. The markup must be CSP-safe: no inline
script that runs, no on*= handlers, no style attributes. Colours are only defined in tokens.css, and every var(--x)
used anywhere must be defined there. No external hosts. The contrast gate (tools/contrast.py) must pass. The
self-test page embeds the shared format cases; they must equal tests/fixtures/format_cases.json.
"""

import json
import os
import re
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
TOKENS = os.path.join(WEB, "css", "tokens.css")
INDEX = os.path.join(WEB, "index.html")
DEV_PAGE = os.path.join(WEB, "dev", "tests.html")
FIXTURE = os.path.join(TESTS, "fixtures", "format_cases.json")

HTML_REF = re.compile(r'''\b(?:href|src)\s*=\s*["']([^"']+)["']''')
SCRIPT_TAG = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
IMPORT = re.compile(r'''(?:^|\n)\s*import\s+(?:[^'"();]*?\s+from\s+)?["']([^"']+)["']''')
VAR_USE = re.compile(r"var\(\s*--([a-z0-9-]+)")
VAR_DEF = re.compile(r"--([a-z0-9-]+)\s*:")
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
INLINE_STYLE = re.compile(r"""\bstyle\s*=\s*(["']|\\["'])""")
INLINE_HANDLER = re.compile(r"""\bon[a-z]{3,}\s*=\s*(["']|\\["'])""")
EXTERNAL = re.compile(r"https?://|//cdn|@import|@font-face")


def walk(folder, suffixes):
    """Every file under folder with one of the suffixes, sorted, as absolute paths."""
    found = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for name in sorted(filenames):
            if os.path.splitext(name)[1] in suffixes:
                found.append(os.path.join(dirpath, name))
    return found


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def rel(path):
    return os.path.relpath(path, REPO).replace(os.sep, "/")


def web_text_files():
    """The sources of the new shell. web/legacy.html is excluded: it is the old page, replaced in WP8."""
    return [p for p in walk(WEB, {".html", ".css", ".js"}) if os.path.basename(p) != "legacy.html"]


class AssetTests(unittest.TestCase):

    def test_index_references_resolve(self):
        missing = []
        for ref in HTML_REF.findall(read(INDEX)):
            if ref.startswith(("data:", "#", "http://", "https://")):
                continue
            target = os.path.join(WEB, ref.lstrip("/")) if ref.startswith("/") else os.path.join(WEB, ref)
            if not os.path.isfile(target):
                missing.append(ref)
        self.assertEqual(missing, [])

    def test_js_imports_resolve(self):
        problems = []
        for path in walk(WEB, {".js"}):
            for spec in IMPORT.findall(read(path)):
                if not spec.startswith("."):
                    problems.append("%s imports %r (only relative imports are allowed)" % (rel(path), spec))
                    continue
                if not os.path.isfile(os.path.normpath(os.path.join(os.path.dirname(path), spec))):
                    problems.append("%s imports missing file %r" % (rel(path), spec))
        self.assertEqual(problems, [])

    def test_js_files_are_modules_with_imports_checked(self):
        for name in ("app.js", "api.js", "state.js", "router.js", "dom.js", "format.js"):
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", name)), name)
        for name in ("home.js", "topbar.js", "usage.js", "kpi.js", "tasks.js", "phases.js", "running.js",
                     "needsyou.js", "next.js", "recent.js", "extras.js", "legend.js"):
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", "views", name)), name)


class CspTests(unittest.TestCase):

    def test_index_has_no_inline_script_style_or_handlers(self):
        text = read(INDEX)
        for match in SCRIPT_TAG.finditer(text):
            self.assertIn("src=", match.group(1), "inline <script> in index.html")
        self.assertIsNone(INLINE_STYLE.search(text), "style attribute in index.html")
        self.assertIsNone(INLINE_HANDLER.search(text), "on*= handler in index.html")

    def test_dev_page_only_has_data_or_module_scripts(self):
        for match in SCRIPT_TAG.finditer(read(DEV_PAGE)):
            attrs = match.group(1)
            if "src=" in attrs:
                continue
            self.assertIn('type="application/json"', attrs, "executable inline script in dev/tests.html")

    def test_no_inline_style_or_handlers_in_any_web_source(self):
        problems = []
        for path in web_text_files():
            text = read(path)
            if INLINE_STYLE.search(text):
                problems.append(rel(path) + ": style attribute")
            if INLINE_HANDLER.search(text):
                problems.append(rel(path) + ": on*= handler")
        self.assertEqual(problems, [])

    def test_no_external_hosts_or_imports(self):
        problems = []
        for path in web_text_files():
            if EXTERNAL.search(read(path)):
                problems.append(rel(path))
        self.assertEqual(problems, [])

    def test_no_uppercase_transform(self):
        problems = [rel(p) for p in web_text_files() if p.endswith(".css") and "uppercase" in read(p)]
        self.assertEqual(problems, [])


class TokenTests(unittest.TestCase):

    def test_every_var_used_is_defined_in_tokens(self):
        defined = set(VAR_DEF.findall(read(TOKENS)))
        missing = []
        for path in web_text_files():
            for name in VAR_USE.findall(read(path)):
                if name not in defined:
                    missing.append("%s uses var(--%s)" % (rel(path), name))
        self.assertEqual(missing, [])

    def test_hex_colours_only_in_tokens(self):
        problems = []
        for path in web_text_files():
            if os.path.abspath(path) == os.path.abspath(TOKENS):
                continue
            for found in HEX.findall(read(path)):
                problems.append("%s: %s" % (rel(path), found))
        self.assertEqual(problems, [])

    def test_contrast_gate_passes(self):
        proc = subprocess.run([sys.executable, os.path.join(REPO, "tools", "contrast.py")],
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class DevPageTests(unittest.TestCase):

    def test_embedded_format_cases_match_fixture(self):
        match = re.search(r'<script type="application/json" id="format-cases">(.*?)</script>', read(DEV_PAGE),
                          re.S)
        self.assertIsNotNone(match, "format-cases block missing from dev/tests.html")
        with open(FIXTURE, encoding="utf-8") as fh:
            self.assertEqual(json.loads(match.group(1)), json.load(fh))


if __name__ == "__main__":
    unittest.main()
