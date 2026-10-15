// Work, List view (WP31): a dense table of the project's tasks with a checkbox, id, title, phase, status, model, est,
// spent, cap and flags. Headers sort (the sort is kept per project), Group by phase, status or model adds a header row
// per group, and a bulk bar appears once tasks are selected: Set status, Start and Stop. The batch gets one toast
// and one Undo (cmd.js runBatch). On phone the table becomes two-line rows; the bulk bar and checkboxes hide (CSS).

import { chipHtml, esc } from "../dom.js";
import { fmtTokens, MISSING } from "../format.js";
import { modelChip, sectionCopyHtml, taskCopyHtml } from "./tasks.js";
import { COLUMNS, copyItem, STATE_LABEL, columnKey, taskHref } from "./board.js";

export const GROUPS = ["", "phase", "status", "model"];
const SORT_KEYS = ["n", "id", "title", "phase", "status", "model", "est", "spent", "cap"];
const HEADS = [
  ["id", "ID"],
  ["title", "Task"],
  ["phase", "Phase"],
  ["status", "Status"],
  ["model", "Model"],
  ["est", "Est"],
  ["spent", "Spent"],
  ["cap", "Cap"],
];
const selections = new Map();

// The sort as "key:asc" or "key:desc". Anything unknown falls back to the file order.
export function parseSort(text) {
  const parts = String(text || "").split(":");
  const key = SORT_KEYS.indexOf(parts[0]) >= 0 ? parts[0] : "n";
  return { key: key, dir: parts[1] === "desc" ? "desc" : "asc" };
}

// The sort text after a header is clicked: the same key flips the direction, a new key starts ascending.
export function nextSort(current, key) {
  const now = parseSort(current);
  if (now.key === key) return key + ":" + (now.dir === "asc" ? "desc" : "asc");
  return key + ":asc";
}

function sortValue(task, key) {
  if (key === "n") return task.order;
  if (key === "id") return task.id;
  if (key === "title") return task.title;
  if (key === "phase") return task.phase;
  if (key === "status") return COLUMNS.findIndex(function (c) {
    return c.key === columnKey(task.state);
  });
  if (key === "model") return task.model || "";
  if (key === "est") return task.tokensK;
  if (key === "spent") return task.spentK;
  return task.capK;
}

// Missing values sort last in either direction.
export function sortTasks(tasks, sortText) {
  const sort = parseSort(sortText);
  const sign = sort.dir === "desc" ? -1 : 1;
  return tasks.slice().sort(function (a, b) {
    const x = sortValue(a, sort.key);
    const y = sortValue(b, sort.key);
    const xMissing = x === null || x === undefined || x === "";
    const yMissing = y === null || y === undefined || y === "";
    if (xMissing || yMissing) return xMissing === yMissing ? a.order - b.order : (xMissing ? 1 : -1);
    if (typeof x === "number" && typeof y === "number") return (x - y) * sign || a.order - b.order;
    return String(x).localeCompare(String(y), undefined, { numeric: true }) * sign || a.order - b.order;
  });
}

export function selectionOf(pid) {
  if (!selections.has(pid)) selections.set(pid, new Set());
  return selections.get(pid);
}

export function setSelected(pid, id, on) {
  const set = selectionOf(pid);
  if (on) {
    set.add(id);
  } else {
    set.delete(id);
  }
}

export function setAllSelected(pid, ids, on) {
  const set = selectionOf(pid);
  for (const id of ids) {
    if (on) {
      set.add(id);
    } else {
      set.delete(id);
    }
  }
}

export function clearSelection(pid) {
  selectionOf(pid).clear();
}

function groupKey(task, group) {
  if (group === "phase") return task.phase;
  if (group === "status") return columnKey(task.state);
  return task.model || "";
}

function groupLabel(ctx, task, group) {
  if (group === "phase") return task.phaseName + " (" + task.phase + ")";
  if (group === "status") return STATE_LABEL[task.state] || task.state;
  return task.model || "Unassigned model";
}

// Tasks in group order: each group keeps the sort, groups follow the first task they reach in that sort.
function groupsOf(ctx, sorted) {
  if (!ctx.group) return [{ label: null, items: sorted }];
  const groups = [];
  const byKey = new Map();
  for (const task of sorted) {
    const key = groupKey(task, ctx.group);
    if (!byKey.has(key)) {
      const group = { label: groupLabel(ctx, task, ctx.group), key: key, items: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    byKey.get(key).items.push(task);
  }
  return groups;
}

export function groupBarHtml(ctx) {
  const options = [["", "None"], ["phase", "Phase"], ["status", "Status"], ["model", "Model"]].map(function (o) {
    return '<option value="' + o[0] + '"' + (ctx.group === o[0] ? " selected" : "") + ">" + esc(o[1]) +
      "</option>";
  }).join("");
  return '<div class="wk-groupbar"><label class="wk-field">Group by <select data-wk="group">' + options +
    "</select></label></div>";
}

function bulkHtml(pid, ids) {
  const options = COLUMNS.map(function (c) {
    return '<option value="' + c.state + '">' + esc(STATE_LABEL[c.state]) + "</option>";
  }).join("");
  return '<div class="wk-bulk" role="region" aria-label="Bulk actions" data-ids="' + esc(ids.join(",")) + '">' +
    '<p class="wk-bulk-count">' + ids.length + (ids.length === 1 ? " task" : " tasks") + " selected</p>" +
    '<label class="wk-field">Set status <select id="wk-bulk-status" data-focus="wk-bulk-status">' + options +
    '</select></label><button type="button" class="btn btn-small" data-wk="bulk" data-op="status" ' +
    'data-focus="wk-bulk-apply">Apply status</button><button type="button" class="btn btn-small" ' +
    'data-wk="bulk" data-op="start" aria-label="Start selected tasks" data-focus="wk-bulk-start">Start</button>' +
    '<button type="button" class="btn btn-small" data-wk="bulk" data-op="stop" aria-label="Stop selected tasks" ' +
    'data-focus="wk-bulk-stop">Stop</button>' +
    '<button type="button" class="btn btn-small" data-wk="bulk" data-op="clear" data-focus="wk-bulk-clear">' +
    "Clear selection</button></div>";
}

function headHtml(ctx, allChecked, shownIds) {
  const sort = parseSort(ctx.sort);
  const cells = HEADS.map(function (h) {
    const on = sort.key === h[0];
    const aria = on ? (sort.dir === "desc" ? "descending" : "ascending") : "none";
    const label = "Sort by " + h[1] + (on ? (sort.dir === "desc" ? " descending" : " ascending") : "");
    return '<th scope="col" class="wk-c-' + h[0] + '" aria-sort="' + aria + '"><button type="button" ' +
      'class="wk-sort" data-wk="sort" data-key="' + h[0] + '" aria-label="' + esc(label) +
      '" data-focus="wk-sort-' + h[0] + '">' + esc(h[1]) +
      (on ? (sort.dir === "desc" ? " ▾" : " ▴") : "") + "</button></th>";
  }).join("");
  const all = '<th scope="col" class="wk-c-sel"><input type="checkbox" data-wk="select-all" data-ids="' +
    esc(shownIds.join(",")) + '" data-focus="wk-select-all" aria-label="Select all visible tasks"' +
    (allChecked ? " checked" : "") +
    "></th>";
  return "<thead><tr>" + all + cells + '<th scope="col" class="wk-c-flags">Flags</th>' +
    '<th scope="col" class="wk-c-ref"><span class="sr-only">Copy reference</span></th></tr></thead>';
}

function rowHtml(ctx, task, checked) {
  const subsDone = task.subs.filter(function (s) {
    return s.done;
  }).length;
  const flags = [];
  if (task.needsUser) flags.push(chipHtml("needs you", "warning"));
  if (task.blocked) flags.push(chipHtml("blocked", "danger"));
  if (task.subs.length) flags.push('<span class="num wk-fn">' + subsDone + "/" + task.subs.length + " sub</span>");
  if (task.comments) flags.push('<span class="num wk-fn">' + task.comments + " cmt</span>");
  return '<tr class="' + (task.state === "done" ? "is-done" : "") + '" data-wk-task="' + esc(task.id) +
    '" data-state="' + esc(task.state) + '">' +
    '<td class="wk-c-sel"><input type="checkbox" data-wk="select" data-task="' + esc(task.id) +
    '" data-focus="wk-sel-' + esc(task.id) + '" aria-label="' + esc("Select " + task.id) + '"' +
    (checked ? " checked" : "") + "></td>" +
    '<td class="wk-c-id num">' + esc(task.id) + "</td>" +
    '<td class="wk-c-title"><a href="' + esc(taskHref(ctx, task.id)) + '" data-focus="wk-title-' + esc(task.id) +
    '" title="' + esc(task.title) + '">' + esc(task.title) + "</a></td>" +
    '<td class="wk-c-phase">' + esc(task.phase) + "</td>" +
    '<td class="wk-c-status">' + esc(STATE_LABEL[task.state] || task.state) + "</td>" +
    '<td class="wk-c-model">' + (task.model ? modelChip(task.model) : "") + "</td>" +
    '<td class="wk-c-est num">' + esc(fmtTokens(task.tokensK)) + "</td>" +
    '<td class="wk-c-spent num">' + esc(fmtTokens(task.spentK)) + "</td>" +
    '<td class="wk-c-cap num">' + esc(task.capK == null ? MISSING : fmtTokens(task.capK)) + "</td>" +
    '<td class="wk-c-flags">' + flags.join(" ") + "</td>" +
    '<td class="wk-c-ref">' + taskCopyHtml(ctx.pid, ctx.snap, copyItem(task)) + "</td></tr>";
}

export function listView(ctx) {
  const sorted = sortTasks(ctx.shown, ctx.sort);
  const shownIds = sorted.map(function (t) {
    return t.id;
  });
  const sel = selectionOf(ctx.pid);
  const picked = shownIds.filter(function (id) {
    return sel.has(id);
  });
  const allChecked = shownIds.length > 0 && picked.length === shownIds.length;
  const bulk = picked.length ? bulkHtml(ctx.pid, picked) : "";
  const bodies = groupsOf(ctx, sorted).map(function (group) {
    const copy = sectionCopyHtml(ctx.pid, "list." + ctx.group + "." + (group.key || "unassigned"),
      group.label, group.items.length);
    const head = group.label === null ? ""
      : '<tr class="wk-group-head"><th scope="colgroup" colspan="11">' + esc(group.label) + " · " +
        group.items.length + (group.items.length === 1 ? " task" : " tasks") + copy + "</th></tr>";
    const rows = group.items.map(function (t) {
      return rowHtml(ctx, t, sel.has(t.id));
    }).join("");
    return "<tbody>" + head + rows + "</tbody>";
  }).join("");
  return bulk + '<div class="wk-tablewrap"><table class="wk-table"><caption class="sr-only">Tasks</caption>' +
    headHtml(ctx, allChecked, shownIds) + bodies + "</table></div>";
}
