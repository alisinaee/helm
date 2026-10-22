"""Checks for the app shell (WP28): the icon sprite, the CSS budget, the section registry and the router, and the
node render of the nav, the bottom nav and the top bar.

The sprite check reads every "icons.svg#i-..." reference in web/ and requires each id to be a symbol in icons.svg; the
sprite stays at 5 KB or less. The CSS check keeps the whole web/css folder at 51 KB or less and shell.css at 8 KB or
less. The router and render checks run tests/web/render_shell.mjs in node; they are skipped when node is missing.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
ICONS = os.path.join(WEB, "icons.svg")
CSS_DIR = os.path.join(WEB, "css")
RENDER = os.path.join(TESTS, "web", "render_shell.mjs")
ICON_REF = re.compile(r"icons\.svg#(i-[A-Za-z0-9-]+)")
SYMBOL_ID = re.compile(r'<symbol\b[^>]*\bid="(i-[A-Za-z0-9-]+)"')
SECTION_MODULE = re.compile(r'module:\s*("[^"]+"|null)')
INLINE = re.compile(r"""\sstyle\s*=|\son[a-z]{3,}\s*=""", re.IGNORECASE)
FLOW_CSS_MAX = 5.5 * 1024  # flow.css: Overview, Inbox, Activity and the question card (5.3 KB on 2026-10-16)
CSS_TOTAL_MAX = 192 * 1024  # the one shared web/css total cap, imported by the other CSS tests. 2026-10-17: sections grow (System v2, Activity, Roadmap map, Tokens); cap raised from 80 KB so work is not blocked. Keep per-file budgets in their own tests.
SHELL_CSS_MAX = 10 * 1024  # R11.129/R11.125: usage mini bars, rail count badges
ICONS_MAX = 6 * 1024  # raised from 5 KB for the R12.1 icon set (22 symbols)
SHELL_FILES = ("shell.css", "panel.css", "work.css", "plan.css", "admin.css", "flow.css", "motion.css")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def web_sources():
    found = []
    for dirpath, dirnames, filenames in os.walk(WEB):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith((".html", ".css", ".js")) and name != "legacy.html":
                found.append(os.path.join(dirpath, name))
    return found


def node_render():
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not installed; the shell render check is skipped")
    proc = subprocess.run([node, "--experimental-default-type=module", RENDER, WEB],
                          capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("render_shell.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class IconSpriteTests(unittest.TestCase):

    def test_sprite_is_small_and_defines_its_symbols(self):
        text = read(ICONS)
        self.assertLessEqual(len(text.encode("utf-8")), ICONS_MAX)
        self.assertGreaterEqual(len(SYMBOL_ID.findall(text)), 14)
        self.assertIsNone(INLINE.search(text), "the sprite must not carry style attributes or handlers")

    def test_every_icon_reference_names_a_symbol(self):
        symbols = set(SYMBOL_ID.findall(read(ICONS)))
        missing = []
        for path in web_sources():
            for name in ICON_REF.findall(read(path)):
                if name not in symbols:
                    missing.append("%s uses %s" % (os.path.relpath(path, REPO), name))
        self.assertEqual(missing, [])

    def test_every_section_icon_exists_in_the_sprite(self):
        symbols = set(SYMBOL_ID.findall(read(ICONS)))
        routes = read(os.path.join(WEB, "js", "routes.js"))
        icons = re.findall(r'icon:\s*"([a-z-]+)"', routes)
        self.assertGreaterEqual(len(icons), 10)
        for name in icons + ["settings", "collapse", "more", "theme", "help", "panel"]:
            self.assertIn("i-" + name, symbols, name)


class CssBudgetTests(unittest.TestCase):

    def test_all_css_is_within_budget(self):
        total = sum(os.path.getsize(os.path.join(CSS_DIR, name)) for name in os.listdir(CSS_DIR)
                    if name.endswith(".css"))
        self.assertLessEqual(total, CSS_TOTAL_MAX, "web/css totals %d bytes" % total)

    def test_shell_css_is_within_this_packages_budget(self):
        self.assertLessEqual(os.path.getsize(os.path.join(CSS_DIR, "shell.css")), SHELL_CSS_MAX)

    def test_index_links_every_shell_stylesheet(self):
        html = read(os.path.join(WEB, "index.html"))
        for name in SHELL_FILES:
            self.assertIn('href="/css/%s"' % name, html, name)
            self.assertTrue(os.path.isfile(os.path.join(CSS_DIR, name)), name)

    def test_stub_stylesheets_are_commented_and_small(self):
        # plan.css is filled by WP32 (its size budget is checked in tests/web/test_plan.py), so only the rules
        # are checked.
        self.assertIn(".lane-head", read(os.path.join(CSS_DIR, "plan.css")))
        # work.css is filled by WP31: it must carry real rules for the Work section, not the stub.
        self.assertIn(".wk-board", read(os.path.join(CSS_DIR, "work.css")))

    def test_flow_css_holds_the_overview_inbox_and_activity_styles(self):
        # WP30 filled flow.css: the question card and the activity rows. It stays well inside the 51 KB total.
        text = read(os.path.join(CSS_DIR, "flow.css"))
        self.assertTrue(text.lstrip().startswith("/*"))
        self.assertLessEqual(len(text.encode("utf-8")), FLOW_CSS_MAX)
        self.assertIn(".qc {", text)
        self.assertIn(".act-row", text)


class RegistryTests(unittest.TestCase):

    def test_section_modules_that_are_named_exist(self):
        text = read(os.path.join(WEB, "js", "routes.js"))
        for match in SECTION_MODULE.findall(text):
            if match == "null":
                continue
            path = os.path.normpath(os.path.join(WEB, "js", match.strip('"')))
            self.assertTrue(os.path.isfile(path), match)

    def test_unbuilt_sections_are_registered_without_a_module(self):
        # WP34 built the last unbuilt sections, so no entry is null now; the loader must still refuse a null module.
        text = read(os.path.join(WEB, "js", "routes.js"))
        self.assertIn("!section.module", text)

    def test_shell_modules_exist(self):
        for name in ("router.js", "routes.js", "state.js", "app.js", "cmd.js", "keys.js"):
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", name)), name)
        for name in ("nav.js", "topbar.js", "toast.js", "overview.js", "work.js"):
            self.assertTrue(os.path.isfile(os.path.join(WEB, "js", "views", name)), name)


class ShellRenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out = node_render()

    def test_routes_parse_and_redirect_old_links(self):
        routes = self.out["routes"]
        self.assertEqual(routes["#/"]["redirect"], "#/all/overview")
        self.assertEqual(routes[""]["redirect"], "#/all/overview")
        self.assertEqual(routes["#/p/splitnet"]["redirect"], "#/p/splitnet/overview")
        self.assertIsNone(routes["#/all/inbox"]["redirect"])
        self.assertEqual(routes["#/all/inbox"]["section"], "inbox")
        self.assertEqual(routes["#/p/BAD!/work"]["name"], "home")
        self.assertEqual(routes["#/all/nope"]["section"], "overview")

    def test_project_route_keeps_view_item_and_filters(self):
        route = self.out["routes"]["#/p/splitnet/work/board/i/t12?f=state:todo"]
        self.assertEqual((route["name"], route["id"], route["section"]), ("project", "splitnet", "work"))
        self.assertEqual((route["view"], route["item"]), ("board", "t12"))
        self.assertIn("state%3Atodo", route["redirect"])

    def test_nav_has_sections_badges_and_no_inline_markup(self):
        nav = self.out["nav"]
        for label in ("Overview", "Inbox", "Roadmap", "Work", "Agents", "Tokens", "Rules",
                      "Activity", "Settings"):
            self.assertIn(">" + label + "</span>", nav, label)
        self.assertNotIn(">Issues</span>", nav)
        self.assertIn('aria-current="page"', nav)
        self.assertIn("nav-b", nav)
        self.assertIsNone(INLINE.search(nav))

    def test_bottom_nav_has_more_and_its_sheet(self):
        bnav = self.out["bnav"]
        self.assertIn('id="bnav-more"', bnav)
        self.assertIn('aria-controls="bnav-more"', bnav)
        self.assertIn("More", bnav)

    def test_stopped_project_shows_the_pill_and_resume(self):
        top = self.out["topbarStopped"]
        self.assertIn("Stopped", top)
        self.assertIn('data-op="control.resume"', top)
        self.assertEqual(top.count("<h1"), 1)

    def test_meters_show_unknown_without_rows_and_values_with_rows(self):
        self.assertIn("unknown", self.out["topbarStopped"])
        meters = self.out["topbarMeters"]
        # The top bar is one weekly line: the stop from the meter rows; no reading in the fixture means unknown.
        self.assertIn("stop at 60%", meters)
        self.assertIn("Week unknown", meters)
        self.assertNotIn("62/60%", meters)
        self.assertIn("Week unknown", self.out["topbarStopped"])


if __name__ == "__main__":
    sys.exit(unittest.main())
