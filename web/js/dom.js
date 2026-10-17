// DOM writes and markup helpers. This is the only module that assigns HTML strings to the page (lint_js enforces it).
// patch() replaces one section only when its markup changed, keeps the focused control and the scroll positions of
// the section and its scrolled descendants, and sets meter widths through the CSSOM because the CSP forbids style
// attributes.

const lastHtml = new Map();

export function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
    if (ch === "&") return "&amp;";
    if (ch === "<") return "&lt;";
    if (ch === ">") return "&gt;";
    if (ch === "\"") return "&quot;";
    return "&#39;";
  });
}

function clampPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(0, n));
}

// Set every element with data-pct to its width. Run after each write, and on any root that holds meters.
export function applyMeters(root) {
  const scope = root || document;
  const fills = scope.querySelectorAll("[data-pct]");
  for (const el of fills) {
    el.style.width = clampPct(el.getAttribute("data-pct")) + "%";
  }
}

// Replace one section's contents by morphing the live DOM toward the new markup (no library). Returns true when the DOM
// changed. Markup equal to the last write (or to the current innerHTML) is not written at all. The morph keeps every
// element that still exists (matched by id, data-key, data-id, else by tag in order), so a <details> the user opened, a
// form the user unhid, a typed value, a hover or a transition survives a refresh; only changed attributes and text are
// written. `open` and `hidden` follow the server only when the server's own value changed (see syncAttrs). While the
// user is mid-interaction inside the section (pointer down, a menu or popover open, a dirty focused field) the write is
// deferred and the latest markup is applied about 150 ms after the interaction ends. A focused control that had to be
// replaced keeps its id (or data-focus key), value and selection; scroll positions of the section and its scrolled
// descendants are kept. A minimal document without createElement (some tests) gets the plain innerHTML write.
const pending = new Map();
let flushTimer = 0;
let pointerDownTarget = null;
let listening = false;
const FLUSH_MS = 150;
const KEEP_ATTRS = ["open", "hidden"];
const BUSY_SELECTOR = ".tb-pop:not([hidden]), .tb-menu:not([hidden]), .sys-menu-host:not([hidden]), " +
  "details.wk-menu[open], [aria-haspopup][aria-expanded=\"true\"]";

function canMorph() {
  return typeof document.createElement === "function";
}

function listen() {
  if (listening || typeof document.addEventListener !== "function") return;
  listening = true;
  const down = function (ev) { pointerDownTarget = ev.target || null; };
  const up = function () {
    pointerDownTarget = null;
    scheduleFlush();
  };
  document.addEventListener("pointerdown", down, true);
  document.addEventListener("pointerup", up, true);
  document.addEventListener("pointercancel", up, true);
  document.addEventListener("focusout", scheduleFlush, true);
}

function isDirty(node) {
  if (!node || !node.tagName) return false;
  if (node.tagName === "INPUT" || node.tagName === "TEXTAREA") {
    if (node.type === "checkbox" || node.type === "radio") return node.checked !== node.defaultChecked;
    return node.value !== node.defaultValue;
  }
  if (node.tagName === "SELECT" && node.options) {
    return Array.from(node.options).some(function (o) { return o.selected !== o.defaultSelected; });
  }
  return false;
}

// True while the user is working inside el: the section should not be rewritten now.
export function isInteracting(el) {
  if (pointerDownTarget && typeof el.contains === "function" && el.contains(pointerDownTarget)) return true;
  if (typeof el.querySelector === "function" && el.querySelector(BUSY_SELECTOR)) return true;
  const active = document.activeElement;
  return Boolean(active) && typeof el.contains === "function" && el.contains(active) && isDirty(active);
}

function scheduleFlush() {
  if (!pending.size || flushTimer) return;
  flushTimer = setTimeout(flushPending, FLUSH_MS);
}

function flushPending() {
  flushTimer = 0;
  for (const [id, html] of Array.from(pending)) {
    const el = document.getElementById(id);
    if (!el) {
      pending.delete(id);
    } else if (!isInteracting(el)) {
      pending.delete(id);
      applyPatch(el, id, html);
    }
  }
  scheduleFlush();
}

export function patch(sectionId, html) {
  const el = document.getElementById(sectionId);
  if (!el) return false;
  if (lastHtml.get(sectionId) === html) {
    pending.delete(sectionId);
    return false;
  }
  if (canMorph()) {
    listen();
    if (isInteracting(el)) {
      pending.set(sectionId, html);
      scheduleFlush();
      return false;
    }
  }
  pending.delete(sectionId);
  return applyPatch(el, sectionId, html);
}

function applyPatch(el, sectionId, html) {
  if (lastHtml.get(sectionId) === html || el.innerHTML === html) {
    lastHtml.set(sectionId, html);
    return false;
  }
  const active = document.activeElement;
  const inside = Boolean(active) && el.contains(active);
  const keep = inside ? focusState(active) : null;
  const scrolled = collectScroll(el);
  writeHtml(el, html);
  lastHtml.set(sectionId, html);
  applyMeters(el);
  if (keep && !(document.activeElement && el.contains(document.activeElement))) restoreFocus(el, keep);
  restoreScroll(el, scrolled);
  return true;
}

function parseInto(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  return tpl.content || tpl;
}

// Write html into el: a morph when el already has content, a plain write for the first render.
function writeHtml(el, html) {
  if (!canMorph()) {
    el.innerHTML = html;
    return;
  }
  const src = parseInto(html);
  if (!el.firstChild) {
    el.innerHTML = html;
    stampTree(el);
    return;
  }
  morphChildren(el, src);
}

// Remember the server's open/hidden for every element that carries them (see syncAttrs).
function stampTree(root) {
  const found = typeof root.querySelectorAll === "function" ? root.querySelectorAll("details, [hidden]") : [];
  const list = Array.from(found);
  if (root.nodeType === 1) list.push(root);
  for (const node of list) stampNode(node);
}

function stampNode(node) {
  if (node.nodeType !== 1 || !node.hasAttribute) return;
  node.__srv = { open: node.hasAttribute("open"), hidden: node.hasAttribute("hidden") };
}

function keyOfChild(node) {
  if (node.nodeType !== 1) return null;
  const id = node.getAttribute("id");
  if (id) return "#" + id;
  const key = node.getAttribute("data-key");
  if (key) return "k:" + key;
  const did = node.getAttribute("data-id");
  return did ? "d:" + did : null;
}

function sigOf(node) {
  return node.nodeType === 1 ? node.nodeName : "#" + node.nodeType;
}

// Update oldEl's attributes to newEl's. `open` and `hidden` are written only when the server value differs from the
// server value of the previous render, so what the user toggled in between stays.
function syncAttrs(oldEl, newEl) {
  if (!oldEl.__srv) stampNode(oldEl);
  const srv = oldEl.__srv;
  for (const name of KEEP_ATTRS) {
    const want = newEl.hasAttribute(name);
    if (want === srv[name]) continue;
    srv[name] = want;
    if (want) oldEl.setAttribute(name, newEl.getAttribute(name));
    else oldEl.removeAttribute(name);
  }
  const next = Array.from(newEl.attributes);
  const names = new Set();
  for (const attr of next) {
    if (KEEP_ATTRS.indexOf(attr.name) >= 0) continue;
    names.add(attr.name);
    if (oldEl.getAttribute(attr.name) !== attr.value) oldEl.setAttribute(attr.name, attr.value);
  }
  for (const attr of Array.from(oldEl.attributes)) {
    if (KEEP_ATTRS.indexOf(attr.name) < 0 && !names.has(attr.name)) oldEl.removeAttribute(attr.name);
  }
}

function morphNode(oldNode, newNode) {
  if (oldNode.nodeType !== 1) {
    if (oldNode.nodeValue !== newNode.nodeValue) oldNode.nodeValue = newNode.nodeValue;
    return;
  }
  const before = oldNode.nodeName === "TEXTAREA" ? oldNode.textContent : oldNode.getAttribute("value");
  syncAttrs(oldNode, newNode);
  morphChildren(oldNode, newNode);
  syncField(oldNode, newNode, before);
}

// A field's live value or checked state follows the new markup (the attribute alone does not move it once the user
// has touched it), except for the focused control (being edited) and an unsent text draft (the server value did not
// change). Checkboxes and radios always follow the markup.
function syncField(oldEl, newEl, before) {
  const tag = oldEl.nodeName;
  if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") return;
  if (document.activeElement === oldEl) return;
  if (tag === "INPUT") {
    const kind = (oldEl.getAttribute("type") || "text").toLowerCase();
    if (kind === "checkbox" || kind === "radio") {
      const want = newEl.hasAttribute("checked");
      if (oldEl.checked !== want) oldEl.checked = want;
    } else {
      const want = newEl.getAttribute("value") || "";
      // An unsent draft stays when the server's own value did not change.
      if (oldEl.value !== want && (before || "") !== want) oldEl.value = want;
    }
  } else if (tag === "TEXTAREA") {
    if (oldEl.value !== newEl.textContent && (before || "") !== newEl.textContent) oldEl.value = newEl.textContent;
  } else if (oldEl.options) {
    Array.from(oldEl.options).forEach(function (opt, i) {
      const src = newEl.options ? newEl.options[i] : null;
      if (src && opt.selected !== src.hasAttribute("selected")) opt.selected = src.hasAttribute("selected");
    });
  }
}

// Make parent's children match newParent's, reusing old nodes: by key first, else the next unused old node of the same
// tag, in order. Cost is linear in the number of children.
function morphChildren(parent, newParent) {
  const oldKids = Array.from(parent.childNodes);
  const newKids = Array.from(newParent.childNodes);
  const keyed = new Map();
  const queues = new Map();
  for (const node of oldKids) {
    const key = keyOfChild(node);
    if (key && !keyed.has(key)) {
      keyed.set(key, node);
    } else {
      const sig = sigOf(node);
      if (!queues.has(sig)) queues.set(sig, { list: [], at: 0 });
      queues.get(sig).list.push(node);
    }
  }
  const used = new Set();
  let cursor = parent.firstChild;
  for (const nw of newKids) {
    const key = keyOfChild(nw);
    let match = null;
    if (key) {
      match = keyed.get(key) || null;
    } else {
      const q = queues.get(sigOf(nw));
      if (q && q.at < q.list.length) match = q.list[q.at++];
    }
    if (match && used.has(match)) match = null;
    if (match) {
      used.add(match);
      morphNode(match, nw);
      if (match === cursor) cursor = cursor.nextSibling;
      else parent.insertBefore(match, cursor);
    } else {
      parent.insertBefore(nw, cursor);
      used.add(nw);
      if (nw.nodeType === 1) stampTree(nw);
    }
  }
  for (const node of oldKids) {
    if (!used.has(node) && node.parentNode === parent) parent.removeChild(node);
  }
}

// A stable key for one child element among its siblings: its id, else its data-key, else its tag and class list with
// its index among the siblings that share that tag and class. `seen` counts those siblings for one parent.
function scrollKey(node, seen) {
  const id = node.getAttribute("id");
  if (id) return "#" + id;
  const dataKey = node.getAttribute("data-key");
  if (dataKey) return "[data-key=" + dataKey + "]";
  const sig = node.tagName + "." + (node.getAttribute("class") || "");
  const index = seen.get(sig) || 0;
  seen.set(sig, index + 1);
  return sig + "@" + index;
}

// The scroll position of el and of every scrolled descendant, each with its path of keys from el.
function collectScroll(root) {
  const out = [];
  function walk(node, path) {
    if (node.scrollTop > 0 || node.scrollLeft > 0) {
      out.push({ path: path, top: node.scrollTop || 0, left: node.scrollLeft || 0 });
    }
    const seen = new Map();
    for (const child of Array.from(node.children || [])) {
      walk(child, path.concat([scrollKey(child, seen)]));
    }
  }
  walk(root, []);
  return out;
}

// Find the element at a key path from root; null when a step has no match.
function findByPath(root, path) {
  let node = root;
  for (const step of path) {
    const seen = new Map();
    let found = null;
    for (const child of Array.from(node.children || [])) {
      if (scrollKey(child, seen) === step) {
        found = child;
        break;
      }
    }
    if (!found) return null;
    node = found;
  }
  return node;
}

// Put the remembered scroll positions back on the matching new elements.
function restoreScroll(root, records) {
  for (const rec of records) {
    const node = findByPath(root, rec.path);
    if (!node) continue;
    node.scrollTop = rec.top;
    node.scrollLeft = rec.left;
  }
}

const FIELD_TAGS = ["INPUT", "SELECT", "TEXTAREA"];

// The stable key of a control: its id, else its data-focus key. Null when it has neither.
function keyOf(node) {
  if (!node || !node.getAttribute) return null;
  return node.getAttribute("id") || node.getAttribute("data-focus") || null;
}

// Remember the focused control: its key, tag, value and selection (fields only; selection is read in a try because
// some input types do not expose it).
function focusState(node) {
  const key = keyOf(node);
  if (!key) return null;
  const isField = FIELD_TAGS.indexOf(node.tagName) >= 0;
  const state = { key: key, tag: node.tagName, field: isField, value: null, start: null, end: null };
  if (isField) {
    state.value = node.value;
    try {
      state.start = node.selectionStart;
      state.end = node.selectionEnd;
    } catch (err) {
      state.start = null;
      state.end = null;
    }
  }
  return state;
}

// Find the new element with the remembered key and put focus, value and selection back on it.
function restoreFocus(el, state) {
  let match = null;
  for (const candidate of el.querySelectorAll("[id], [data-focus]")) {
    if (keyOf(candidate) === state.key && candidate.tagName === state.tag) {
      match = candidate;
      break;
    }
  }
  if (!match) return;
  if (state.field) {
    match.value = state.value;
    try {
      if (state.start != null && state.end != null) match.setSelectionRange(state.start, state.end);
    } catch (err) {
      // Some input types cannot take a selection; the value is still restored.
    }
  }
  match.focus({ preventScroll: true });
}

// Replace the contents of one element that has no id (patch() needs one), by the same morph. Sets meter widths.
export function setHtml(el, html) {
  if (!el) return;
  writeHtml(el, html);
  applyMeters(el);
}

// One element parsed from markup, for a piece or row that is then placed with insertBefore or swapNode.
export function parseOne(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  return tpl.content ? tpl.content.firstElementChild : tpl.firstElementChild;
}

// Put newEl in place of oldEl (callers keep using newEl). A focused control inside oldEl keeps its focus, value and
// selection (as in patch()), and a <details> the user opened or a hidden element the user unhid stays so when the
// server's own open/hidden value did not change.
export function swapNode(oldEl, newEl) {
  const active = document.activeElement;
  const keep = Boolean(active) && oldEl.contains(active) ? focusState(active) : null;
  if (canMorph() && typeof oldEl.hasAttribute === "function" && typeof newEl.hasAttribute === "function") {
    carryState(oldEl, newEl);
  }
  oldEl.parentNode.replaceChild(newEl, oldEl);
  if (keep) restoreFocus(newEl, keep);
  return newEl;
}

function carryState(oldRoot, newRoot) {
  const pairs = [[oldRoot, newRoot]];
  const walk = function (o, n) {
    const ok = Array.from(o.children || []);
    const nk = Array.from(n.children || []);
    const seenO = new Map();
    const byKey = new Map();
    for (const c of ok) byKey.set(scrollKey(c, seenO), c);
    const seenN = new Map();
    for (const c of nk) {
      if (typeof c.hasAttribute !== "function") continue;
      const m = byKey.get(scrollKey(c, seenN));
      if (m) {
        pairs.push([m, c]);
        walk(m, c);
      }
    }
  };
  walk(oldRoot, newRoot);
  stampTree(newRoot);
  for (const [o, n] of pairs) {
    const srv = o.__srv;
    for (const name of KEEP_ATTRS) {
      const serverNow = n.hasAttribute(name);
      const serverBefore = srv ? srv[name] : o.hasAttribute(name);
      if (serverNow !== serverBefore || o.hasAttribute(name) === serverNow) continue;
      if (!n.__srv) stampNode(n);
      if (o.hasAttribute(name)) n.setAttribute(name, "");
      else n.removeAttribute(name);
    }
  }
}

export function setHidden(sectionId, hidden) {
  const el = document.getElementById(sectionId);
  if (el) el.hidden = Boolean(hidden);
}

// Markup helpers. They return strings and escape every value they are given.

export function meterHtml(pct, tone) {
  const width = pct == null ? 0 : clampPct(pct);
  return '<div class="meter tone-' + esc(tone || "accent") + '" aria-hidden="true">' +
    '<span class="meter-fill" data-pct="' + width + '"></span></div>';
}

export function chipHtml(text, kind) {
  return '<span class="chip chip-' + esc(kind || "neutral") + '">' + esc(text) + "</span>";
}

export function bannerHtml(tone, title, detail) {
  const detailHtml = detail ? '<p class="banner-detail">' + esc(detail) + "</p>" : "";
  return '<div class="banner banner-' + esc(tone) + '"><p class="banner-title">' + esc(title) + "</p>" +
    detailHtml + "</div>";
}

export function emptyHtml(title, actionHtml) {
  return '<div class="empty"><p class="empty-title">' + esc(title) + "</p>" +
    (actionHtml ? "<p>" + actionHtml + "</p>" : "") + "</div>";
}

// The placeholder lines while data loads. The wrapper is a busy region with a spoken "Loading"; the lines are hidden.
export function skeletonHtml(widths) {
  const list = widths || ["w-60", "w-90", "w-40"];
  const lines = list.map(function (w) {
    return '<span class="skel ' + esc(w) + '"></span>';
  }).join("");
  return '<div aria-busy="true"><span class="sr-only">Loading</span><div aria-hidden="true">' + lines +
    "</div></div>";
}

// SectionHeader: a disclosure button with a one-line summary, and a body that is hidden when closed.
export function sectionHtml(opts) {
  const id = opts.id;
  const expanded = Boolean(opts.open);
  const bodyId = "sec-" + id + "-body";
  return '<section class="section" aria-labelledby="sec-' + esc(id) + '-title">' +
    '<h2 class="section-h"><button type="button" class="section-head" aria-expanded="' + expanded +
    '" aria-controls="' + bodyId + '" data-action="toggle-section" data-section="' + esc(id) +
    '" data-focus="toggle-' + esc(id) + '">' +
    '<span class="section-title" id="sec-' + esc(id) + '-title">' + esc(opts.title) + "</span>" +
    '<span class="section-summary">' + esc(opts.summary || "") + "</span>" +
    '<span class="chev" aria-hidden="true">' + (expanded ? "▾" : "▸") + "</span>" +
    "</button></h2>" +
    '<div class="section-body" id="' + bodyId + '"' + (expanded ? "" : " hidden") + ">" +
    (opts.body || "") + "</div></section>";
}
