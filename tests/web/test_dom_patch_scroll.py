"""R7.57: patch() in web/js/dom.js does not write when the markup is unchanged, and it keeps the scroll position of the
section and of each scrolled descendant (matched by id, data-key, or tag, class and index among siblings). The DOM
behaviour runs in node with a small fake document (no browser here). Skipped with a message when node is not
installed."""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
DOM = os.path.join(REPO, "web", "js", "dom.js")
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)

# A fake document: innerHTML is looked up in FRAMES (html string -> child elements) and each write is counted.
HARNESS = r"""
const url = process.argv[1];
const { patch } = await import(url);

let writes = 0;
function makeEl(tag, attrs, children) {
  return {
    tagName: tag, attrs: attrs || {}, children: children || [], scrollTop: 0, scrollLeft: 0, _html: "",
    getAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n) ? this.attrs[n] : null; },
    setAttribute(n, v) { this.attrs[n] = String(v); },
    focus() { doc.active = this; },
    contains(node) { return node === this || this.children.indexOf(node) >= 0; },
    querySelectorAll() { return []; },
    get innerHTML() { return this._html; },
    set innerHTML(v) {
      writes += 1;
      this._html = v;
      this.children = FRAMES[v] ? FRAMES[v]() : [];
    },
  };
}

function list(rowCount) {
  const rows = [];
  for (let i = 0; i < rowCount; i += 1) rows.push(makeEl("DIV", { class: "row" }));
  return makeEl("DIV", { class: "hd-list" }, rows);
}

const FRAMES = {
  L1: function () { return [list(3)]; },
  L2: function () { return [list(3)]; },
  K1: function () { return [makeEl("DIV", { "data-key": "a" }), makeEl("DIV", { "data-key": "b" })]; },
  K2: function () { return [makeEl("DIV", { "data-key": "b" }), makeEl("DIV", { "data-key": "a" })]; },
  G: function () { return [makeEl("P", { class: "gone" })]; },
};
const sec = makeEl("DIV", { id: "sec" });
const doc = {
  active: null,
  get activeElement() { return this.active; },
  getElementById(id) { return id === "sec" ? sec : null; },
};
globalThis.document = doc;
const out = {};

// Scrolled list and row: the section is rewritten and both positions come back on the new elements.
sec.innerHTML = "L1";
const oldList = sec.children[0];
oldList.scrollTop = 120;
oldList.children[1].scrollTop = 40;
writes = 0;
out.changed = patch("sec", "L2");
out.writes = writes;
const newList = sec.children[0];
out.newNode = newList !== oldList;
out.listTop = newList.scrollTop;
out.rowTop = newList.children[1].scrollTop;

// Same markup again: no write, and the scroll position is left alone.
writes = 0;
out.sameChanged = patch("sec", "L2");
out.sameWrites = writes;
out.listTopAfterSame = sec.children[0].scrollTop;

// Keyed rows keep their position when the order changes.
sec.innerHTML = "K1";
sec.children[1].scrollTop = 33;
patch("sec", "K2");
out.keyedTop = sec.children[0].getAttribute("data-key") === "b" ? sec.children[0].scrollTop : null;
out.keyedOther = sec.children[1].scrollTop;

// A scrolled element that no longer exists is dropped without an error.
sec.innerHTML = "L1";
sec.children[0].scrollTop = 50;
out.goneChanged = patch("sec", "G");
out.goneCount = sec.children.length;

console.log(JSON.stringify(out));
"""


class PatchScroll(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")

    def test_patch_keeps_scroll_and_skips_unchanged_markup(self):
        if not self.node:
            self.skipTest("node is not installed")
        proc = subprocess.run([self.node, "--input-type=module", "-e", HARNESS, "file://" + DOM],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertTrue(out["changed"])
        self.assertEqual(out["writes"], 1)
        self.assertTrue(out["newNode"])
        self.assertEqual(out["listTop"], 120)
        self.assertEqual(out["rowTop"], 40)
        self.assertFalse(out["sameChanged"])
        self.assertEqual(out["sameWrites"], 0)
        self.assertEqual(out["listTopAfterSame"], 120)
        self.assertEqual(out["keyedTop"], 33)
        self.assertEqual(out["keyedOther"], 0)
        self.assertTrue(out["goneChanged"])
        self.assertEqual(out["goneCount"], 1)

    def test_dom_js_has_no_inline_style_or_script(self):
        with open(DOM, encoding="utf-8") as fh:
            src = fh.read()
        self.assertFalse(INLINE.search(src))
        self.assertIn("function restoreScroll(root, records)", src)
        self.assertIn("if (lastHtml.get(sectionId) === html || el.innerHTML === html)", src)


if __name__ == "__main__":
    unittest.main()
