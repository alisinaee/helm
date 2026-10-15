"""R7.80: the Head list is painted in place. web/js/views/head.js keeps the .hd-list element across a refresh, matches
rows by data-id, rebuilds only the rows whose markup changed, skips the work when the snapshot rev and the paged rows
are unchanged, and updates only the age text on a 60 s timer. Runs in node with a small fake DOM (no browser here); a
node-less machine skips.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")

# A fake document: a tiny HTML parser for the markup head.js writes, classList, id and attribute lookups, and counts of
# the row (tbody or li) markup that is parsed. The clock is pinned; setTimeout and setInterval are captured.
HARNESS = r"""
const web = process.argv[2];
import { pathToFileURL } from "node:url";
const VOID = new Set(["input", "img", "br", "hr", "meta", "link", "wbr"]);
const parsed = [];
let clock = Date.parse("2026-10-15T10:00:00Z");
Date.now = () => clock;

class El {
  constructor(tag, attrs) {
    this.tagName = tag.toUpperCase();
    this.attrs = attrs || {};
    this.children = [];
    this.parentNode = null;
    this.text = "";
  }
  get classList() {
    const el = this;
    const list = () => (el.attrs.class || "").split(/\s+/).filter(Boolean);
    return {
      contains: (c) => list().indexOf(c) >= 0,
      toggle: (c, on) => {
        const set = new Set(list());
        const want = on === undefined ? !set.has(c) : Boolean(on);
        if (want) set.add(c); else set.delete(c);
        el.attrs.class = Array.from(set).join(" ");
        return want;
      },
    };
  }
  getAttribute(n) { return n in this.attrs ? String(this.attrs[n]) : null; }
  setAttribute(n, v) { this.attrs[n] = String(v); }
  get firstElementChild() { return this.children[0] || null; }
  get firstChild() { return this.children[0] || null; }
  get nextElementSibling() {
    const p = this.parentNode;
    if (!p) return null;
    return p.children[p.children.indexOf(this) + 1] || null;
  }
  get textContent() { return this.text + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) {
    this.children.forEach((c) => { c.parentNode = null; });
    this.children = [];
    this.text = String(v);
  }
  set innerHTML(html) {
    this.children.forEach((c) => { c.parentNode = null; });
    this.children = [];
    this.text = "";
    parseInto(this, html);
  }
  addEventListener() {}
  get content() { return this._content || null; }
  appendChild(c) { return this.insertBefore(c, null); }
  insertBefore(c, ref) {
    if (c.parentNode) c.parentNode.removeChild(c);
    let i = this.children.length;
    if (ref) {
      i = this.children.indexOf(ref);
      if (i < 0) throw new Error("insertBefore: reference is not a child");
    }
    this.children.splice(i, 0, c);
    c.parentNode = this;
    return c;
  }
  removeChild(c) {
    const i = this.children.indexOf(c);
    if (i < 0) throw new Error("removeChild: not a child");
    this.children.splice(i, 1);
    c.parentNode = null;
    return c;
  }
  replaceChild(n, o) {
    const i = this.children.indexOf(o);
    if (i < 0) throw new Error("replaceChild: not a child");
    if (n.parentNode) n.parentNode.removeChild(n);
    this.children[i] = n;
    n.parentNode = this;
    o.parentNode = null;
    return o;
  }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  contains(node) {
    for (let n = node; n; n = n.parentNode) if (n === this) return true;
    return false;
  }
  matches(sel) {
    return sel.split(",").some((part) => {
      const s = part.trim();
      const re = /\.([\w-]+)|#([\w-]+)|\[([\w-]+)\]|^([a-zA-Z][\w-]*)/g;
      let m;
      let ok = s.length > 0;
      const classes = (this.attrs.class || "").split(/\s+/);
      while ((m = re.exec(s))) {
        if (m[1] && classes.indexOf(m[1]) < 0) ok = false;
        if (m[2] && this.attrs.id !== m[2]) ok = false;
        if (m[3] && !(m[3] in this.attrs)) ok = false;
        if (m[4] && this.tagName !== m[4].toUpperCase()) ok = false;
      }
      return ok;
    });
  }
  all(sel) {
    const out = [];
    const walk = (node) => {
      for (const c of node.children) {
        if (c.matches(sel)) out.push(c);
        walk(c);
      }
    };
    walk(this);
    return out;
  }
  querySelector(sel) { return this.all(sel)[0] || null; }
  querySelectorAll(sel) { return selAll(this, sel); }
}

function parseAttrs(s) {
  const attrs = {};
  const re = /([^\s=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"']+)))?/g;
  let m;
  while ((m = re.exec(s))) {
    attrs[m[1]] = m[2] !== undefined ? m[2] : m[3] !== undefined ? m[3] : m[4] !== undefined ? m[4] : "";
  }
  return attrs;
}

function parseInto(container, html) {
  const stack = [container];
  const re = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>|([^<]+)/g;
  let m;
  while ((m = re.exec(html))) {
    const top = stack[stack.length - 1];
    if (m[4] !== undefined) { top.text += m[4]; continue; }
    const tag = m[2].toLowerCase();
    if (m[1] === "/") {
      for (let i = stack.length - 1; i > 0; i--) {
        if (stack[i].tagName === tag.toUpperCase()) { stack.length = i; break; }
      }
      continue;
    }
    const el = new El(tag, parseAttrs(m[3]));
    top.appendChild(el);
    if (!VOID.has(tag)) stack.push(el);
  }
  return container;
}

// Descendant selectors: the last compound is matched under the earlier ones, in order.
function selAll(scope, sel) {
  const parts = sel.trim().split(/\s+/);
  return scope.all(parts[parts.length - 1]).filter((el) => {
    let a = el.parentNode;
    for (let i = parts.length - 2; i >= 0; i--) {
      while (a && !a.matches(parts[i])) a = a.parentNode;
      if (!a) return false;
      a = a.parentNode;
    }
    return true;
  });
}
const idIndex = (root, id) => root.all("#" + id)[0] || null;
const root = new El("html", {});
const doc = {
  activeElement: null,
  createElement(tag) {
    const el = new El(tag, {});
    if (tag === "template") {
      Object.defineProperty(el, "innerHTML", {
        set(html) {
          parsed.push(html);
          const frag = parseInto(new El("fragment", {}), html);
          el._content = frag;
        },
      });
    }
    return el;
  },
  getElementById(id) { return idIndex(root, id); },
  querySelectorAll(sel) { return selAll(root, sel); },
};
globalThis.document = doc;
globalThis.window = { location: { hash: "#/p/alpha/head?f=all&view=list" } };
const queue = [];
let intervals = [];
globalThis.setTimeout = (fn) => { queue.push(fn); return 0; };
globalThis.setInterval = (fn) => { intervals.push(fn); return { unref() {} }; };
window.setTimeout = globalThis.setTimeout;
window.setInterval = globalThis.setInterval;

const head = await import(pathToFileURL(web + "/js/views/head.js").href);
const main = new El("main", { id: "main" });
root.appendChild(main);

function flush() {
  while (queue.length) queue.shift()();
}
function rowsOf(n, changed) {
  const out = [];
  for (let i = 1; i <= n; i++) {
    out.push({ id: "H" + i, kind: "ask", sum: "Item " + i + (changed === i ? " edited" : ""), status: "new",
      age: 5, stale: false, amber: false, carried: false, links: [], more: 0, acct: null, sid: "", acc: false,
      auto: false, ts: "2026-10-15T09:55:00Z", dup: null, suggest: [] });
  }
  return out;
}
let shellHtml = null;
function vmOf(rows, rev) {
  return {
    route: { name: "project", id: "alpha", section: "head" },
    project: { snapshot: { rev: rev, fetchedAt: "2026-10-15T10:00:00Z", questions: [], needsYou: [],
      head: { now: "2026-10-15T10:00:00Z",
      prev: [], counts: {}, rows: rows } } },
    head: { now: "2026-10-15T10:00:00Z", prev: [], counts: {}, rows: rows },
  };
}
function render(vm) {
  const html = head.sectionView(vm);
  if (html !== shellHtml) {
    main.innerHTML = html;
    shellHtml = html;
  }
  flush();
}
const rowParses = () => parsed.filter((h) => h.indexOf("<tbody") === 0 || h.indexOf("<li") === 0).length;
const items = () => selAll(main, ".hd-list .hd-item");
const idOfItem = (item) => item.querySelector(".hd-row").getAttribute("data-id");
const out = {};

// First paint: the list element exists and holds 6 rows.
render(vmOf(rowsOf(6), "r1"));
const list1 = main.querySelector(".hd-list");
out.firstRows = items().map(idOfItem);
const before = {};
items().forEach((item) => { before[idOfItem(item)] = item; });

// No data change: nothing is parsed, the list is the same object.
parsed.length = 0;
render(vmOf(rowsOf(6), "r1"));
out.sameNoChange = main.querySelector(".hd-list") === list1;
out.parsesNoChange = parsed.length;

// One row changed (new rev): the list is the same object, one row is parsed, the other rows are the same objects.
parsed.length = 0;
render(vmOf(rowsOf(6, 3), "r2"));
out.sameOneChange = main.querySelector(".hd-list") === list1;
out.rowParsesOneChange = rowParses();
out.untouched = items().filter((item) => before[idOfItem(item)] === item).length;
out.order = items().map(idOfItem);
out.h3Text = main.querySelector(".hd-sum") ? "" : "";

// A row added at the top and a row removed: order kept, list still the same object.
parsed.length = 0;
const fresh = { id: "H0", kind: "ask", sum: "New", status: "new", age: 0, links: [], ts: "2026-10-15T09:59:00Z" };
const withNew = [fresh].concat(rowsOf(6, 3).filter((r) => r.id !== "H2"));
render(vmOf(withNew, "r3"));
out.sameAddRemove = main.querySelector(".hd-list") === list1;
out.orderAddRemove = items().map(idOfItem);
out.rowParsesAddRemove = rowParses();

// Ages: a 60 s tick updates the age text only (no parse, same list).
const ageOf = (id) => items().filter((i) => idOfItem(i) === id)[0].querySelector(".hd-age").textContent;
const ageBefore = ageOf("H0");
clock += 25 * 60000;
parsed.length = 0;
intervals.forEach((fn) => fn());
out.ageBefore = ageBefore;
out.ageAfter = ageOf("H0");
out.parsesOnTick = parsed.length;
out.sameAfterTick = main.querySelector(".hd-list") === list1;
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class HeadInPlaceTest(unittest.TestCase):
    def run_harness(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "harness.mjs")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(HARNESS)
            res = subprocess.run(["node", path, WEB], capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
            import json
            return json.loads(res.stdout.strip().splitlines()[-1])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_list_node_kept_and_rows_in_place(self):
        out = self.run_harness()
        self.assertEqual(sorted(out["firstRows"]), ["H1", "H2", "H3", "H4", "H5", "H6"])
        self.assertTrue(out["sameNoChange"])
        self.assertEqual(out["parsesNoChange"], 0)
        self.assertTrue(out["sameOneChange"])
        self.assertEqual(out["rowParsesOneChange"], 1)
        self.assertEqual(out["untouched"], 5)
        self.assertEqual(out["order"], out["firstRows"])
        self.assertTrue(out["sameAddRemove"])
        self.assertIn("H0", out["orderAddRemove"])
        self.assertNotIn("H2", out["orderAddRemove"])
        kept = [i for i in out["firstRows"] if i != "H2"]
        self.assertEqual([i for i in out["orderAddRemove"] if i != "H0"], kept)
        self.assertEqual(out["rowParsesAddRemove"], 1)

    def test_age_tick_updates_text_only(self):
        out = self.run_harness()
        self.assertNotEqual(out["ageBefore"], out["ageAfter"])
        self.assertEqual(out["parsesOnTick"], 0)
        self.assertTrue(out["sameAfterTick"])


if __name__ == "__main__":
    unittest.main()
