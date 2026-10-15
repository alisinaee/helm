"""R7.52: patch() in web/js/dom.js always writes the section, even while a control inside it has focus, and puts the
focused control's id (or data-focus key), value and selection back on the matching new element. web/js/views/head.js
keys its verbatim text cache by id and snapshot revision (snap.rev, else fetchedAt) and drops texts of older revisions.
The DOM behaviour runs in node with a small fake document (no browser here); the head.js checks read the source.
Skipped with a message when node is not installed."""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
DOM = os.path.join(WEB, "js", "dom.js")
HEAD = os.path.join(WEB, "js", "views", "head.js")
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)

# A fake document: innerHTML is looked up in FRAMES (html string -> child elements), and querySelectorAll matches
# only the attribute selectors it is asked for ("[id]", "[data-focus]", "[data-pct]").
HARNESS = r"""
const url = process.argv[1];
const { patch } = await import(url);

function makeEl(tag, attrs, extra) {
  const el = Object.assign({
    tagName: tag, attrs: attrs || {}, children: [], value: attrs && attrs.value || "",
    selectionStart: 0, selectionEnd: 0, _html: "",
    getAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n) ? this.attrs[n] : null; },
    setAttribute(n, v) { this.attrs[n] = String(v); },
    setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b; },
    focus() { doc.active = this; },
    contains(node) { return node === this || this.children.indexOf(node) >= 0; },
    querySelectorAll(sel) {
      const names = (sel.match(/\[([a-z-]+)\]/g) || []).map(function (s) { return s.slice(1, -1); });
      return this.children.filter(function (c) {
        return names.some(function (n) { return c.attrs[n] !== undefined; });
      });
    },
  }, extra || {});
  Object.defineProperty(el, "innerHTML", {
    get() { return this._html; },
    set(v) { this._html = v; this.children = FRAMES[v] ? FRAMES[v]() : []; },
  });
  return el;
}

const FRAMES = {
  A: function () { return [makeEl("INPUT", { id: "q", value: "old" })]; },
  B: function () { return [makeEl("INPUT", { id: "q", value: "new" })]; },
  S: function () { return [makeEl("SELECT", { "data-focus": "sort", value: "a" })]; },
  S2: function () { return [makeEl("SELECT", { "data-focus": "sort", value: "a" })]; },
  T: function () { return [makeEl("SPAN", { id: "x" })]; },
  U: function () { return [makeEl("INPUT", { id: "other", value: "z" })]; },
};
const sec = makeEl("DIV", { id: "sec" });
const doc = {
  active: null,
  get activeElement() { return this.active; },
  getElementById(id) { return id === "sec" ? sec : null; },
};
globalThis.document = doc;
const out = {};

sec.innerHTML = "A";
sec.children[0].value = "typed";
sec.children[0].selectionStart = 1;
sec.children[0].selectionEnd = 3;
doc.active = sec.children[0];
out.wroteWhileFocused = patch("sec", "B");
out.html = sec.innerHTML;
const q = sec.children[0];
out.q = { value: q.value, start: q.selectionStart, end: q.selectionEnd, focused: doc.active === q };

sec.innerHTML = "S";
doc.active = null;
const s0 = sec.children[0];
s0.value = "b";
doc.active = s0;
out.select = patch("sec", "S2") && doc.active === sec.children[0];

doc.active = null;
out.unfocusedWrites = patch("sec", "T");
out.sameHtmlSkips = patch("sec", "T");

sec.innerHTML = "A";
sec.children[0].value = "typed";
doc.active = sec.children[0];
out.noMatch = patch("sec", "U");
out.noMatchFocus = doc.active !== null && sec.children.indexOf(doc.active) >= 0;
out.noMatchHtml = sec.innerHTML;
console.log(JSON.stringify(out));
"""


def _head_source():
    with open(HEAD, encoding="utf-8") as fh:
        return fh.read()


class PatchFocus(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")

    def test_patch_writes_the_section_while_a_field_has_focus(self):
        if not self.node:
            self.skipTest("node is not installed")
        proc = subprocess.run([self.node, "--input-type=module", "-e", HARNESS, "file://" + DOM],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertTrue(out["wroteWhileFocused"])
        self.assertEqual(out["html"], "B")
        self.assertEqual(out["q"], {"value": "typed", "start": 1, "end": 3, "focused": True})
        self.assertTrue(out["select"])
        self.assertTrue(out["unfocusedWrites"])
        self.assertFalse(out["sameHtmlSkips"])
        self.assertTrue(out["noMatch"])
        self.assertFalse(out["noMatchFocus"])
        self.assertEqual(out["noMatchHtml"], "U")

    def test_dom_js_no_longer_skips_focused_fields(self):
        with open(DOM, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn('active.tagName === "SELECT" || active.tagName === "INPUT"', src)
        self.assertIn("function restoreFocus(el, state)", src)
        self.assertIn("setSelectionRange(state.start, state.end)", src)
        self.assertFalse(INLINE.search(src))


class HeadCacheRevision(unittest.TestCase):
    def setUp(self):
        self.src = _head_source()

    def test_cache_key_carries_the_revision(self):
        self.assertIn('return (pid || "") + "\\n" + id + "@" + fullRev;', self.src)
        self.assertIn('String(snap.rev || snap.fetchedAt || "")', self.src)

    def test_texts_of_an_older_revision_are_dropped(self):
        self.assertIn('if (!key.endsWith("@" + rev)) fullCache.delete(key);', self.src)
        self.assertIn("setRev(vm);", self.src)

    def test_fetch_stores_only_for_the_current_revision(self):
        self.assertIn('if (key.endsWith("@" + fullRev)) fullCache.set(key, entry);', self.src)
        self.assertFalse(INLINE.search(self.src))


if __name__ == "__main__":
    unittest.main()
