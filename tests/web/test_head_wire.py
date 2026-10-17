"""The Head wire-up (R7.31 H9, docs/HEAD-SPEC.md sections 5 and 8): the section entry, the icon, the nav badge, the
Overview chip, the stylesheet link, and the loader's head key.

Static checks read the sources. The nav badge is rendered in node (render_head_wire.mjs) from a snapshot list with
open asks; the check is skipped when node is not installed. The Head section loads web/js/views/head.js, whose
sectionView(vm) reads the snapshot's head key; the render check folds the demo fixture (render_head.mjs) and checks
the rows the screen draws.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)

from tests.web.test_head_view import view_model  # noqa: E402

WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_head_wire.mjs")
RENDER_HEAD = os.path.join(TESTS, "web", "render_head.mjs")
LOADER = os.path.join(REPO, "roadmap", "services", "loader.py")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class HeadSection(unittest.TestCase):
    def setUp(self):
        self.routes = read(os.path.join(WEB, "js", "routes.js"))

    def test_head_is_a_top_level_section_after_inbox(self):
        self.assertIn('{ id: "head", label: "Head", icon: "head", module: "./views/head.js", bottom: false }',
                      self.routes)
        self.assertLess(self.routes.index('id: "inbox"'), self.routes.index('id: "head"'))
        self.assertLess(self.routes.index('id: "head"'), self.routes.index('id: "roadmap"'))

    def test_head_module_exports_section_view(self):
        src = read(os.path.join(WEB, "js", "views", "head.js"))
        self.assertRegex(src, r"export function sectionView\(vm\)")
        state = read(os.path.join(WEB, "js", "state.js"))
        self.assertIn("head: raw.head && typeof raw.head === \"object\" ? raw.head : null", state)

    def test_head_section_icon_is_in_the_sprite(self):
        self.assertIn('<symbol id="i-head"', read(os.path.join(WEB, "icons.svg")))

    def test_head_stylesheet_is_linked_from_index(self):
        index = read(os.path.join(WEB, "index.html"))
        self.assertIn('<link rel="stylesheet" href="/css/head.css">', index)
        self.assertTrue(os.path.isfile(os.path.join(WEB, "css", "head.css")))


class HeadBadgeAndChip(unittest.TestCase):
    def test_nav_counts_open_asks_from_the_snapshot_head_key(self):
        nav = read(os.path.join(WEB, "js", "views", "nav.js"))
        self.assertIn("snap.head.counts.unhandled", nav)
        self.assertIn('head: { key: "head", tone: "neutral", word: "open asks" }', nav)  # R11.125: generic badge
        self.assertNotIn("innerHTML", nav)

    def test_overview_chip_links_to_the_unhandled_filter(self):
        overview = read(os.path.join(WEB, "js", "views", "overview.js"))
        self.assertIn("function headChip(snap)", overview)
        self.assertIn("/head?f=unhandled", overview)
        self.assertIn("headChip(snap)", overview)

    def test_nav_badge_renders_in_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        base = {"questions": [], "needsYou": [], "issues": [], "tasks": [], "runningCount": 0}
        snapshots = [dict(base, id="alpha", head={"counts": {"unhandled": 3}}),
                     dict(base, id="beta", head={"counts": {"unhandled": 2}})]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "input.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"snapshots": snapshots}, fh)
            proc = subprocess.run([node, "--experimental-default-type=module", RENDER, WEB, path],
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["headCount"], 5)
        self.assertTrue(out["navHasHead"])
        self.assertTrue(out["navBadge"])  # the count reads as a number with an "open asks" screen-reader label


class HeadRender(unittest.TestCase):
    def test_demo_fixture_renders_rows_and_escapes_text(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        vm = view_model()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "vm.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(vm, fh)
            proc = subprocess.run([node, "--experimental-default-type=module", RENDER_HEAD, WEB, path],
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        screen = out["screen"]
        self.assertIn('class="hd-screen"', screen)
        self.assertIn('data-project="alpha"', screen)
        for row in vm["head"]["rows"]:
            self.assertIn('data-id="' + row["id"] + '"', screen)
        self.assertIn('data-id="H1"', out["open"])
        self.assertNotIn("<img src=x", out["open"])
        self.assertIn("&lt;img", out["open"])
        self.assertIn('href="#head?f=queue"', out["screen"])


class HeadRouteFilters(unittest.TestCase):
    """The router keeps the Head query keys for the head section only (router.js HEAD_FILTER_KEYS)."""

    def test_head_query_keys_survive_parse_and_redirect(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = (
            "const r = await import(process.argv[1]);"
            "const hashes = ['#head?f=unhandled&q=api%20fix&kind=task&sid=alpha&id=H1', '#/all/roadmap?f=state:todo&q=x'];"
            "const out = hashes.map((h) => { const p = r.parseRoute(h); return {section: p.section, filters: p.filters, redirect: p.redirect || null}; });"
            "console.log(JSON.stringify(out));"
        )
        url = "file://" + os.path.join(WEB, "js", "router.js")
        proc = subprocess.run([node, "--input-type=module", "-e", script, url],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        head, roadmap = json.loads(proc.stdout)
        self.assertEqual(head["section"], "head")
        self.assertEqual(head["filters"], {"f": "unhandled", "q": "api fix", "kind": "task", "sid": "alpha", "id": "H1"})
        self.assertIn("q=api+fix", head["redirect"])
        self.assertIn("kind=task", head["redirect"])
        self.assertEqual(roadmap["section"], "roadmap")
        self.assertEqual(roadmap["filters"], {"f": "state:todo"})
        self.assertNotIn("q=", roadmap["redirect"] or "")


class LoaderHeadKey(unittest.TestCase):
    def test_loader_passes_head_records_into_the_snapshot(self):
        src = read(LOADER)
        self.assertIn("head_records=", src)
        self.assertIn("_head_records(folder)", src)
        self.assertIn("from roadmap.services import control, head as head_store", src)

    def test_head_records_helper_is_fail_open(self):
        from roadmap.services import loader
        self.assertIsNone(loader._head_records(None))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(loader._head_records(tmp), [])


if __name__ == "__main__":
    unittest.main()
