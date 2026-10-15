// Planner v2 (R7.13 H5): the plan tree. Every row, the header included, sits in one fixed 12-column grid (see
// planner.css): toggle, outline label, F id, title with its acceptance line, phase, bar, done/total, gaps, state, Acc,
// the ⋯ menu and the copy button. Indent lives inside the title cell only, so the columns never move.
// Items come from the snapshot features rows (id, parent, label, ask, gaps, acc, done, total, state, accepted); the
// tasks of an item come from each task's feats. Only the person accepts. The pickers (Assign, Link tasks) are small
// in-flow popovers of buttons, never a native select. Writes go through cmd.js run(): feature.add, set, move, link,
// unlink, accept, rm. bind(el) attaches the listeners once; sectionView(vm) draws the markup.

import { run } from "../cmd.js";
import { chipHtml, emptyHtml, esc, meterHtml } from "../dom.js";
import { copyButton, refSummary } from "../ref.js";
import { projectHash } from "../router.js";
import { pageState } from "./inbox.js";
import { modelChip, STATE_WORD } from "./tasks.js";

const STATUS = [["", "All"], ["doing", "Doing"], ["todo", "Todo"], ["done", "Done"], ["hold", "Hold"],
  ["uncovered", "Uncovered"]];
const TONE = { done: "success", doing: "accent", todo: "neutral", hold: "defer", uncovered: "warning" };
const GRID = "pl-row row-grid";
const MAX_DEPTH = 2;
const MAX_FEATS = 3;
const PICK_CAP = 60;
const FEAT_ID = /^F[1-9][0-9]?$/;

// The view state lives here, not in the URL, so a poll keeps the filters and the open items.
const ui = { status: "", unaccepted: false, open: {}, menu: null, edit: null, pick: null, project: "", focus: "",
  panels: { wait: true, orph: true, unc: false } };
const bound = new WeakSet();
const focusMark = { key: "" };

function featuresOf(snap) {
  return snap.features || { rows: [], uncovered: [], orphans: [], counts: {} };
}

// Rows into a tree in file order: kids by parent id, top-level rows, the preorder list with depths.
function buildTree(rows) {
  const byId = {};
  for (const r of rows) byId[r.id] = r;
  const kids = {};
  const top = [];
  for (const r of rows) {
    if (r.parent && byId[r.parent]) (kids[r.parent] = kids[r.parent] || []).push(r);
    else top.push(r);
  }
  const order = [];
  const walk = function (list, depth) {
    for (const r of list) {
      order.push({ row: r, depth: depth });
      if (depth < MAX_DEPTH) walk(kids[r.id] || [], depth + 1);
    }
  };
  walk(top, 0);
  return { byId: byId, kids: kids, top: top, order: order };
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
  if (state.status && row.state !== state.status) return false;
  return !(state.unaccepted && row.accepted);
}

function shown(row, tree, state) {
  if (matches(row, state)) return true;
  return (tree.kids[row.id] || []).some((k) => shown(k, tree, state));
}

function filtering(state) {
  return Boolean(state.status || state.unaccepted);
}

function isOpen(row, depth, state) {
  if (filtering(state)) return true;
  const v = state.open[row.id];
  return v === undefined ? depth === 0 : v;
}

function workHash(row, project) {
  return projectHash(project, "work") + "?f=" + encodeURIComponent("feat:" + row.id);
}

function stateChip(row) {
  if (row.gaps > 0 && row.state !== "done") return chipHtml("gap", "warning");
  return chipHtml(row.state, TONE[row.state] === "accent" ? "neutral" : TONE[row.state] || "neutral");
}

const ASK = '<svg class="pl-ask" role="img" aria-label="you asked" viewBox="0 0 8 8"><title>you asked</title>' +
  '<circle cx="4" cy="4" r="3"/></svg>';

function taskRowHtml(feat, task, depth, ctx) {
  const blocked = ctx.blocked;
  const tid = esc(task.id);
  return '<li class="pl-task ' + GRID + '"><span></span><span class="rg-t pl-id2">' + tid + "</span>" +
    '<span class="pl-main lvl' + Math.min(depth, MAX_DEPTH) + '"><a class="rg-t" href="' +
    esc(projectHash(ctx.state.project, "work") + "/i/" + encodeURIComponent(task.id)) + '" title="' +
    esc(task.title) + '">' + esc(task.title) + "</a></span>" +
    '<span class="rg-t">' + esc(task.phase || "") + '</span><span class="pl-md">' +
    (task.model ? modelChip(task.model) : "") + "</span>" +
    '<span class="rg-num">' + (blocked.indexOf(task.id) >= 0 ? "blocked" : "") + "</span><span></span>" +
    "<span>" + chipHtml(STATE_WORD[task.state] || task.state, task.state === "done" ? "success" : "neutral") +
      "</span>" +
    '<button type="button" class="btn btn-small pl-unl" data-pl="unlink" data-task="' + tid + '" data-id="' +
    esc(feat.id) + '" aria-label="Unlink ' + tid + " from " + esc(feat.id) + '">Unlink</button></li>';
}

function popHtml(label, items, empty) {
  const list = items.length ? items.map(function (it, i) {
    return '<button type="button" class="btn btn-small" data-pl="pick" data-val="' + esc(it.val) + '"' +
      (it.off ? " disabled" : "") + (i === 0 ? ' data-focus="pl-pop-first"' : "") + ">" + esc(it.text) + "</button>";
  }).join("") : '<p class="pl-note">' + esc(empty) + "</p>";
  return '<div class="pl-pop" id="pl-pop" role="group" aria-label="' + esc(label) + '">' + list +
    '<button type="button" class="btn btn-small" data-pl="pick-close" data-focus="pl-pop-close">Close</button></div>';
}

function assignPop(snap, tree, taskId) {
  const t = (snap.tasks || []).find((x) => x.id === taskId);
  const full = t && (t.feats || []).length >= MAX_FEATS;
  const items = tree.order.map((e) => ({ val: e.row.id, off: Boolean(full),
    text: " ".repeat(e.depth * 2) + labelOf(e.row) + " " + e.row.id + " " + e.row.title }));
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
  return '<form class="pl-edit" data-pl-form="edit"><label class="sr-only" for="pl-edit-in">' + esc(label) +
    '</label><input id="pl-edit-in" name="text" type="text" autocomplete="off" required maxlength="' +
      (acc ? 160 : 80) +
    '" value="' + esc(value) + '" placeholder="' + esc(label) + '" data-focus="pl-edit">' +
    (add ? '<label class="pl-ck"><input type="checkbox" name="ask"> you asked</label>' : "") +
    '<button type="submit" class="btn btn-small btn-primary">Save</button>' +
    '<button type="button" class="btn btn-small" data-pl="edit-cancel">Cancel</button>' +
    '<span class="pl-err" role="alert"></span></form>';
}

function menuHtml(row, depth, pos, hasKids) {
  const id = esc(row.id);
  const b = (act, text, extra, dis) => '<button type="button" class="btn btn-small" data-pl="' + act + '" data-id="' +
    id +
    '"' + (extra || "") + (dis ? " disabled" : "") + ">" + text + "</button>";
  const rmOff = row.total > 0 || hasKids;
  return '<div class="pl-menu" id="pl-menu-' + id + '" role="group" aria-label="Actions for ' + id + '">' +
    b("add", "Add sub plan", "", depth >= MAX_DEPTH) + b("rename", "Rename") + b("acc-edit", "Edit acceptance") +
    b("ask", row.ask ? "Not asked" : "Mark asked") + b("link-open", "Link tasks") +
    b("move", "Move up", ' data-dir="up"', pos.i === 0) +
      b("move", "Move down", ' data-dir="down"', pos.i >= pos.n - 1) +
    b("hold", row.state === "hold" ? "Resume" : "Hold") +
    b("rm", "Remove", rmOff ? ' aria-label="Remove ' + id + ' (needs no tasks and no children)"' : "", rmOff) +
      "</div>";
}

function itemHtml(ctx, row, depth, pos) {
  const { state, tree } = ctx;
  const id = esc(row.id);
  const kids = (tree.kids[row.id] || []).filter((k) => shown(k, tree, state));
  const own = ctx.direct[row.id] || [];
  const open = isOpen(row, depth, state);
  const menu = state.menu === row.id;
  const edit = state.edit && state.edit.id === row.id ? state.edit : null;
  const pct = row.total ? (row.done / row.total) * 100 : 0;
  const link = esc(workHash(row, state.project));
  const copy = copyButton("feature", row.id, labelOf(row) + " " + row.title,
    { project: state.project, sum: refSummary("feature", row, ctx.snap) });
  const accLine = row.acc ? '<span class="rg-t pl-ax" title="' + esc(row.acc) + '">' + esc(row.acc) + "</span>" : "";
  const head = '<div class="' + GRID + '"><span><button type="button" class="btn btn-small pl-tg" data-pl="toggle" ' +
    'data-id="' + id + '" aria-expanded="' + open + '" aria-controls="pl-sub-' + id + '" data-focus="pl-tg:' + id +
    '" aria-label="' + (open ? "Hide" : "Show") + " " + (kids.length ? "sub plans" : "tasks") + " of " + id + '">' +
    (open ? "▾" : "▸") + "</button></span>" +
    '<span class="rg-t pl-lb">' + esc(labelOf(row)) + '</span><span class="rg-t pl-id">' + id + "</span>" +
    '<span class="pl-main lvl' + depth + '"><span class="pl-l1">' + (row.ask ? ASK : "") + '<a class="rg-t" href="' +
    link + '" title="' + esc(row.title) + '">' + esc(row.title) + "</a></span>" + accLine + "</span>" +
    '<span class="rg-t pl-ph">' + esc(row.phase || "") + "</span>" +
    '<span class="pl-bar">' +
      meterHtml(pct, row.state === "done" ? "success" : row.blocked > 0 ? "warning" : "accent") +
    '</span><a class="rg-num pl-ct" href="' + link + '" aria-label="' + esc(row.done + " of " + row.total +
    " tasks done, open " + row.id + " in Work") + '">' + esc(row.done + "/" + row.total) + "</a>" +
    '<span class="rg-num pl-gp">' + (row.gaps > 0 ? esc(row.gaps) : "") + "</span><span>" + stateChip(row) + "</span>" +
    '<span class="pl-ok"><input type="checkbox" data-pl="accept" data-id="' + id + '" data-state="' + esc(row.state) +
    '" data-focus="pl-ok:' + id + '" aria-label="Accepted: ' + id + " " + esc(row.title) + '"' +
    (row.accepted ? " checked" : "") + "></span>" +
    '<span><button type="button" class="btn btn-small pl-more" data-pl="menu" data-id="' + id + '" aria-expanded="' +
    menu + '"' + (menu ? ' aria-controls="pl-menu-' + id + '"' : "") + ' data-focus="pl-more:' + id +
    '" aria-label="More actions for ' + id + '">⋯</button></span>' + copy + "</div>";
  const extra = (menu ? menuHtml(row, depth, pos, kids.length > 0) : "") +
    (edit && edit.kind !== "add" ? editHtml(edit, row) : "") +
    (state.pick && state.pick.kind === "link" && state.pick.id === row.id ? linkPop(ctx.snap, row) : "");
  const sub = [];
  if (edit && edit.kind === "add") sub.push('<li class="pl-extra">' + editHtml(edit, row) + "</li>");
  kids.forEach((k, i) => sub.push(itemHtml(ctx, k, depth + 1, { i: i, n: kids.length })));
  for (const t of own) sub.push(taskRowHtml(row, t, depth + 1, ctx));
  if (!kids.length && !own.length) {
    sub.push('<li class="pl-empty">No tasks yet. Use ⋯ then Link tasks, or ask your agent.</li>');
  }
  return '<li id="pl-feat-' + id + '" class="pl-item is-' + esc(row.state) +
    (state.focus === row.id ? " is-focus" : "") +
    '">' + head + (extra ? '<div class="pl-extras">' + extra + "</div>" : "") +
    '<ul class="pl-sub" id="pl-sub-' + id + '" aria-label="Inside ' + id + '"' + (open ? "" : " hidden") + ">" +
    sub.join("") + "</ul></li>";
}

function headHtml() {
  const cols = ["", "Plan", "ID", "Title", "Phase", "Progress", "Tasks", "Gaps", "State", "Acc", "", ""];
  return '<div class="' + GRID + ' pl-head rg-head" aria-hidden="true">' +
    cols.map((c) => "<span" + (c === "Tasks" || c === "Gaps" ? ' class="rg-num"' : "") + ">" + c + "</span>").join("") +
    "</div>";
}

function liHtml(first, title, btn, pop) {
  return '<li class="pl-li"><span class="rg-t">' + esc(first) + '</span><span class="rg-t" title="' + esc(title) +
    '">' + esc(title) + "</span>" + btn + (pop || "") + "</li>";
}

function panelsHtml(snap, features, tree, state, waiting) {
  const tasks = {};
  for (const t of snap.tasks || []) tasks[t.id] = t;
  const orphans = features.orphans || [];
  const uncovered = (features.uncovered || []).filter((id) => tree.byId[id]);
  const kinds = [["wait", waiting.length, "waiting for your OK", false], ["orph", orphans.length, "orphan tasks", true],
    ["unc", uncovered.length, "uncovered", true]];
  const chips = kinds.filter((c) => c[1] > 0).map(function (c) {
    const key = c[0];
    return '<button type="button" class="btn btn-small pl-sig' + (c[3] ? " is-warn" : "") + '" data-pl="panel" ' +
      'data-val="' + key + '" aria-expanded="' + state.panels[key] + '" aria-controls="pl-panel-' + key +
      '" data-focus="pl-sig:' + key + '">' + (c[3] ? "! " : "") + c[1] + " " + c[2] + "</button>";
  });
  if (!chips.length) return "";
  const panel = (key, title, lis) => lis.length ? '<ul class="pl-panel" id="pl-panel-' + key + '" aria-label="' +
    title +
    '"' + (state.panels[key] ? "" : " hidden") + ">" + lis.join("") + "</ul>" : "";
  const accept = (r) => liHtml(labelOf(r) + " " + r.id, r.title, '<button type="button" class="btn btn-small" ' +
    'data-pl="accept-btn" data-id="' + esc(r.id) + '" aria-label="Accept ' + esc(r.id) + '">Accept</button>');
  const assign = (id) => liHtml(id, tasks[id] ? tasks[id].title : "", '<button type="button" class="btn btn-small" ' +
    'data-pl="assign-open" data-task="' + esc(id) + '" aria-haspopup="true" aria-expanded="' +
      isPick(state, "assign", id) +
    '"' + (isPick(state, "assign", id) ? ' aria-controls="pl-pop"' : "") + ' data-focus="pl-assign:' + esc(id) +
    '" aria-label="Assign ' + esc(id) + ' to a plan item">Assign</button>',
  isPick(state, "assign", id) ? assignPop(snap, tree, id) : "");
  const unc = (id) => liHtml(labelOf(tree.byId[id]) + " " +
    id, tree.byId[id].title, '<button type="button" class="btn btn-small" ' +
    'data-pl="link-open" data-id="' + esc(id) + '">Link tasks</button>');
  return '<div class="pl-sigs">' + chips.join("") + "</div>" +
    panel("wait", "Waiting for your OK", waiting.map(accept)) +
    panel("orph", "Orphan tasks", orphans.map(assign)) + panel("unc", "Uncovered plan items", uncovered.map(unc));
}

function isPick(state, kind, id) {
  const p = state.pick;
  return Boolean(p && p.kind === kind && (kind === "assign" ? p.task === id : p.id === id));
}

function toolbarHtml(state) {
  const chips = STATUS.map((s) => '<button type="button" class="btn btn-small pl-flt" data-pl="status" data-val="' +
    s[0] +
    '" aria-pressed="' + (state.status === s[0]) + '" data-focus="pl-st:' + s[0] + '">' + s[1] + "</button>").join("");
  return '<div class="pl-bar-t"><div class="pl-chips" role="group" aria-label="Filter by status">' + chips + "</div>" +
    '<label class="pl-ck"><input type="checkbox" data-pl="unaccepted" data-focus="pl-un"' +
    (state.unaccepted ? " checked" : "") + "> Unaccepted only</label>" +
    '<button type="button" class="btn btn-primary pl-add" data-pl="add" data-id="" data-focus="pl-add">' +
    "+ Plan phase</button></div>";
}

// The Planner markup for a snapshot. state: status, unaccepted, open (id to true or false), menu, edit, pick, panels.
export function plannerHtml(snap, st) {
  const state = Object.assign({ status: "", unaccepted: false, open: {}, menu: null, edit: null, pick: null,
    project: ui.project, focus: "", panels: ui.panels }, st);
  const features = featuresOf(snap);
  const rows = features.rows || [];
  const tree = buildTree(rows);
  const waiting = rows.filter((r) => r.state === "done" && !r.accepted);
  const head = '<div class="page-head"><p class="page-title">Plan</p><p class="page-note">' +
    esc(rows.length + " items · " + (features.orphans || []).length + " orphan tasks · " + waiting.length +
    " waiting for your OK") + "</p></div>";
  const addTop = state.edit && state.edit.kind === "add" && !state.edit.id ? editHtml(state.edit, {}) : "";
  if (!rows.length) {
    return head + addTop + emptyHtml("No plan yet. Ask your agent to create the roadmap.",
      '<button type="button" class="btn btn-primary" data-pl="add" data-id="" data-focus="pl-add">' +
      "+ Plan phase</button>") +
      panelsHtml(snap, features, tree, state, waiting);
  }
  const ctx = { snap: snap, tree: tree, state: state, direct: directTasks(snap), blocked: snap.blocked || [] };
  const vis = tree.top.filter((r) => shown(r, tree, state));
  const list = vis.length ? '<ul class="pl-list" aria-label="Plan">' +
    vis.map((r, i) => itemHtml(ctx, r, 0, { i: i, n: vis.length })).join("") + "</ul>"
    : emptyHtml("No plan items match these filters.");
  return head + toolbarHtml(state) + addTop + panelsHtml(snap, features, tree, state, waiting) + headHtml() + list;
}

function pickProjectHtml(vm) {
  const projects = Array.isArray(vm.projects) ? vm.projects : [];
  if (!projects.length) return emptyHtml("No projects yet.", '<a href="#/all/overview">Go to All projects</a>');
  const items = projects.map((p) => '<li><a class="btn" href="#/p/' + esc(p.id) + '/planner">' + esc(p.name || p.id) +
    "</a></li>").join("");
  return '<div class="page-head"><p class="page-title">Planner</p><p class="page-note">Pick a project</p></div>' +
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
  ui.unaccepted = false;
  if (typeof document === "undefined" || typeof setTimeout !== "function") return;
  setTimeout(function () {
    const el = document.getElementById("pl-feat-" + fid);
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "center" });
  }, 0);
}

export function sectionView(vm) {
  if (vm.route.name !== "project") return pickProjectHtml(vm);
  const state = pageState(vm);
  if (state) return state;
  ui.project = vm.route.id;
  applyFocus(vm.route, vm.project.snapshot);
  return plannerHtml(vm.project.snapshot, ui);
}

function rerender() {
  if (typeof document !== "undefined") document.dispatchEvent(new Event("rb:render"));
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

// A checkbox keeps its focus until it is left, and patch() does not redraw under a focused control. So the control
// is blurred before the redraw and the focus goes back to the same data-focus key afterwards.
function redraw(key, target) {
  if (target && typeof target.blur === "function") target.blur();
  rerender();
  focusKey(key);
}

function confirmAccept() {
  return typeof window !== "undefined" && typeof window.confirm === "function"
    ? window.confirm("This item is not done yet. Accept it anyway?") : false;
}

function startEdit(kind, id) {
  ui.edit = { kind: kind, id: id };
  ui.menu = null;
  ui.pick = null;
  if (kind === "add" && id) ui.open[id] = true;
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
    redraw("pl-more:" + pick.id);
  }
}

const ACTIONS = {
  toggle: (el, id) => {
    ui.open[id] = el.getAttribute("aria-expanded") !== "true";
    redraw("pl-tg:" + id);
  },
  menu: (el, id) => {
    ui.menu = ui.menu === id ? null : id;
    ui.pick = null;
    redraw("pl-more:" + id);
  },
  status: (el) => {
    ui.status = el.getAttribute("data-val");
    redraw("pl-st:" + ui.status);
  },
  panel: (el) => {
    const k = el.getAttribute("data-val");
    ui.panels[k] = !ui.panels[k];
    redraw("pl-sig:" + k);
  },
  add: (el, id) => startEdit("add", id),
  rename: (el, id) => startEdit("rename", id),
  "acc-edit": (el, id) => startEdit("acc", id),
  "edit-cancel": () => {
    const id = ui.edit ? ui.edit.id : "";
    ui.edit = null;
    redraw(id ? "pl-more:" + id : "pl-add");
  },
  ask: (el, id) => {
    ui.menu = null;
    const on = el.textContent === "Mark asked";
    run("feature.set", { id: id, ask: on }, { label: (on ? "Marked asked " : "Cleared asked ") + id });
    redraw("pl-more:" + id);
  },
  hold: (el, id) => {
    const on = el.textContent === "Hold";
    ui.menu = null;
    run("feature.set", { id: id, hold: on }, { label: (on ? "Held " : "Resumed ") + id });
    redraw("pl-more:" + id);
  },
  move: (el, id) => {
    run("feature.move", { id: id, dir: el.getAttribute("data-dir") }, { label: "Moved " + id });
    redraw("pl-more:" + id);
  },
  rm: (el, id) => {
    ui.menu = null;
    run("feature.rm", { id: id }, { label: "Removed " + id });
  },
  "link-open": (el, id) => {
    ui.menu = null;
    ui.pick = { kind: "link", id: id };
    redraw("pl-pop-first");
  },
  "assign-open": (el) => {
    const task = el.getAttribute("data-task");
    ui.pick = isPick(ui, "assign", task) ? null : { kind: "assign", task: task };
    redraw(ui.pick ? "pl-pop-first" : "pl-assign:" + task);
  },
  pick: (el) => onPick(el.getAttribute("data-val")),
  "pick-close": () => {
    const p = ui.pick;
    ui.pick = null;
    redraw(p && p.kind === "assign" ? "pl-assign:" + p.task : p ? "pl-more:" + p.id : "");
  },
  unlink: (el) => run("feature.unlink", { task: el.getAttribute("data-task"), feats: [el.getAttribute("data-id")] },
    { label: "Unlinked " + el.getAttribute("data-task") }),
  "accept-btn": (el, id) => run("feature.accept", { id: id, on: true }, { label: "Accepted " + id }),
};

function onClick(event) {
  const el = event.target && event.target.closest ? event.target.closest("[data-pl]") : null;
  if (!el || el.tagName !== "BUTTON" || el.disabled) return;
  const act = ACTIONS[el.getAttribute("data-pl")];
  if (act) act(el, el.getAttribute("data-id") || "");
}

function onChange(event) {
  const el = event.target;
  if (!el || !el.getAttribute) return;
  const action = el.getAttribute("data-pl");
  if (action === "unaccepted") {
    ui.unaccepted = el.checked;
    redraw("pl-un", el);
  } else if (action === "accept") {
    const id = el.getAttribute("data-id");
    const on = el.checked;
    if (on && el.getAttribute("data-state") !== "done" && !confirmAccept()) {
      el.checked = false;
      return;
    }
    run("feature.accept", { id: id, on: on }, { label: (on ? "Accepted " : "Unaccepted ") + id });
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
  redraw(edit.id ? "pl-more:" + edit.id : "pl-add");
}

// Esc closes the open form, picker or menu and returns focus to its button; arrows move inside a picker.
function onKeydown(event) {
  const t = event.target;
  if (event.key === "Escape") {
    if (ui.edit) ACTIONS["edit-cancel"]();
    else if (ui.pick) ACTIONS["pick-close"]();
    else if (ui.menu) ACTIONS.menu(null, ui.menu);
    return;
  }
  const pop = t && t.closest ? t.closest(".pl-pop") : null;
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
  el.addEventListener("change", onChange);
  el.addEventListener("submit", onSubmit);
  el.addEventListener("keydown", onKeydown);
}
