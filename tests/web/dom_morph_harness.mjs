// Node harness for tests/web/test_dom_morph.py: a tiny DOM (tree ops, attributes, a small HTML parser and selector
// matcher) just big enough to run web/js/dom.js patch() as a keyed morph. Prints one JSON object of results.
const url = process.argv[2];
const VOID = new Set(["input", "br", "img", "hr"]);

class Node {
  constructor(type) { this.nodeType = type; this.parentNode = null; this.childNodes = []; }
  get firstChild() { return this.childNodes[0] || null; }
  get nextSibling() {
    if (!this.parentNode) return null;
    const list = this.parentNode.childNodes;
    return list[list.indexOf(this) + 1] || null;
  }
  get children() { return this.childNodes.filter((n) => n.nodeType === 1); }
  get firstElementChild() { return this.children[0] || null; }
  get textContent() {
    return this.nodeType === 3 ? this.nodeValue : this.childNodes.map((n) => n.textContent).join("");
  }
  removeChild(c) { this.childNodes.splice(this.childNodes.indexOf(c), 1); c.parentNode = null; return c; }
  insertBefore(c, ref) {
    if (c.parentNode) c.parentNode.removeChild(c);
    const at = ref ? this.childNodes.indexOf(ref) : this.childNodes.length;
    this.childNodes.splice(at, 0, c);
    c.parentNode = this;
    return c;
  }
  appendChild(c) { return this.insertBefore(c, null); }
  replaceChild(n, o) { this.insertBefore(n, o); this.removeChild(o); return o; }
  contains(n) { for (let x = n; x; x = x.parentNode) if (x === this) return true; return false; }
  all() {
    const out = [];
    for (const c of this.children) { out.push(c); out.push(...c.all()); }
    return out;
  }
}

class Text extends Node {
  constructor(v) { super(3); this.nodeValue = v; this.nodeName = "#text"; }
}

class El extends Node {
  constructor(tag) {
    super(1);
    this.nodeName = tag.toUpperCase(); this.tagName = this.nodeName; this.attributes = []; this._v = null;
    this.scrollTop = 0; this.scrollLeft = 0;
  }
  getAttribute(n) { const a = this.attributes.find((x) => x.name === n); return a ? a.value : null; }
  hasAttribute(n) { return this.getAttribute(n) !== null; }
  setAttribute(n, v) {
    const a = this.attributes.find((x) => x.name === n);
    if (a) a.value = String(v); else this.attributes.push({ name: n, value: String(v) });
  }
  removeAttribute(n) { this.attributes = this.attributes.filter((x) => x.name !== n); }
  get defaultValue() { return this.getAttribute("value") || ""; }
  get value() { return this._v === null ? this.defaultValue : this._v; }
  set value(v) { this._v = String(v); }
  get checked() { return this._c === undefined ? this.hasAttribute("checked") : this._c; }
  set checked(v) { this._c = Boolean(v); }
  get type() { return this.getAttribute("type") || "text"; }
  focus() { doc.active = this; }
  setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b; }
  matches(sel) {
    const m = /^([a-z]*)((?:\.[\w-]+)*)((?:\[[^\]]+\])*)(:not\(\[hidden\]\))?$/.exec(sel.trim());
    if (!m) return false;
    if (m[1] && m[1].toUpperCase() !== this.nodeName) return false;
    const cls = (this.getAttribute("class") || "").split(/\s+/);
    for (const c of m[2].split(".").filter(Boolean)) if (!cls.includes(c)) return false;
    for (const a of (m[3].match(/\[[^\]]+\]/g) || [])) {
      const p = /^\[([\w-]+)(?:=(?:"([^"]*)"|([^\]]*)))?\]$/.exec(a);
      const got = this.getAttribute(p[1]);
      const want = p[2] !== undefined ? p[2] : p[3];
      if (got === null || (want !== undefined && got !== want)) return false;
    }
    return !(m[4] && this.hasAttribute("hidden"));
  }
  querySelectorAll(sel) { return this.all().filter((e) => sel.split(",").some((s) => e.matches(s))); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  set innerHTML(html) {
    for (const c of this.childNodes.slice()) this.removeChild(c);
    for (const c of parse(html)) this.appendChild(c);
    this._html = html;
  }
  get innerHTML() { return this._html || ""; }
}

function parse(html) {
  const root = new Node(11);
  let cur = root;
  const re = /<(\/?)([a-z0-9]+)((?:\s+[\w-]+(?:="[^"]*")?)*)\s*>|([^<]+)/g;
  let m;
  while ((m = re.exec(html))) {
    if (m[4] !== undefined) { cur.appendChild(new Text(m[4])); continue; }
    if (m[1]) { cur = cur.parentNode || root; continue; }
    const el = new El(m[2]);
    for (const a of m[3].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) el.setAttribute(a[1], a[2] === undefined ? "" : a[2]);
    cur.appendChild(el);
    if (!VOID.has(m[2])) cur = el;
  }
  return root.childNodes.slice();
}

const timers = [];
globalThis.setTimeout = (fn, ms) => { timers.push(fn); return timers.length; };
const doc = {
  active: null, byId: {}, listeners: {},
  get activeElement() { return this.active; },
  getElementById(id) { return this.byId[id] || null; },
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
  createElement(tag) {
    const t = new El(tag);
    Object.defineProperty(t, "content", {
      get() {
        const f = new Node(11);
        t.childNodes.slice().forEach((c) => f.appendChild(c));
        return f;
      },
    });
    return t;
  },
};
globalThis.document = doc;
const { patch } = await import(url);
const flush = () => { const t = timers.splice(0); t.forEach((f) => f()); };

function section(id) { const el = new El("div"); el.setAttribute("id", id); doc.byId[id] = el; return el; }
const out = {};

// 1. A <details> the user opened stays open; text still updates; the node is the same.
let s = section("a");
patch("a", '<details id="d"><summary>t</summary><p>one</p></details>');
const d = s.firstChild;
d.setAttribute("open", "");
out.d1 = patch("a", '<details id="d"><summary>t</summary><p>two</p></details>');
out.dSame = s.firstChild === d;
out.dOpen = d.hasAttribute("open");
out.dText = d.textContent;
patch("a", '<details id="d" open><summary>t</summary><p>two</p></details>');
out.dServerOpen = d.hasAttribute("open");
patch("a", '<details id="d"><summary>t</summary><p>two</p></details>');
out.dServerClose = d.hasAttribute("open");

// 2. Unchanged html returns false.
out.same = patch("a", '<details id="d"><summary>t</summary><p>two</p></details>');

// 3. Keyed reorder keeps nodes.
s = section("b");
patch("b", '<ul><li data-key="x">X</li><li data-key="y">Y</li><li data-key="z">Z</li></ul>');
const ul = s.firstChild;
const [lx, ly, lz] = ul.children;
patch("b", '<ul><li data-key="z">Z</li><li data-key="x">X2</li><li data-key="y">Y</li></ul>');
out.reorder = ul.children[0] === lz && ul.children[1] === lx && ul.children[2] === ly;
out.reorderText = lx.textContent;

// 4. A focused dirty input defers the patch; value and node survive once the interaction ends.
s = section("c");
patch("c", '<p>a</p><input id="q" value="old">');
const q = s.children[1];
q.value = "typed";
q.selectionStart = 1; q.selectionEnd = 3;
doc.active = q;
out.focusPatch = patch("c", "<p>b</p><input id=\"q\" value=\"old\">");
out.focusDeferred = s.children[0].textContent;
doc.active = null;
flush();
out.focusAfter = s.children[0].textContent;
out.inputSame = s.children[1] === q;
out.inputValue = q.value;

// 5. A focused but clean input is morphed in place and keeps focus and node.
s = section("e");
patch("e", '<p>a</p><input id="q2" value="v">');
const q2 = s.children[1];
doc.active = q2;
patch("e", '<p>b</p><input id="q2" value="v">');
out.cleanSame = s.children[1] === q2 && doc.active === q2 && s.children[0].textContent === "b";

// 6. An open popover defers the patch until it closes.
s = section("f");
patch("f", '<p>a</p><div class="tb-pop" hidden>menu</div>');
const pop = s.children[1];
pop.removeAttribute("hidden");
out.popPatch = patch("f", '<p>b</p><div class="tb-pop" hidden>menu</div>');
out.popDeferred = s.children[0].textContent;
pop.setAttribute("hidden", "");
flush();
out.popAfter = s.children[0].textContent;

// 7. A user-unhidden form stays visible while the server keeps it hidden.
s = section("g");
patch("g", '<form id="fm" hidden><input id="i1"></form><p>a</p>');
const fm = s.firstChild;
fm.removeAttribute("hidden");
patch("g", '<form id="fm" hidden><input id="i1"></form><p>b</p>');
out.formShown = !fm.hasAttribute("hidden");

// 8. 2,000 rows: a changed list morphs fast.
s = section("h");
const item = (i, sfx) => `<li data-key="r${i}">row ${i} ${sfx}</li>`;
const rows = (n, sfx) => "<ul>" + Array.from({ length: n }, (_, i) => item(i, sfx)).join("") + "</ul>";
patch("h", rows(2000, "a"));
const t0 = Date.now();
out.bigChanged = patch("h", rows(2000, "b"));
out.bigMs = Date.now() - t0;
out.bigText = s.firstChild.children[1999].textContent;

// 9. A checkbox the user ticked (not focused) follows the new markup; a focused text field keeps its typing.
s = section("i");
patch("i", '<input type="checkbox" id="cb" checked><input id="tx" value="a">');
const cb = s.children[0];
const tx = s.children[1];
cb.checked = true;
tx.value = "typed";
doc.active = null;
patch("i", '<input type="checkbox" id="cb"><input id="tx" value="b">');
out.cbUnchecked = cb.checked === false && s.children[0] === cb;
out.txFollows = tx.value === "b";
tx.value = "typing";
doc.active = tx;
s.children[0].checked = true;
patch("i", '<input type="checkbox" id="cb"><input id="tx" value="c">');
out.txFocusedKept = tx.value === "typing" || s.children[1].value === "typing";
console.log(JSON.stringify(out));
