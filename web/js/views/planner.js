// Planner (WP53). Project scope only. Each feature is one row in the shared .row-grid tracks: caret, id, title with its
// acceptance line, phase, priority, a progress bar, done/total tasks, estimated and spent K, blocked count, a state
// chip, the person's Acc box and a ⋯ menu. A feature opens to its tasks (Unlink per task, a picker to link another).
// Callouts above the list name the uncovered features (no tasks) and the orphan tasks (in no feature).
// Only the person accepts: the Acc box asks first when the feature is not done.
// Writes go through cmd.js run(): feature.add, feature.set, feature.link, feature.unlink, feature.accept, feature.rm.
// bind(el) attaches the listeners once to the section element, which stays in place across renders. The router calls
// it; sectionView(vm) draws the markup through dom.js.

import { run } from "../cmd.js";
import { chipHtml, emptyHtml, esc, meterHtml } from "../dom.js";
import { fmtCount, MISSING } from "../format.js";
import { itemHash, pageState } from "./inbox.js";
import { modelChip, STATE_WORD } from "./tasks.js";

const FEAT_WORD = { done: "done", doing: "doing", todo: "todo", hold: "hold", uncovered: "uncovered" };
const FEAT_TONE = { done: "success", doing: "neutral", todo: "neutral", hold: "defer", uncovered: "warning" };
const STATUS_OPTIONS = [["", "All"], ["doing", "Doing"], ["todo", "Todo"], ["done", "Done"], ["hold", "Hold"],
  ["uncovered", "Uncovered"]];
const GRID = "pl-row row-grid";

// The view state. It lives here, not in the URL, so a poll keeps the filters and the open features.
const ui = { status: "", phase: "", unaccepted: false, open: {}, menu: null, adding: false, project: "",
  filtersOpen: false, focus: "" };
const bound = new WeakSet();
const focusMark = { key: "" };                  // the ?f= feature already opened and scrolled to (route id and id)
const FEAT_ID = /^F[1-9][0-9]?$/;

function emptyFeatures() {
  return { rows: [], uncovered: [], orphans: [], counts: {} };
}

function taskMap(snap) {
  const map = {};
  for (const t of snap.tasks || []) map[t.id] = t;
  return map;
}

function visible(row, state) {
  if (state.status && row.state !== state.status) return false;
  if (state.phase && row.phase !== state.phase) return false;
  if (state.unaccepted && row.accepted) return false;
  return true;
}

// Top-level features in snapshot order, each followed by its sub-features (one level). A sub-feature whose parent is
// filtered out, or missing, is shown at the top.
function orderedRows(rows, state) {
  const shown = rows.filter(function (r) {
    return visible(r, state);
  });
  const shownIds = {};
  for (const r of shown) shownIds[r.id] = true;
  const out = [];
  for (const row of shown) {
    if (row.parent && shownIds[row.parent]) continue;
    out.push({ row: row, depth: 0 });
    for (const child of shown) {
      if (child.parent === row.id) out.push({ row: child, depth: 1 });
    }
  }
  return out;
}

// The tasks a feature covers, its own and its sub-features', in snapshot order. A task names its features in feats,
// so the snapshot does not carry the id list.
function memberIds(snap, row, rows) {
  const group = {};
  group[row.id] = true;
  for (const r of rows) {
    if (r.parent === row.id) group[r.id] = true;
  }
  return (snap.tasks || []).filter(function (t) {
    return (t.feats || []).some(function (f) {
      return group[f] === true;
    });
  }).map(function (t) {
    return t.id;
  });
}

function accText(row) {
  if (row.acc) return row.acc;
  return row.state === "done" ? "Done: acceptance is not in the snapshot" : "No acceptance line yet";
}

function numText(value) {
  return typeof value === "number" && Number.isFinite(value) ? fmtCount(value) : MISSING;
}

function barTone(row) {
  if (row.state === "done") return "success";
  return row.blocked > 0 ? "warning" : "neutral";
}

function featOptions(features, selected) {
  return (features.rows || []).map(function (f) {
    return '<option value="' + esc(f.id) + '"' + (f.id === selected ? " selected" : "") + ">" +
      esc(f.id + " " + f.title) + "</option>";
  }).join("");
}

function phaseOptions(snap, selected) {
  return (snap.phases || []).map(function (p) {
    return '<option value="' + esc(p.id) + '"' + (p.id === selected ? " selected" : "") + ">" +
      esc(p.id + " " + (p.name || "")) + "</option>";
  }).join("");
}

function taskLinkHtml(id) {
  return '<a href="' + esc(itemHash(ui.project, id)) + '" aria-label="Open ' + esc(id) + ' in Work">→ Work</a>';
}

// One task under an open feature, in the same tracks as the feature row.
function taskRowHtml(feature, taskId, tasks, blockedIds) {
  const t = tasks[taskId];
  const id = esc(taskId);
  if (!t) {
    return '<li class="pl-task ' + GRID + '"><span></span><span class="rg-t">' + id +
      '</span><span class="rg-t pl-title">Not in the plan</span></li>';
  }
  const blocked = blockedIds.indexOf(taskId) >= 0;
  return '<li class="pl-task ' + GRID + '"><span></span><span class="rg-t">' + id + "</span>" +
    '<span class="pl-title"><span class="rg-t" title="' + esc(t.title) + '">' + esc(t.title) + "</span> " +
    taskLinkHtml(taskId) + "</span>" +
    '<span class="pl-opt">' + (t.model ? modelChip(t.model) : "") + "</span>" +
    '<span class="pl-opt"></span>' +
    '<span>' + chipHtml(STATE_WORD[t.state] || t.state, t.state === "done" ? "success" : "neutral") + "</span>" +
    '<span></span>' +
    '<span class="rg-num">' + numText(t.tokensK) + "</span>" +
    '<span class="pl-opt"></span>' +
    '<span class="rg-num">' + (blocked ? "1" : "0") + "</span>" +
    '<button type="button" class="btn btn-small pl-unlink" data-pl="unlink" data-task="' + id + '" data-feat="' +
    esc(feature.id) + '" aria-label="Unlink ' + id + " from " + esc(feature.id) + '">Unlink</button></li>';
}

function linkPickerHtml(snap, feature) {
  const linked = {};
  for (const id of feature.tasks || []) linked[id] = true;
  const options = (snap.tasks || []).filter(function (t) {
    return !linked[t.id];
  }).map(function (t) {
    return '<option value="' + esc(t.id) + '">' + esc(t.id + " " + t.title) + "</option>";
  }).join("");
  const fid = esc(feature.id);
  return '<li class="pl-task pl-pick ' + GRID + '"><span></span><label class="pl-pick-label">' +
    '<span class="sr-only">Link a task to ' + fid + "</span>" +
    '<select class="pl-select" data-pl="link" data-feat="' + fid +
    '" data-focus="pl-link:' + fid + '"><option value="">Link a task…</option>' + options +
    "</select></label></li>";
}

function menuHtml(feature, open) {
  const fid = esc(feature.id);
  const rmDisabled = feature.total > 0 ? " disabled" : "";
  const rmHelp = feature.total > 0 ? " (unlink its tasks first)" : "";
  return '<div class="pl-menu" id="pl-menu-' + fid + '" role="group" aria-label="Actions for ' + fid + '"' +
    (open ? "" : " hidden") + ">" +
    '<button type="button" class="btn btn-small" data-pl="hold" data-id="' + fid + '" data-hold="' +
    (feature.hold ? "0" : "1") + '" data-focus="pl-hold:' + fid + '">' + (feature.hold ? "Resume" : "Hold") +
    "</button>" +
    '<button type="button" class="btn btn-small" data-pl="rm" data-id="' + fid + '" data-focus="pl-rm:' + fid +
    '"' + rmDisabled + ' aria-label="Remove ' + fid + rmHelp + '">Remove</button></div>';
}

function featureHtml(snap, entry, tasks, blockedIds, state, rows) {
  const row = entry.row;
  const fid = esc(row.id);
  const open = Boolean(state.open[row.id]);
  const pct = row.total ? (row.done / row.total) * 100 : 0;
  const menuOpen = state.menu === row.id;
  const tone = FEAT_TONE[row.state] || "neutral";
  const word = FEAT_WORD[row.state] || row.state;
  const taskIds = memberIds(snap, row, rows);
  const tasksHtml = '<ul class="pl-tasks" id="pl-tasks-' + fid + '" aria-label="Tasks of ' + fid + '"' +
    (open ? "" : " hidden") + ">" + taskIds.map(function (id) {
      return taskRowHtml(row, id, tasks, blockedIds);
    }).join("") + linkPickerHtml(snap, row) + "</ul>";
  return '<li id="pl-feat-' + fid + '" class="pl-feat' + (entry.depth ? " pl-sub" : "") + " is-" + esc(row.state) +
    (state.focus === row.id ? " is-focus" : "") + '">' +
    '<div class="' + GRID + '">' +
    '<button type="button" class="btn btn-small pl-caret" data-pl="toggle" data-id="' + fid +
    '" aria-expanded="' + open + '" aria-controls="pl-tasks-' + fid + '" data-focus="pl-toggle:' + fid +
    '" aria-label="' + (open ? "Hide" : "Show") + " tasks of " + fid + '">' + (open ? "▾" : "▸") + "</button>" +
    '<span class="rg-t pl-id">' + fid + "</span>" +
    '<span class="pl-main"><span class="rg-t pl-title" title="' + esc(row.title) + '">' + esc(row.title) +
    '</span><span class="rg-t pl-acctext" title="' + esc(row.acc || "") + '">' + esc(accText(row)) +
    "</span></span>" +
    '<span class="rg-t pl-opt">' + esc(row.phase || MISSING) + "</span>" +
    '<span class="rg-num pl-opt">' + numText(row.prio) + "</span>" +
    '<span class="pl-bar">' + meterHtml(pct, tone === "success" ? "success" : barTone(row)) + "</span>" +
    '<span class="rg-num">' + esc(row.done + "/" + row.total) + "</span>" +
    '<span class="rg-num">' + numText(row.estK) + "</span>" +
    '<span class="rg-num pl-opt">' + numText(row.spentK) + "</span>" +
    '<span class="rg-num pl-opt">' + numText(row.blocked) + "</span>" +
    '<span class="pl-state">' + chipHtml(word, tone) + "</span>" +
    '<span class="pl-acc"><input type="checkbox" data-pl="accept" data-id="' + fid + '" data-state="' +
    esc(row.state) + '" data-focus="pl-acc:' + fid + '" aria-label="Accepted: ' + fid + " " + esc(row.title) + '"' +
    (row.accepted ? " checked" : "") + "></span>" +
    '<button type="button" class="btn btn-small pl-more" data-pl="menu" data-id="' + fid +
    '" aria-expanded="' + menuOpen + '" aria-controls="pl-menu-' + fid + '" data-focus="pl-menu:' + fid +
    '" aria-label="More actions for ' + fid + '">⋯</button>' + "</div>" +
    menuHtml(row, menuOpen) + tasksHtml + "</li>";
}

function calloutHtml(snap, features, state) {
  const parts = [];
  const uncovered = features.uncovered || [];
  if (uncovered.length) {
    const byId = {};
    for (const r of features.rows || []) byId[r.id] = r;
    const items = uncovered.map(function (id) {
      const r = byId[id];
      const fid = esc(id);
      return "<li>" + '<span class="rg-t">' + fid + " " + esc(r ? r.title : "") + "</span> " +
        '<button type="button" class="btn btn-small" data-pl="toggle" data-id="' + fid + '" data-focus="pl-toggle:' +
        fid + '">Link tasks</button></li>';
    }).join("");
    parts.push('<details class="pl-callout is-warning" open><summary>! ' + uncovered.length +
      " uncovered " + (uncovered.length === 1 ? "feature" : "features") + "</summary>" +
      '<ul class="pl-callout-list">' + items + "</ul></details>");
  }
  const orphans = features.orphans || [];
  if (orphans.length) {
    const tasks = taskMap(snap);
    const items = orphans.map(function (id) {
      const t = tasks[id];
      const tid = esc(id);
      return "<li>" + '<span class="rg-t">' + tid + " " + esc(t ? t.title : "") + "</span> " +
        '<label class="pl-pick-label"><span class="sr-only">Assign ' + tid + " to a feature</span>" +
        '<select class="pl-select" data-pl="assign" data-task="' + tid +
        '" data-focus="pl-assign:' + tid + '"><option value="">Assign…</option>' +
        featOptions(features, "") + "</select></label></li>";
    }).join("");
    parts.push('<details class="pl-callout is-warning" open><summary>! ' + orphans.length + " orphan " +
      (orphans.length === 1 ? "task" : "tasks") + "</summary>" +
      '<ul class="pl-callout-list">' + items + "</ul></details>");
  }
  return parts.length ? '<div class="pl-callouts" aria-label="Coverage">' + parts.join("") + "</div>" : "";
}

// On a phone the filters sit behind a toggle (the button shows how many are set); on a wide screen they always show.
function filtersHtml(snap, state) {
  const status = STATUS_OPTIONS.map(function (o) {
    return '<option value="' + o[0] + '"' + (o[0] === state.status ? " selected" : "") + ">" + o[1] + "</option>";
  }).join("");
  const set = (state.status ? 1 : 0) + (state.phase ? 1 : 0) + (state.unaccepted ? 1 : 0);
  const open = Boolean(state.filtersOpen);
  return '<button type="button" class="btn btn-small pl-filter-toggle" data-pl="filters" aria-expanded="' + open +
    '" aria-controls="pl-filters" data-focus="pl-filters-toggle">Filters' + (set ? " (" + set + ")" : "") +
    "</button>" +
    '<div class="pl-filters' + (open ? " is-open" : "") + '" id="pl-filters" role="group" ' +
    'aria-label="Filter features">' +
    '<label class="pl-field">Status <select data-pl="filter-status" data-focus="pl-filter-status">' + status +
    "</select></label>" +
    '<label class="pl-field">Phase <select data-pl="filter-phase" data-focus="pl-filter-phase">' +
    '<option value="">All</option>' + phaseOptions(snap, state.phase) + "</select></label>" +
    '<label class="pl-field pl-check"><input type="checkbox" data-pl="filter-unaccepted" ' +
    'data-focus="pl-filter-unaccepted"' + (state.unaccepted ? " checked" : "") + "> Unaccepted only</label>" +
    '<button type="button" class="btn btn-primary pl-add-inline" data-pl="adding" data-focus="pl-adding">+ Feature' +
    "</button></div>";
}

function addFormHtml(snap, features) {
  const parents = (features.rows || []).filter(function (r) {
    return !r.parent;
  });
  return '<form class="pl-add" data-pl-form="add" aria-labelledby="pl-add-h">' +
    '<h2 class="ov-h" id="pl-add-h">New feature</h2>' +
    '<p class="pl-fld"><label for="pl-add-title">Title</label>' +
    '<input id="pl-add-title" name="title" type="text" maxlength="80" required autocomplete="off"></p>' +
    '<p class="pl-fld"><label for="pl-add-acc">Acceptance (how the person knows it works)</label>' +
    '<input id="pl-add-acc" name="acc" type="text" maxlength="160" autocomplete="off"></p>' +
    '<p class="pl-fld"><label>Priority <select name="prio">' +
    '<option value="1">1 (first)</option><option value="2" selected>2</option><option value="3">3</option>' +
    "</select></label>" +
    '<label>Phase <select name="phase"><option value="">None</option>' + phaseOptions(snap, "") +
    "</select></label>" +
    '<label>Sub-feature of <select name="parent"><option value="">None (top level)</option>' +
    featOptions({ rows: parents }, "") + "</select></label></p>" +
    '<p class="pl-err" role="alert" id="pl-add-err"></p>' +
    '<p><button type="submit" class="btn btn-primary" data-focus="pl-add-submit">Add feature</button> ' +
    '<button type="button" class="btn" data-pl="adding" data-focus="pl-add-cancel">Cancel</button></p></form>';
}

function headHtml() {
  return '<div class="pl-head ' + GRID + ' rg-head" aria-hidden="true"><span></span><span>ID</span>' +
    "<span>Feature / acceptance</span><span class=\"pl-opt\">Phase</span><span class=\"pl-opt\">Pri</span>" +
    "<span>Progress</span><span>Tasks</span><span>Est K</span><span class=\"pl-opt\">Spent K</span>" +
    '<span class="pl-opt"><abbr title="Blocked tasks">Blk</abbr></span><span>State</span><span>Acc</span>' +
    "<span></span></div>";
}

// The Planner markup for a snapshot. ui: status, phase, unaccepted, open (id to true), menu (feature id), adding.
export function plannerHtml(snap, state) {
  const features = snap.features || emptyFeatures();
  const rows = features.rows || [];
  const tasks = taskMap(snap);
  const blockedIds = snap.blocked || [];
  const head = '<div class="page-head"><p class="page-title">Planner</p><p class="page-note">' +
    esc(rows.length + " features · " + (features.uncovered || []).length + " uncovered") + "</p></div>";
  const add = state.adding ? addFormHtml(snap, features) : "";
  if (!rows.length) {
    const orphans = (features.orphans || []).length;
    const orphanNote = orphans ? '<p class="page-note">' + esc(fmtCount(orphans) + " tasks are orphans.") + "</p>" : "";
    return head + add + emptyHtml("No features yet. Features say what you're building; tasks say how.",
      '<button type="button" class="btn btn-primary" data-pl="adding" data-focus="pl-adding">+ Feature</button>') +
      orphanNote;
  }
  const entries = orderedRows(rows, state);
  const list = entries.length
    ? '<ul class="pl-list" aria-label="Features">' + entries.map(function (entry) {
      return featureHtml(snap, entry, tasks, blockedIds, state, rows);
    }).join("") + "</ul>"
    : emptyHtml("No features match these filters.");
  // The floating + Feature button is for phones; the filter row carries its own on wide screens.
  const fab = state.adding ? "" : '<button type="button" class="btn btn-primary pl-fab" data-pl="adding" ' +
    'data-focus="pl-adding-fab">+ Feature</button>';
  return head + calloutHtml(snap, features, state) + add + filtersHtml(snap, state) + headHtml() + list + fab;
}

// Names the projects so the person can open a project's Planner. Used for the All projects scope.
function pickProjectHtml(vm) {
  const projects = Array.isArray(vm.projects) ? vm.projects : [];
  if (!projects.length) {
    return emptyHtml("No projects yet.", '<a href="#/all/overview">Go to All projects</a>');
  }
  const items = projects.map(function (p) {
    return '<li><a class="btn" href="#/p/' + esc(p.id) + '/planner">' + esc(p.name || p.id) + "</a></li>";
  }).join("");
  return '<div class="page-head"><p class="page-title">Planner</p><p class="page-note">Pick a project</p></div>' +
    '<ul class="pl-pick-list" aria-label="Projects">' + items + "</ul>";
}

// A feature in the ?f= query (the Work drawer chip links there) is opened, the filters are cleared so it shows, and the
// page scrolls to it once. The highlight stays while the query names it.
function focusFrom(route) {
  const f = route.filters && typeof route.filters.f === "string" ? route.filters.f : "";
  return FEAT_ID.test(f) ? f : "";
}

function applyFocus(route, fid) {
  const key = fid ? route.id + "#" + fid : "";
  ui.focus = fid;
  if (key === focusMark.key) return;
  focusMark.key = key;
  if (!fid) return;
  ui.open[fid] = true;
  ui.status = "";
  ui.phase = "";
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
  applyFocus(vm.route, focusFrom(vm.route));
  return plannerHtml(vm.project.snapshot, ui);
}

function rerender() {
  if (typeof document !== "undefined") document.dispatchEvent(new Event("rb:render"));
}

// A select or checkbox keeps its focus until it is left, and patch() does not redraw under a focused control. So the
// control is blurred before the redraw, and the focus goes back to the same data-focus key afterwards.
function redrawKeeping(target) {
  const key = target.getAttribute("data-focus");
  if (typeof target.blur === "function") target.blur();
  rerender();
  focusKey(key);
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

function confirmAccept() {
  return typeof window !== "undefined" && typeof window.confirm === "function"
    ? window.confirm("This feature is not done yet. Accept it anyway?") : false;
}

function onClick(event) {
  const el = event.target && event.target.closest ? event.target.closest("[data-pl]") : null;
  if (!el || el.tagName !== "BUTTON" || el.disabled) return;
  const action = el.getAttribute("data-pl");
  const id = el.getAttribute("data-id");
  if (action === "toggle") {
    ui.open[id] = !ui.open[id];
    rerender();
  } else if (action === "menu") {
    ui.menu = ui.menu === id ? null : id;
    rerender();
  } else if (action === "adding") {
    ui.adding = !ui.adding;
    rerender();
  } else if (action === "filters") {
    ui.filtersOpen = !ui.filtersOpen;
    rerender();
  } else if (action === "hold") {
    run("feature.set", { id: id, hold: el.getAttribute("data-hold") === "1" },
      { label: (el.getAttribute("data-hold") === "1" ? "Held " : "Resumed ") + id });
  } else if (action === "rm") {
    ui.menu = null;
    run("feature.rm", { id: id }, { label: "Removed " + id });
  } else if (action === "unlink") {
    run("feature.unlink", { task: el.getAttribute("data-task"), feat: el.getAttribute("data-feat") },
      { label: "Unlinked " + el.getAttribute("data-task") });
  }
}

function onChange(event) {
  const el = event.target;
  if (!el || !el.getAttribute) return;
  const action = el.getAttribute("data-pl");
  if (!action) return;
  if (action === "filter-status") {
    ui.status = el.value;
    redrawKeeping(el);
  } else if (action === "filter-phase") {
    ui.phase = el.value;
    redrawKeeping(el);
  } else if (action === "filter-unaccepted") {
    ui.unaccepted = el.checked;
    redrawKeeping(el);
  } else if (action === "accept") {
    const id = el.getAttribute("data-id");
    const on = el.checked;
    if (on && el.getAttribute("data-state") !== "done" && !confirmAccept()) {
      el.checked = false;
      return;
    }
    run("feature.accept", { id: id, on: on }, { label: (on ? "Accepted " : "Unaccepted ") + id });
  } else if (action === "link") {
    if (!el.value) return;
    const task = el.value;
    const feat = el.getAttribute("data-feat");
    el.blur();
    run("feature.link", { task: task, feats: [feat] }, { label: "Linked " + task + " to " + feat });
  } else if (action === "assign") {
    if (!el.value) return;
    const task = el.getAttribute("data-task");
    el.blur();
    run("feature.link", { task: task, feats: [el.value] }, { label: "Assigned " + task });
  }
}

function onSubmit(event) {
  const form = event.target;
  if (!form || form.getAttribute("data-pl-form") !== "add") return;
  event.preventDefault();
  const title = form.elements.title.value.trim();
  const err = form.querySelector(".pl-err");
  if (!title) {
    if (err) err.textContent = "Give the feature a title.";
    form.elements.title.focus();
    return;
  }
  const parent = form.elements.parent.value;
  const args = {
    title: title,
    acc: form.elements.acc.value.trim(),
    prio: Number(form.elements.prio.value),
    phase: form.elements.phase.value || null,
    parent: parent || null,
  };
  ui.adding = false;
  form.reset();
  run("feature.add", args, { label: "Feature added" });
}

// Attach the listeners once. The guard keeps the module importable without a page (tests).
export function bind(el) {
  if (!el || bound.has(el)) return;
  bound.add(el);
  el.addEventListener("click", onClick);
  el.addEventListener("change", onChange);
  el.addEventListener("submit", onSubmit);
}
