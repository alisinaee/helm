// System context menu (R11.105): header (name, kind, progress), action items, optional inline task list.
// menuItems/menuHtml/placeMenu/nextIndex are pure; openMenu/closeMenu/bindContextMenu touch the DOM.

import { esc, chipHtml, meterHtml, setHtml } from "../dom.js";

const LIST_MAX = 12;
const LONG_PRESS_MS = 500;
const LONG_PRESS_MOVE = 8;
let el = null;
let current = null;

function len(v) { return Array.isArray(v) ? v.length : 0; }

export function menuItems(target, d, opts) {
  const o = opts || {};
  const t = target || {};
  const n = len(d && d.board) + len(d && d.work);
  const items = [
    { action: "details", label: "Details" },
    { action: "tasks", label: "Tasks (" + n + ")", disabled: n === 0 },
    { action: "work", label: "Open in Work" },
    { action: "copy", label: "Copy id" },
    { action: "ask", label: "Ask Head about it" },
  ];
  if (t.group || t.kind === "container" || t.kind === "group") {
    items.push({ action: "toggle", label: o.expanded ? "Collapse" : "Expand" });
  }
  if (o.canDrill) items.push({ action: "drill", label: "Open sub-diagram" });
  items.push({ action: "views", label: "Show in other views" });
  return items;
}

function taskRows(d, pid) {
  const rows = [];
  const p = encodeURIComponent(pid || "");
  for (const b of (d && d.board) || []) {
    rows.push({ id: b.id, title: b.title, status: b.status,
      href: "#/p/" + p + "/planner?f=" + encodeURIComponent(b.id) });
  }
  for (const w of (d && d.work) || []) {
    rows.push({ id: w.id, title: w.title, status: w.status,
      href: "#/p/" + p + "/work/i/" + encodeURIComponent(w.id) });
  }
  return rows;
}

function listHtml(d, pid) {
  const rows = taskRows(d, pid);
  const shown = rows.slice(0, LIST_MAX).map((r) =>
    '<a class="sys-menu-row" role="menuitem" href="' + esc(r.href) + '">' +
    chipHtml(r.status || "-", "neutral") +
    '<span class="sys-menu-id">' + esc(r.id) + '</span><span class="sys-menu-t">' + esc(r.title) +
    "</span></a>").join("");
  const more = rows.length > LIST_MAX ?
    '<span class="sys-menu-more">+' + (rows.length - LIST_MAX) + " more</span>" : "";
  return '<div class="sys-menu-list">' + shown + more + "</div>";
}

export function menuHtml(target, d, opts) {
  const o = opts || {};
  const t = target || {};
  const pr = d && d.progress;
  const prog = pr && pr.total > 0
    ? meterHtml(pr.pct) + '<span class="sys-menu-p">' + esc(pr.done) + "/" + esc(pr.total) + " done</span>" : "";
  const head = '<div class="sys-menu-h"><span class="sys-menu-n">' + esc(t.label || t.id) + "</span>" +
    chipHtml(t.kind || "node", "neutral") + prog + "</div>";
  const id = esc(t.id);
  const btn = (it) => '<button type="button" class="sys-menu-i" role="menuitem" data-sys-menu="' + esc(it.action) +
    '" data-sys-id="' + id + '"' + (it.disabled ? " disabled" : "") + ">" + esc(it.label) +
    (it.hint ? '<span class="sys-menu-hint">' + esc(it.hint) + "</span>" : "") + "</button>";
  let body = "";
  for (const it of menuItems(t, d, o)) {
    body += btn(it);
    if (it.action === "tasks" && o.showTasks) body += listHtml(d, o.pid);
    if (it.action === "ask" || it.action === "work")
      body += it.action === "ask" ? '<div class="sys-menu-sep" role="separator"></div>' : "";
  }
  return '<div class="sys-menu" role="menu" aria-label="' + esc("Actions for " + (t.label || t.id)) + '">' +
    head + '<div class="sys-menu-sep" role="separator"></div>' + body + "</div>";
}

export function placeMenu(at, size, box) {
  const a = at || { x: 0, y: 0 };
  const w = size.w, h = size.h;
  const maxX = box.x + box.w - w, maxY = box.y + box.h - h;
  const x = Math.max(box.x, Math.min(a.x, maxX));
  const y = Math.max(box.y, Math.min(a.y, maxY));
  return { x, y };
}

// Index of the next enabled item for a key; wraps for arrows. Returns the current index when none applies.
export function nextIndex(items, i, key) {
  const ok = (k) => items[k] && !items[k].disabled;
  const n = items.length;
  if (!n) return -1;
  if (key === "Home") { for (let k = 0; k < n; k++) if (ok(k)) return k; return i; }
  if (key === "End") { for (let k = n - 1; k >= 0; k--) if (ok(k)) return k; return i; }
  const step = key === "ArrowDown" ? 1 : key === "ArrowUp" ? -1 : 0;
  if (!step) return i;
  let k = i;
  for (let c = 0; c < n; c++) {
    k = (k + step + n) % n;
    if (ok(k)) return k;
  }
  return i;
}

export function isOpen() { return Boolean(el && el.isConnected && !el.hidden); }

export function closeMenu() {
  if (!el) return;
  const back = current && current.opts && current.opts.returnFocus;
  el.hidden = true;
  el.replaceChildren();
  document.removeEventListener("pointerdown", onOutside, true);
  document.removeEventListener("keydown", onKey, true);
  current = null;
  if (back && typeof back.focus === "function") back.focus();
}

function buttons() { return el ? Array.from(el.querySelectorAll("button.sys-menu-i")) : []; }

function onOutside(e) { if (el && !el.contains(e.target)) closeMenu(); }

function onKey(e) {
  if (!isOpen()) return;
  const btns = buttons();
  const items = btns.map((b) => ({ disabled: b.disabled }));
  const i = btns.indexOf(document.activeElement);
  if (e.key === "Escape" || e.key === "Tab") {
    e.preventDefault();
    closeMenu();
  } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
    e.preventDefault();
    const k = nextIndex(items, i, e.key);
    if (btns[k]) btns[k].focus();
  } else if ((e.key === "Enter" || e.key === " ") && i >= 0) {
    e.preventDefault();
    btns[i].click();
  }
}

function render() {
  const c = current;
  setHtml(el, menuHtml(c.target, c.d, c.opts));
  const m = el.firstElementChild;
  const box = c.box;
  const pos = placeMenu(c.at, { w: m.offsetWidth, h: m.offsetHeight }, box);
  el.style.left = pos.x + "px";
  el.style.top = pos.y + "px";
}

export function openMenu(host, at, target, d, opts, onAction) {
  if (!el) {
    el = document.createElement("div");
    el.className = "sys-menu-host";
    el.addEventListener("click", (e) => {
      const b = e.target.closest && e.target.closest("button.sys-menu-i");
      if (!b || b.disabled || !current) return;
      const action = b.getAttribute("data-sys-menu");
      const id = b.getAttribute("data-sys-id");
      if (action === "tasks") {
        current.opts = Object.assign({}, current.opts, { showTasks: !current.opts.showTasks });
        render();
        const again = el.querySelector('[data-sys-menu="tasks"]');
        if (again) again.focus();
        return;
      }
      const cb = current.onAction;
      closeMenu();
      if (cb) cb(action, id);
      document.dispatchEvent(new CustomEvent("system:menu", { detail: { action, id } }));
    });
  }
  if (isOpen()) closeMenu();
  if (el.parentNode !== host) host.appendChild(el);
  const hr = host.getBoundingClientRect();
  current = { at: at || { x: 0, y: 0 }, target, d, opts: Object.assign({}, opts), onAction,
    box: { x: 0, y: 0, w: host.clientWidth || hr.width, h: host.clientHeight || hr.height } };
  el.hidden = false;
  render();
  document.addEventListener("pointerdown", onOutside, true);
  document.addEventListener("keydown", onKey, true);
  const first = buttons().find((b) => !b.disabled);
  if (first) first.focus();
}

// Right-click, Shift+F10 / ContextMenu key on a focused [data-sys] node, and touch long-press.
export function bindContextMenu(svg, getTarget, open) {
  const fire = (node, pt) => {
    const t = getTarget(node);
    if (t) open(t, pt);
  };
  svg.addEventListener("contextmenu", (e) => {
    const node = e.target.closest && e.target.closest("[data-sys]");
    if (!node) return;
    e.preventDefault();
    fire(node, { x: e.clientX, y: e.clientY });
  });
  svg.addEventListener("keydown", (e) => {
    if (!(e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey))) return;
    const node = e.target.closest && e.target.closest("[data-sys]");
    if (!node) return;
    e.preventDefault();
    const r = node.getBoundingClientRect();
    fire(node, { x: r.left + r.width / 2, y: r.top + r.height / 2 });
  });
  let timer = null, start = null;
  const cancel = () => { if (timer) clearTimeout(timer); timer = null; };
  svg.addEventListener("touchstart", (e) => {
    const node = e.target.closest && e.target.closest("[data-sys]");
    const t = e.touches && e.touches[0];
    if (!node || !t) return;
    start = { x: t.clientX, y: t.clientY };
    cancel();
    timer = setTimeout(() => { timer = null; fire(node, start); }, LONG_PRESS_MS);
  }, { passive: true });
  svg.addEventListener("touchmove", (e) => {
    const t = e.touches && e.touches[0];
    if (t && start && Math.hypot(t.clientX - start.x, t.clientY - start.y) > LONG_PRESS_MOVE) cancel();
  }, { passive: true });
  svg.addEventListener("touchend", cancel);
  svg.addEventListener("touchcancel", cancel);
}
