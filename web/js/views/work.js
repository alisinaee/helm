// Work section (WP31): the Board, List and Tree views of one project's tasks. This module reads the route and the saved
// preferences, builds one context for the view, and handles the section's clicks, changes and bulk actions. Filters (f)
// and grouping (g) ride in the hash, so a link can carry them. The view, sort and phone column are kept per project in
// rb.ui.v2 under ui.filters["work.<id>"], so they survive a reload. Every write goes through cmd.js.

import { bannerHtml, emptyHtml, esc, skeletonHtml } from "../dom.js";
import { run, runBatch } from "../cmd.js";
import { buildHash, currentRoute } from "../router.js";
import { loadUi, updateUi } from "../state.js";
import { boardView, COLUMNS, filterBarHtml, finePointer, matchesFilters, parseFilters, setStatus, toggleToken,
  workTasks } from "./board.js";
import { clearSelection, groupBarHtml, GROUPS, listView, nextSort, parseSort, setAllSelected, setSelected } from
  "./list.js";
import { subtaskToggle, treeView } from "./tree.js";

const VIEWS = ["board", "list", "tree"];
const VIEW_LABEL = { board: "Board", list: "List", tree: "Tree" };
const PREF_PREFIX = "work.";
const COLUMN_KEYS = COLUMNS.map(function (c) {
  return c.key;
});

function savedParams(pid) {
  const raw = loadUi().filters[PREF_PREFIX + pid];
  return new URLSearchParams(typeof raw === "string" ? raw : "");
}

// The effective preferences: the route wins for view, f and g when it carries them; the saved values fill the rest.
function readPrefs(pid, route) {
  const saved = savedParams(pid);
  const filters = route.filters || {};
  const f = filters.f || saved.get("f") || "";
  const g = filters.g || saved.get("g") || "";
  const view = VIEWS.indexOf(route.view) >= 0 ? route.view : (VIEWS.indexOf(saved.get("v")) >= 0
    ? saved.get("v") : "board");
  const col = COLUMN_KEYS.indexOf(saved.get("c")) >= 0 ? saved.get("c") : "todo";
  return {
    view: view,
    f: f,
    g: GROUPS.indexOf(g) >= 0 ? g : "",
    s: parseSort(saved.get("s")),
    sRaw: saved.get("s") || "",
    c: col,
  };
}

function persist(pid, prefs) {
  const params = new URLSearchParams();
  params.set("v", prefs.view);
  if (prefs.f) params.set("f", prefs.f);
  if (prefs.g) params.set("g", prefs.g);
  params.set("s", prefs.sRaw || "n:asc");
  params.set("c", prefs.c);
  const text = params.toString();
  if (savedParams(pid).toString() === text) return;
  updateUi(function (ui) {
    ui.filters[PREF_PREFIX + pid] = text;
  });
}

function cleanFilters(f, g) {
  const out = {};
  if (f) out.f = f;
  if (g) out.g = g;
  return out;
}

function dispatchRender() {
  window.dispatchEvent(new Event("hashchange"));
}

// Keep the URL and the saved preferences in step, then show the result. Changing the hash re-renders by itself.
function goWork(pid, changes) {
  const route = currentRoute();
  const prefs = Object.assign(readPrefs(pid, route), changes);
  persist(pid, prefs);
  const hash = buildHash({ name: "project", id: pid, section: "work", view: prefs.view, item: route.item || null,
    filters: cleanFilters(prefs.f, prefs.g) });
  if (window.location.hash === hash) {
    dispatchRender();
  } else {
    window.location.hash = hash;
  }
}

function saveOnly(pid, changes) {
  const prefs = Object.assign(readPrefs(pid, currentRoute()), changes);
  persist(pid, prefs);
  dispatchRender();
}

function focusLater(selector) {
  window.setTimeout(function () {
    const el = document.querySelector(selector);
    if (el) el.focus({ preventScroll: true });
  }, 0);
}

function headHtml(ctx) {
  const total = ctx.all.length;
  const note = !total ? "No tasks yet" : (ctx.shown.length === total ? total + (total === 1 ? " task" : " tasks")
    : "Showing " + ctx.shown.length + " of " + total + " tasks");
  const buttons = VIEWS.map(function (v) {
    return '<button type="button" aria-pressed="' + (ctx.view === v ? "true" : "false") +
      '" data-wk="view" data-view="' + v + '" data-focus="wk-view-' + v + '">' + VIEW_LABEL[v] + "</button>";
  }).join("");
  return '<div class="page-head"><h2 class="page-title">Work</h2><p class="page-note">' + esc(note) + "</p></div>" +
    '<div class="wk-top"><div class="seg wk-views" role="group" aria-label="Work view">' + buttons + "</div></div>";
}

function bodyHtml(ctx) {
  if (!ctx.all.length) {
    return emptyHtml("No tasks in this project yet.", "<span>Tasks come from the project's task file.</span>");
  }
  if (!ctx.shown.length) {
    return filterBarHtml(ctx) + emptyHtml("No tasks match these filters.",
      '<button type="button" class="btn btn-small" data-wk="clear" data-focus="wk-clear">Clear filters</button>');
  }
  if (ctx.view === "list") return filterBarHtml(ctx) + groupBarHtml(ctx) + listView(ctx);
  if (ctx.view === "tree") return filterBarHtml(ctx) + treeView(ctx);
  return filterBarHtml(ctx) + boardView(ctx);
}

export function sectionView(vm) {
  const route = vm.route;
  if (route.name !== "project" || !vm.project) {
    return emptyHtml("Work belongs to one project.", '<a href="#/all/overview">Go to All projects</a>');
  }
  if (vm.project.notFound) {
    return emptyHtml("No project with that id.", '<a href="#/all/overview">Go to All projects</a>');
  }
  const snap = vm.project.snapshot;
  if (!snap) {
    if (vm.project.error) {
      return bannerHtml("danger", "Could not load this project. Retrying.", vm.project.error.message);
    }
    return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90"]) + "</div>";
  }
  const pid = route.id;
  const prefs = readPrefs(pid, route);
  persist(pid, prefs);
  const F = parseFilters(prefs.f);
  const all = workTasks(snap, vm.now);
  const ctx = {
    pid: pid,
    snap: snap,
    view: prefs.view,
    all: all,
    shown: all.filter(function (t) {
      return matchesFilters(t, F);
    }),
    F: F,
    filters: cleanFilters(prefs.f, prefs.g),
    group: prefs.g,
    sort: prefs.sRaw || "n:asc",
    col: prefs.c,
    open: vm.prefsOpen || {},
    fine: finePointer(),
  };
  return '<div class="wk" data-project="' + esc(pid) + '">' + headHtml(ctx) + bodyHtml(ctx) + "</div>";
}

// Bulk actions run one batch: the selected visible tasks, with the status or the run request from the bar.
function bulk(pid, root, el) {
  const op = el.getAttribute("data-op");
  const bar = el.closest(".wk-bulk");
  const ids = bar ? (bar.getAttribute("data-ids") || "").split(",").filter(Boolean) : [];
  if (op === "clear") {
    clearSelection(pid);
    dispatchRender();
    return;
  }
  if (!ids.length) return;
  let items;
  let done;
  if (op === "status") {
    const picked = root.querySelector("#wk-bulk-status");
    const to = picked ? picked.value : "";
    if (COLUMNS.every(function (c) {
      return c.state !== to;
    })) return;
    items = ids.map(function (id) {
      return { op: "task.status", args: { id: id, status: to }, key: "task:" + id, value: to };
    });
    done = "tasks updated";
  } else if (op === "start") {
    items = ids.map(function (id) {
      return { op: "task.start", args: { id: id } };
    });
    done = "tasks queued to run";
  } else {
    items = ids.map(function (id) {
      return { op: "task.stop", args: { id: id } };
    });
    done = "stop requests sent";
  }
  clearSelection(pid);
  runBatch(items, { project: pid, done: done });
}

function onClick(event) {
  const el = event.target && event.target.closest ? event.target.closest("[data-wk]") : null;
  if (!el) return;
  const root = el.closest(".wk");
  if (!root) return;
  const pid = root.getAttribute("data-project");
  const kind = el.getAttribute("data-wk");
  const route = currentRoute();
  const prefs = readPrefs(pid, route);
  if (kind === "view") {
    goWork(pid, { view: el.getAttribute("data-view") });
  } else if (kind === "filter") {
    goWork(pid, { f: toggleToken(prefs.f, el.getAttribute("data-token")) });
  } else if (kind === "clear") {
    goWork(pid, { f: "" });
  } else if (kind === "tab") {
    saveOnly(pid, { c: el.getAttribute("data-col") });
  } else if (kind === "sort") {
    const next = nextSort(prefs.sRaw, el.getAttribute("data-key"));
    saveOnly(pid, { sRaw: next });
  } else if (kind === "status") {
    setStatus(pid, el.getAttribute("data-task"), el.getAttribute("data-to"), el.getAttribute("data-from"));
  } else if (kind === "run-start") {
    const id = el.getAttribute("data-task");
    run("task.start", { id: id }, { project: pid, label: id + " queued to run" });
  } else if (kind === "run-stop") {
    const id = el.getAttribute("data-task");
    run("task.stop", { id: id }, { project: pid, label: id + " stop requested" });
  } else if (kind === "bulk") {
    bulk(pid, root, el);
  }
}

function onChange(event) {
  const el = event.target;
  const root = el && el.closest ? el.closest(".wk") : null;
  if (!root) return;
  const pid = root.getAttribute("data-project");
  const kind = el.getAttribute("data-wk");
  if (kind === "select") {
    const id = el.getAttribute("data-task");
    setSelected(pid, id, el.checked);
    el.blur();
    dispatchRender();
    focusLater('[data-focus="wk-sel-' + id + '"]');
  } else if (kind === "select-all") {
    const ids = (el.getAttribute("data-ids") || "").split(",").filter(Boolean);
    setAllSelected(pid, ids, el.checked);
    el.blur();
    dispatchRender();
    focusLater('[data-focus="wk-select-all"]');
  } else if (kind === "sub") {
    subtaskToggle(pid, el.getAttribute("data-addr"), el.checked);
  } else if (kind === "group") {
    el.blur();
    goWork(pid, { g: el.value });
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
}
