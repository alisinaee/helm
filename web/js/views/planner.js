// Planner (R7.109): the plan on the Head screen's layout and classes (.hd-* in head.css). A filter bar (All, Doing,
// Todo, Done, Waiting for your OK, Uncovered), a count line, and one table row per plan item on the Head table grid:
// ID (the stretched toggle), title with its indent and outline label, phase, state chip, done/total, the Accept button
// in a fixed column (done and not yet accepted), and the copy button. An open item shows its linked tasks as compact
// rows with status chips, then its actions (link, add sub plan, rename, acceptance, asked, move, hold, remove). Each
// item is one tbody keyed by its id: it is replaced only when its markup changes (dom.js parseOne and swapNode), so a
// refresh keeps the scroll and the focus. Data: snap.features (rows, orphans) and snap.tasks. Writes go through cmd.js
// run(): feature.add, set, move, link, unlink, accept, rm. bind(el) attaches the listeners once.

import { run } from "../cmd.js";
import { chipHtml, emptyHtml, esc, parseOne, swapNode } from "../dom.js";
import { copyButton, refSummary } from "../ref.js";
import { projectHash } from "../router.js";
import { pageState } from "./inbox.js";
import { STATE_WORD } from "./tasks.js";

const FILTERS = [["", "All"], ["doing", "Doing"], ["todo", "Todo"], ["done", "Done"],
  ["waiting", "Waiting for your OK"], ["uncovered", "Uncovered"]];
const TONE = { done: "success", doing: "sonnet", todo: "neutral", hold: "defer", uncovered: "warning" };
const LABEL = { done: "Done", doing: "Doing", todo: "Todo", hold: "Hold", uncovered: "Uncovered" };
const MAX_DEPTH = 2;
const MAX_FEATS = 3;
const PICK_CAP = 60;
const FEAT_ID = /^F[1-9][0-9]?$/;
const HEAD_CELLS = [["ID", "hd-n"], ["Title", "hd-sumc"], ["Phase", "hd-kind"], ["State", "hd-stc"],
  ["Done", "hd-age"], ["Accept", "hd-acc"], ["", "hd-cp"]];
const LIST_OPEN = '<div class="hd-list"><table class="hd-tbl" aria-label="Plan"><thead><tr>' +
  HEAD_CELLS.map(function (c) {
    return '<th scope="col" class="' + c[1] + '">' + c[0] + "</th>";
  }).join("") + "</tr></thead>";
const LIST_CLOSE = "</table></div>";
const ASK = '<svg class="pl-ask" role="img" aria-label="you asked" viewBox="0 0 8 8"><title>you asked</title>' +
  '<circle cx="4" cy="4" r="3"/></svg>';

// The view state lives here, not in the URL, so a refresh keeps the filter and the open items.
const ui = { status: "", open: {}, edit: null, pick: null, project: "", focus: "" };
const bound = new WeakSet();
const focusMark = { key: "" };
let latest = null;
let painted = null;
let pendingFocus = "";
let pendingScroll = "";

function featuresOf(snap) {
  return snap.features || { rows: [], uncovered: [], orphans: [], counts: {} };
}

// Rows into a tree in file order: kids by parent id, top-level rows, and a preorder list with depths.
function buildTree(rows) {
  const byId = {};
  for (const r of rows) byId[r.id] = r;
  const kids = {};
  const top = [];
  for (const r of rows) {
    if (r.parent && byId[r.parent]) (kids[r.parent] = kids[r.parent] || []).push(r);
    else top.push(r);
  }
  return { byId: byId, kids: kids, top: top };
}

function directTasks(snap) {
  const by = {};
  for (const t of snap.tasks || []) {
    for (const f of t.feats || []) (by[f] = by[f] || []).push(t);
  }
  return by;
}

const labelOf = (row) => row.label || row.id;

function matches(row, state) {
  if (!state.status) return true;
  if (state.status === "waiting") return row.state === "done" && !row.accepted;
  return row.state === state.status;
}

function shown(row, tree, state) {
  if (matches(row, state)) return true;
  return (tree.kids[row.id] || []).some((k) => shown(k, tree, state));
}

function isOpen(row, depth, state) {
  if (state.status) return true;
  const v = state.open[row.id];
  return v === undefined ? depth === 0 : Boolean(v);
}

// The rows to show, in order: an item's children follow it only while it is open (a filter opens them all).
function flatten(tree, state) {
  const out = [];
  const walk = function (list, depth) {
    list.forEach(function (row, i) {
      if (!shown(row, tree, state)) return;
      out.push({ row: row, depth: depth, pos: { i: i, n: list.length } });
      if (depth < MAX_DEPTH && isOpen(row, depth, state)) walk(tree.kids[row.id] || [], depth + 1);
    });
  };
  walk(tree.top, 0);
  return out;
}

// Every item in preorder (the picker lists them in plan order).
function preorder(tree) {
  const out = [];
  const walk = function (list) {
    for (const r of list) {
      out.push(r);
      walk(tree.kids[r.id] || []);
    }
  };
  walk(tree.top);
  return out;
}

function workHash(row, project) {
  return projectHash(project, "work") + "/board?f=" + encodeURIComponent("feat:" + row.id);
}

function stateChip(row) {
  if (row.gaps > 0 && row.state !== "done") return chipHtml("Gap", "warning");
  return chipHtml(LABEL[row.state] || row.state, TONE[row.state] || "neutral");
}

function taskTone(st) {
  if (st === "done" || st === "doing") return "success";
  return st === "blocked" || st === "hold" ? "warning" : "neutral";
}

function taskLi(feat, task, ctx) {
  const tid = esc(task.id);
  const href = projectHash(ctx.state.project, "work") + "/i/" + encodeURIComponent(task.id);
  const blocked = (ctx.blocked || []).indexOf(task.id) >= 0 ? chipHtml("blocked", "warning") : "";
  return '<li class="hd-link"><a class="chip chip-neutral" href="' + esc(href) + '">' + tid + "</a>" +
    '<span class="wk-st">' + chipHtml(STATE_WORD[task.state] || task.state, taskTone(task.state)) + blocked +
    "</span>" +
    '<span class="hd-lbl" title="' + esc(task.title) + '">' + esc(task.title) + "</span>" +
    '<button type="button" class="btn btn-small" data-pl="unlink" data-task="' + tid + '" data-id="' +
    esc(feat.id) + '" aria-label="Unlink ' + tid + " from " + esc(feat.id) + '">Unlink</button></li>';
}

function popHtml(label, items, empty) {
  const list = items.length ? items.map(function (it, i) {
    return '<button type="button" class="btn btn-small" data-pl="pick" data-val="' + esc(it.val) + '"' +
      (it.off ? " disabled" : "") + (i === 0 ? ' data-focus="pl-pop-first"' : "") + "><span>" + esc(it.text) +
      "</span></button>";
  }).join("") : '<p class="hd-none">' + esc(empty) + "</p>";
  return '<div class="hd-blk" id="pl-pop" role="group" aria-label="' + esc(label) + '"><div class="hd-acts">' +
    list + '<button type="button" class="btn btn-small" data-pl="pick-close" data-focus="pl-pop-close">Close</button>' +
    "</div></div>";
}

function assignPop(snap, tree, taskId) {
  const t = (snap.tasks || []).find((x) => x.id === taskId);
  const full = t && (t.feats || []).length >= MAX_FEATS;
  const items = preorder(tree).map((r) => ({ val: r.id, off: Boolean(full),
    text: labelOf(r) + " " + r.id + " " + r.title }));
  return popHtml("Assign " + taskId + " to a plan item (max 3)", items, "No plan items yet.");
}

function linkPop(snap, feat) {
  const open = (snap.tasks || []).filter((t) => (t.feats || []).indexOf(feat.id) < 0 &&
    (t.feats || []).length < MAX_FEATS);
  open.sort((a, b) => (a.feats || []).length - (b.feats || []).length);
  const items = open.slice(0, PICK_CAP).map((t) => ({ val: t.id, text: t.id + " " + t.title }));
  return popHtml("Link a task to " + feat.id, items, "Every task is linked or full.");
}

function editHtml(edit, row) {
  const add = edit.kind === "add";
  const acc = edit.kind === "acc";
  const label = add ? "New plan item title" : acc ? "Acceptance for " + row.id : "Rename " + row.id;
  const value = add ? "" : acc ? row.acc || "" : row.title;
  return '<form class="hd-form" data-pl-form="edit"><label class="sr-only" for="pl-edit-in">' + esc(label) +
    '</label><input id="pl-edit-in" name="text" type="text" autocomplete="off" required maxlength="' +
    (acc ? 160 : 80) + '" value="' + esc(value) + '" placeholder="' + esc(label) + '" data-focus="pl-edit">' +
    (add ? '<label class="hd-lbl"><input type="checkbox" name="ask"> you asked</label>' : "") +
    '<button type="submit" class="btn btn-small btn-primary">Save</button>' +
    '<button type="button" class="btn btn-small" data-pl="edit-cancel" data-focus="pl-edit-cancel">Cancel</button>' +
    '<span class="pl-err" role="alert"></span></form>';
}

function tasksHtml(ctx, row, own) {
  const list = own.length ? own.map((t) => taskLi(row, t, ctx)).join("")
    : '<li class="hd-none">No tasks yet. Use Link tasks, or ask your agent.</li>';
  return '<div class="hd-blk"><p class="hd-lbl">Linked tasks</p><ul class="hd-links" aria-label="Tasks of ' +
    esc(row.id) + '">' + list + "</ul></div>";
}

function actionsHtml(row, depth, pos, hasKids) {
  const id = esc(row.id);
  const b = (act, text, extra, dis) => '<button type="button" class="btn btn-small" data-pl="' + act +
    '" data-id="' + id + '"' + (extra || "") + (dis ? " disabled" : "") + ">" + text + "</button>";
  const rmOff = row.total > 0 || hasKids;
  return '<div class="hd-blk"><div class="hd-acts" aria-label="Actions for ' + id + '">' +
    b("link-open", "Link tasks") +
    b("add", "Add sub plan", "", depth >= MAX_DEPTH) + b("rename", "Rename") + b("acc-edit", "Edit acceptance") +
    b("ask", row.ask ? "Not asked" : "Mark asked", ' data-val="' + (row.ask ? "off" : "on") + '"') +
    b("move", "Move up", ' data-dir="up"', pos.i === 0) +
    b("move", "Move down", ' data-dir="down"', pos.i >= pos.n - 1) +
    b("hold", row.state === "hold" ? "Resume" : "Hold", ' data-val="' + (row.state === "hold" ? "off" : "on") + '"') +
    (row.accepted ? b("unaccept", "Unaccept") : "") +
    b("rm", "Remove", rmOff ? ' aria-label="Remove ' + id + ' (needs no tasks and no children)"' : "", rmOff) +
    "</div></div>";
}

// One plan item: a tbody with its row and its detail (the linked tasks, an open form or picker, the actions).
function featHtml(ctx, row, depth, pos) {
  const { state, tree } = ctx;
  const id = esc(row.id);
  const open = isOpen(row, depth, state);
  const kids = tree.kids[row.id] || [];
  const own = ctx.direct[row.id] || [];
  const link = esc(workHash(row, state.project));
  const edit = state.edit && state.edit.id === row.id ? state.edit : null;
  const pick = state.pick && state.pick.kind === "link" && state.pick.id === row.id ? linkPop(ctx.snap, row) : "";
  const copy = copyButton("feature", row.id, labelOf(row) + " " + row.title,
    { project: state.project, sum: refSummary("feature", row, ctx.snap) });
  const acc = row.acc ? '<div class="hd-lbl" title="' + esc(row.acc) + '">' + esc(row.acc) + "</div>" : "";
  const accept = row.state === "done" && !row.accepted
    ? '<button type="button" class="btn btn-small" data-pl="accept-btn" data-id="' + id + '" aria-label="Accept ' +
      id + '" data-focus="pl-ok:' + id + '">Accept</button>'
    : row.accepted ? '<span aria-label="Accepted" title="Accepted">✓</span>' : "";
  const title = '<div class="hd-sum lvl' + Math.min(depth, MAX_DEPTH) + '">' + (row.ask ? ASK : "") +
    '<span class="hd-lbl">' + esc(labelOf(row)) + "</span> " + '<a href="' + link + '" title="' +
    esc(row.title) + '">' + esc(row.title) + "</a></div>" + acc;
  const head = '<tr class="hd-row" data-id="' + id + '"><td class="hd-n">' +
    '<button type="button" class="hd-hit" data-pl="toggle" data-id="' + id + '" aria-expanded="' + open +
    '" aria-controls="pl-sub-' + id + '" data-focus="pl-tg:' + id + '" aria-label="' + (open ? "Hide " : "Show ") +
    id + '">' + id + "</button></td>" +
    '<td class="hd-sumc">' + title + "</td>" +
    '<td class="hd-kind">' + esc(row.phase || "") + "</td>" +
    '<td class="hd-stc">' + stateChip(row) + "</td>" +
    '<td class="hd-age rg-num" title="' + esc((row.done || 0) + " of " + (row.total || 0) + " tasks done") + '">' +
    esc((row.done || 0) + "/" + (row.total || 0)) + "</td>" +
    '<td class="hd-acc">' + accept + "</td>" +
    '<td class="hd-cp">' + copy + "</td></tr>";
  const detail = '<tr class="hd-detail" id="pl-sub-' + id + '"><td colspan="7"><div class="hd-panel">' +
    tasksHtml(ctx, row, own) + (edit ? editHtml(edit, row) : "") + pick +
    actionsHtml(row, depth, pos, kids.length > 0) + "</div></td></tr>";
  return '<tbody class="hd-item' + (open ? " is-open" : "") + (state.focus === row.id ? " is-focus" : "") +
    '" id="pl-feat-' + id + '" data-id="' + id + '">' + head + detail + "</tbody>";
}

function isPick(state, kind, id) {
  const p = state.pick;
  return Boolean(p && p.kind === kind && (kind === "assign" ? p.task === id : p.id === id));
}

// The orphan tasks (no plan item): one row each with an Assign button; the picker opens under the list.
function orphansHtml(snap, features, tree, state) {
  const orphans = features.orphans || [];
  if (!orphans.length) return "";
  const tasks = {};
  for (const t of snap.tasks || []) tasks[t.id] = t;
  const items = orphans.map(function (id) {
    const t = tasks[id];
    return '<li class="hd-link"><span class="chip chip-neutral">' + esc(id) + '</span>' +
    '<span class="wk-st"></span><span class="hd-lbl">' +
      esc(t ? t.title : "") + '</span><button type="button" class="btn btn-small" data-pl="assign-open" data-task="' +
      esc(id) + '" aria-haspopup="true" data-focus="pl-assign:' +
      esc(id) + '" aria-label="Assign ' + esc(id) + ' to a plan item">Assign</button></li>';
  }).join("");
  const pick = state.pick && state.pick.kind === "assign" ? assignPop(snap, tree, state.pick.task) : "";
  return '<div class="hd-blk"><p class="hd-lbl">Orphan tasks (not in any plan item)</p><ul class="hd-links" ' +
    'aria-label="Orphan tasks">' + items + "</ul>" + pick + "</div>";
}

// The Status options for the Work toolbar's Filters popover (R11.119); the token is "st:" + the status.
export function filterGroups() {
  // No All option: no choice on means All (the badge counts only real choices).
  return [{ id: "plan", label: "Status", options: FILTERS.filter(function (f) {
    return f[0] !== "";
  }).map(function (f) {
    return { token: "st:" + f[0], label: f[1], on: ui.status === f[0] };
  }) }];
}

// Sets the Status filter. With toggle, a choice that is already on turns back to All (the popover is one choice).
export function setStatusFilter(val, toggle) {
  ui.status = toggle && ui.status === val ? "" : val;
}

function countHtml(shownCount, total) {
  return '<p class="hd-count">' + esc("Showing " + shownCount + " of " + total) + "</p>";
}

function topHtml() {
  return '<div class="hd-top"><h2 id="pl-h" class="hd-title sr-only">Plan</h2>' +
    '<button type="button" class="btn btn-primary" data-pl="add" data-id="" data-focus="pl-add">' +
    "<span>+ Plan phase</span></button></div>";
}

// The screen pieces in order. A piece with an empty html is absent; the list piece carries its tbody items.
function piecesOf(snap, state) {
  const features = featuresOf(snap);
  const rows = features.rows || [];
  const tree = buildTree(rows);
  const ctx = { snap: snap, tree: tree, state: state, direct: directTasks(snap), blocked: snap.blocked || [] };
  const pieces = [{ name: "top", html: topHtml() }];
  const addTop = state.edit && state.edit.kind === "add" && !state.edit.id ? editHtml(state.edit, {}) : "";
  if (!rows.length) {
    pieces.push({ name: "add", html: addTop });
    pieces.push({ name: "list", html: emptyHtml("No plan yet. Ask your agent to create the roadmap.") });
    pieces.push({ name: "orph", html: orphansHtml(snap, features, tree, state) });
    return pieces;
  }
  const flat = flatten(tree, state);
  pieces.push({ name: "bar", html: countHtml(flat.length, rows.length) });
  pieces.push({ name: "add", html: addTop });
  if (flat.length) {
    pieces.push({ name: "list", html: LIST_OPEN, close: LIST_CLOSE, items: flat.map(function (e) {
      return { id: e.row.id, html: featHtml(ctx, e.row, e.depth, e.pos) };
    }) });
  } else {
    pieces.push({ name: "list", html: emptyHtml("No plan items match these filters.") });
  }
  pieces.push({ name: "orph", html: orphansHtml(snap, features, tree, state) });
  return pieces;
}

// The Planner markup for a snapshot, as one string (no DOM). st: status, open, edit, pick, focus, project.
export function plannerHtml(snap, st) {
  const state = Object.assign({ status: "", open: {}, edit: null, pick: null, project: ui.project, focus: "" }, st);
  return piecesOf(snap, state).map(function (p) {
    return p.items ? p.html + p.items.map((e) => e.html).join("") + p.close : p.html;
  }).join("");
}

function pickProjectHtml(vm) {
  const projects = Array.isArray(vm.projects) ? vm.projects : [];
  if (!projects.length) return emptyHtml("No projects yet.", '<a href="#/all/overview">Go to All projects</a>');
  const items = projects.map((p) => '<li><a class="btn" href="#/p/' + esc(p.id) + '/work/planner">' +
    esc(p.name || p.id) + "</a></li>").join("");
  return '<div class="page-head"><p class="page-title">Work</p><p class="page-note">Pick a project</p></div>' +
    '<ul class="pl-pick-list" aria-label="Projects">' + items + "</ul>";
}

// An item in the ?f= query (the Work drawer chip links there) is opened with its ancestors, the filters are cleared,
// and the page scrolls to it once. The highlight stays while the query names it.
function applyFocus(route, snap) {
  const f = route.filters && typeof route.filters.f === "string" ? route.filters.f : "";
  const fid = FEAT_ID.test(f) ? f : "";
  const key = fid ? route.id + "#" + fid : "";
  ui.focus = fid;
  if (key === focusMark.key) return;
  focusMark.key = key;
  if (!fid) return;
  const byId = buildTree(featuresOf(snap).rows || []).byId;
  for (let r = byId[fid], n = 0; r && n < 4; n += 1) {
    ui.open[r.id] = true;
    r = r.parent ? byId[r.parent] : null;
  }
  ui.status = "";
  pendingScroll = fid;
}

// The section: an empty, stable screen element (its markup never changes, so app.js leaves it alone). The rows are
// painted into it after the render (flush), in place, so a refresh keeps the scroll and the focus.
export function sectionView(vm) {
  if (vm.route.name !== "project") return pickProjectHtml(vm);
  const state = pageState(vm);
  if (state) return state;
  return screenHtml(vm);
}

// The planner screen element alone, for the Work section's Planner view (R10.7). The caller has checked the snapshot.
export function screenHtml(vm) {
  ui.project = vm.route.id;
  applyFocus(vm.route, vm.project.snapshot);
  latest = { snap: vm.project.snapshot, state: ui };
  if (typeof setTimeout === "function") setTimeout(flush, 0);
  return '<section class="hd-screen" data-section="planner" data-project="' + esc(vm.route.id) +
    '" aria-labelledby="pl-h"></section>';
}

function firstBody(table) {
  return Array.from(table.children).find((c) => c.tagName === "TBODY") || null;
}

function bodyAfter(node) {
  let n = node.nextElementSibling;
  while (n && n.tagName !== "TBODY") n = n.nextElementSibling;
  return n;
}

// Bring the tbody items of the table in line with the piece: remove gone items, replace changed ones, keep the order.
function reconcileItems(table, piece, keys) {
  const want = new Set(piece.items.map((e) => e.id));
  const have = new Map();
  for (const el of Array.from(table.children)) {
    if (el.tagName !== "TBODY") continue;
    const id = el.getAttribute("data-id") || "";
    if (want.has(id)) have.set(id, el);
    else {
      table.removeChild(el);
      keys.delete(id);
    }
  }
  let cursor = firstBody(table);
  for (const entry of piece.items) {
    let el = have.get(entry.id) || null;
    if (!el || keys.get(entry.id) !== entry.html) {
      const fresh = parseOne(entry.html);
      if (el) {
        if (cursor === el) cursor = fresh;
        swapNode(el, fresh);
      }
      el = fresh;
      keys.set(entry.id, entry.html);
    }
    if (el === cursor) cursor = bodyAfter(cursor);
    else table.insertBefore(el, cursor);
  }
}

// Put the pieces into the screen element. A piece is replaced only when its markup changed.
function paint(screen, pieces) {
  if (!painted || painted.screen !== screen) {
    screen.textContent = "";
    painted = { screen: screen, els: new Map() };
  }
  const seen = new Set();
  const order = [];
  for (const piece of pieces) {
    if (!piece.html) continue;
    seen.add(piece.name);
    let rec = painted.els.get(piece.name);
    if (!rec) {
      rec = { el: parseOne(piece.html), html: piece.html, keys: new Map() };
      painted.els.set(piece.name, rec);
    } else if (rec.html !== piece.html) {
      rec.el = swapNode(rec.el, parseOne(piece.html));
      rec.html = piece.html;
      rec.keys = new Map();
    }
    if (piece.items) reconcileItems(rec.el.firstElementChild, piece, rec.keys);
    order.push(rec.el);
  }
  for (const name of Array.from(painted.els.keys())) {
    if (seen.has(name)) continue;
    const rec = painted.els.get(name);
    if (rec.el.parentNode === screen) screen.removeChild(rec.el);
    painted.els.delete(name);
  }
  let cursor = screen.firstElementChild;
  for (const el of order) {
    if (el === cursor) cursor = cursor.nextElementSibling;
    else screen.insertBefore(el, cursor);
  }
}

function focusKey(key) {
  if (!key || typeof document === "undefined") return;
  for (const el of document.querySelectorAll("[data-focus]")) {
    if (el.getAttribute("data-focus") === key) {
      el.focus({ preventScroll: true });
      return;
    }
  }
}

// Runs after the render has put the screen element in main: paints the pieces, then the pending focus and scroll.
function flush() {
  if (typeof document === "undefined" || !latest) return;
  const screen = document.querySelector('#main [data-section="planner"]');
  if (!screen) return;
  try {
    paint(screen, piecesOf(latest.snap, latest.state));
  } catch (err) {
    // A bad row must not freeze the page: show a stable error line and stop, instead of retrying every render.
    painted = null;
    screen.textContent = "The plan could not be shown: " + (err && err.message ? err.message : "unknown error");
    return;
  }
  const key = pendingFocus;
  pendingFocus = "";
  focusKey(key);
  if (pendingScroll) {
    const el = document.getElementById("pl-feat-" + pendingScroll);
    pendingScroll = "";
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "center" });
  }
}

// Redraws through the app render. The focus goes back to the control named by key once the rows are painted.
function redraw(key) {
  pendingFocus = key || "";
  if (typeof document !== "undefined") document.dispatchEvent(new Event("rb:render"));
}

function startEdit(kind, id) {
  ui.edit = { kind: kind, id: id };
  ui.pick = null;
  if (id) ui.open[id] = true;
  redraw("pl-edit");
}

function onPick(val) {
  const pick = ui.pick;
  ui.pick = null;
  if (!pick) return;
  if (pick.kind === "assign") {
    run("feature.link", { task: pick.task, feats: [val] }, { label: "Assigned " + pick.task + " to " + val });
    redraw("pl-assign:" + pick.task);
  } else {
    run("feature.link", { task: val, feats: [pick.id] }, { label: "Linked " + val + " to " + pick.id });
    redraw("pl-tg:" + pick.id);
  }
}

function setOpen(id, on) {
  ui.open[id] = on;
  redraw("pl-tg:" + id);
}

const ACTIONS = {
  toggle: (el, id) => setOpen(id, el.getAttribute("aria-expanded") !== "true"),
  add: (el, id) => startEdit("add", id),
  rename: (el, id) => startEdit("rename", id),
  "acc-edit": (el, id) => startEdit("acc", id),
  "edit-cancel": () => {
    const id = ui.edit ? ui.edit.id : "";
    ui.edit = null;
    redraw(id ? "pl-tg:" + id : "pl-add");
  },
  "link-open": (el, id) => {
    ui.pick = { kind: "link", id: id };
    redraw("pl-pop-first");
  },
  "assign-open": (el) => {
    const task = el.getAttribute("data-task") || "";
    ui.pick = isPick(ui, "assign", task) ? null : { kind: "assign", task: task };
    redraw(ui.pick ? "pl-pop-first" : "pl-assign:" + task);
  },
  pick: (el) => onPick(el.getAttribute("data-val")),
  "pick-close": () => {
    const p = ui.pick;
    ui.pick = null;
    redraw(p && p.kind === "assign" ? "pl-assign:" + p.task : p ? "pl-tg:" + p.id : "");
  },
  unlink: (el) => run("feature.unlink", { task: el.getAttribute("data-task"), feats: [el.getAttribute("data-id")] },
    { label: "Unlinked " + el.getAttribute("data-task") }),
  "accept-btn": (el, id) => run("feature.accept", { id: id, on: true }, { label: "Accepted " + id }),
  unaccept: (el, id) => run("feature.accept", { id: id, on: false }, { label: "Unaccepted " + id }),
  ask: (el, id) => {
    const on = el.getAttribute("data-val") === "on";
    run("feature.set", { id: id, ask: on }, { label: (on ? "Marked asked " : "Cleared asked ") + id });
    redraw("pl-tg:" + id);
  },
  hold: (el, id) => {
    const on = el.getAttribute("data-val") === "on";
    run("feature.set", { id: id, hold: on }, { label: (on ? "Held " : "Resumed ") + id });
    redraw("pl-tg:" + id);
  },
  move: (el, id) => {
    run("feature.move", { id: id, dir: el.getAttribute("data-dir") }, { label: "Moved " + id });
    redraw("pl-tg:" + id);
  },
  rm: (el, id) => {
    run("feature.rm", { id: id }, { label: "Removed " + id });
  },
};

function onClick(event) {
  const t = event.target;
  if (!t || !t.closest || !t.closest('[data-section="planner"]')) return;
  const el = t.closest("[data-pl]");
  if (el) {
    if (el.tagName === "BUTTON" && !el.disabled) {
      const act = ACTIONS[el.getAttribute("data-pl")];
      if (act) act(el, el.getAttribute("data-id") || "");
    }
    return;
  }
  // A click on an item row (not on a button, link or field) opens or closes it, like its ID button.
  const tr = t.closest("tr.hd-row");
  if (tr && !t.closest("a, button, input, select, textarea, label, form")) {
    const id = tr.getAttribute("data-id") || "";
    const body = tr.parentNode;
    setOpen(id, !(body && body.classList.contains("is-open")));
  }
}

function onSubmit(event) {
  const form = event.target;
  if (!form || form.getAttribute("data-pl-form") !== "edit" || !ui.edit) return;
  event.preventDefault();
  const text = form.elements.text.value.trim();
  const err = form.querySelector(".pl-err");
  if (!text && ui.edit.kind !== "acc") {
    if (err) err.textContent = "Give the item a title.";
    form.elements.text.focus();
    return;
  }
  const edit = ui.edit;
  ui.edit = null;
  if (edit.kind === "add") {
    const ask = Boolean(form.elements.ask && form.elements.ask.checked);
    run("feature.add", { title: text, acc: "", prio: 2, phase: null, parent: edit.id || null, ask: ask },
      { label: "Plan item added" });
  } else if (edit.kind === "rename") {
    run("feature.set", { id: edit.id, title: text }, { label: "Renamed " + edit.id });
  } else {
    run("feature.set", { id: edit.id, acc: text }, { label: "Acceptance set for " + edit.id });
  }
  redraw(edit.id ? "pl-tg:" + edit.id : "pl-add");
}

// Esc closes the open form or picker and returns focus to its button; arrows move inside a picker.
function onKeydown(event) {
  const t = event.target;
  if (event.key === "Escape") {
    if (typeof document === "undefined" || !document.querySelector('#main [data-section="planner"]')) return;
    if (ui.edit) ACTIONS["edit-cancel"]();
    else if (ui.pick) ACTIONS["pick-close"]();
    return;
  }
  const pop = t && t.closest ? t.closest("#pl-pop") : null;
  if (!pop || (event.key !== "ArrowDown" && event.key !== "ArrowUp")) return;
  const btns = Array.from(pop.querySelectorAll("button:not([disabled])"));
  const at = btns.indexOf(t);
  const next = btns[(at + (event.key === "ArrowDown" ? 1 : btns.length - 1)) % btns.length];
  event.preventDefault();
  if (next) next.focus();
}

// Attach the listeners once. The guard keeps the module importable without a page (tests).
export function bind(el) {
  if (!el || bound.has(el)) return;
  bound.add(el);
  el.addEventListener("click", onClick);
  el.addEventListener("submit", onSubmit);
  el.addEventListener("keydown", onKeydown);
}
