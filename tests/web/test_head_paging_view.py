"""R7.44: the Head screen pages in the older rows of the full ledger. web/js/views/head.js is checked as source (no
browser here): the paged read is the route's offset and limit, the first paint is the snapshot rows, rows are merged
and deduped by id, the counts come from the ledger total, the list end is watched by an IntersectionObserver with a
Load more button as the fallback, nothing is inline (CSP), and the module parses in node when node is installed.
web/css/head.css belongs to another worker and is not checked here."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
JS = os.path.join(REPO, "web", "js", "views", "head.js")
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)


def _source():
    with open(JS, encoding="utf-8") as fh:
        return fh.read()


class PagingSource(unittest.TestCase):
    def setUp(self):
        self.src = _source()

    def test_pages_come_from_the_paged_route(self):
        self.assertIn('"/head?f=" + scope + "&offset=" + pg.offset', self.src)
        self.assertIn("const PAGE_SIZE = 50;", self.src)
        self.assertIn('"&limit=" + PAGE_SIZE', self.src)
        self.assertIn('getJson(url)', self.src)

    def test_first_paint_uses_the_snapshot_rows_and_merges_by_id(self):
        self.assertIn("const snapHead = vm.project.snapshot.head || null;", self.src)
        self.assertIn("function mergeRows(first, extra)", self.src)
        self.assertIn("seen.has(key)", self.src)

    def test_counts_come_from_the_ledger_total(self):
        self.assertIn("head.ledger = true;", self.src)
        self.assertIn("if (head.ledger) return", self.src)
        self.assertIn("pg.counts = data.counts", self.src)

    def test_end_of_list_and_load_more(self):
        self.assertIn("IntersectionObserver", self.src)
        self.assertIn('data-action="head-more"', self.src)
        self.assertIn("Load more", self.src)
        self.assertIn("Showing ", self.src)
        self.assertIn('class="hd-end"', self.src)
        self.assertIn('document.dispatchEvent(new Event("rb:render"))', self.src)

    def test_a_failed_page_is_not_retried_by_the_observer(self):
        self.assertIn("(auto && pg.error)", self.src)

    def test_no_inline_markup(self):
        self.assertIsNone(INLINE.search(self.src))

    def test_the_module_parses_in_node_when_node_is_installed(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        tmp = tempfile.mkdtemp(prefix="head-paging-js-")
        self.addCleanup(shutil.rmtree, tmp, True)
        copy = os.path.join(tmp, "head.mjs")
        shutil.copy(JS, copy)
        res = subprocess.run([node, "--check", copy], capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
