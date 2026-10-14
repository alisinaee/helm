// Work, Tree view (WP31): phase, then task, then subtask checkboxes. Each phase row folds its tasks (the open state is
// kept per project, and every phase starts open). A subtask checkbox sets the subtask through subtask.toggle, and the
// task title links to its item. Tasks are grouped under their phase in the project's phase order; a task whose phase
// is not in the snapshot goes under Other.

import { chipHtml, esc } from "../dom.js";
import { run } from "../cmd.js";
import { modelChip, phaseCopyHtml, sectionCopyHtml, subCopyHtml, taskCopyHtml } from "./tasks.js";
import { copyItem, STATE_LABEL, columnKey, taskHref } from "./board.js";

function subtaskHtml(ctx, task) {
  if (!task.subs.length) return "";
  const items = task.subs.map(function (s, i) {
    return '<li><label class="wk-sub"><input type="checkbox" data-wk="sub" data-addr="' + esc(s.addr) +
      '" data-focus="wk-sub-' + esc(s.addr) + '"' + (s.done ? " checked" : "") + "> <span>" + esc(s.t) +
      "</span></label>" + subCopyHtml(ctx.pid, task.id, i, { t: s.t, d: s.done }) + "</li>";
  }).join("");
  return '<ul class="wk-subs" aria-label="' + esc("Subtasks of " + task.id) + '">' + items + "</ul>";
}

function taskHtml(ctx, task) {
  const flags = [];
  if (task.model) flags.push(modelChip(task.model));
  if (task.needsUser) flags.push(chipHtml("needs you", "warning"));
  if (task.blocked) flags.push(chipHtml("blocked", "danger"));
  const copy = taskCopyHtml(ctx.pid, ctx.snap, copyItem(task));
  return '<li class="wk-tree-task" data-wk-task="' + esc(task.id) + '" data-state="' + esc(task.state) + '">' +
    '<div class="wk-tree-row"><span class="wk-id num">' + esc(task.id) + "</span>" +
    '<a class="wk-title" href="' + esc(taskHref(ctx, task.id)) + '" aria-label="Task ' + esc(task.id) + ": " +
    esc(task.title) + '" data-focus="wk-title-' + esc(task.id) +
    '">' + esc(task.title) + "</a>" +
    '<span class="wk-word">' + esc(STATE_LABEL[task.state] || task.state) + "</span>" + flags.join("") + copy +
    "</div>" + subtaskHtml(ctx, task) + "</li>";
}

// phase is the snapshot's phase row, or null for the Other group (a section, not a phase).
function phaseHtml(ctx, phaseId, name, tasks, phase) {
  const key = "wk-phase:" + phaseId;
  const saved = ctx.open[key];
  const open = typeof saved === "boolean" ? saved : true;
  const bodyId = "wk-ph-" + phaseId;
  const done = tasks.filter(function (t) {
    return columnKey(t.state) === "done";
  }).length;
  const copy = phase ? phaseCopyHtml(ctx.pid, phase)
    : sectionCopyHtml(ctx.pid, "tree.other", name, tasks.length);
  return '<section class="wk-phase"><h3 class="wk-phase-h"><button type="button" class="wk-phase-btn" ' +
    'aria-expanded="' + open + '" aria-controls="' + bodyId + '" data-action="toggle-item" data-item="' + esc(key) +
    '" data-focus="wk-phase-' + esc(phaseId) + '"><span class="wk-caret" aria-hidden="true">' + (open ? "▾" : "▸") +
    '</span><span class="wk-id num">' + esc(phaseId) + "</span> <span>" + esc(name) + "</span>" +
    '<span class="wk-count num">' + done + "/" + tasks.length + "</span></button>" + copy + "</h3>" +
    '<ul class="wk-tree-tasks" id="' + bodyId + '"' + (open ? "" : " hidden") + ">" +
    tasks.map(function (t) {
      return taskHtml(ctx, t);
    }).join("") + "</ul></section>";
}

export function treeView(ctx) {
  const phases = ctx.snap.phases;
  const known = new Set(phases.map(function (p) {
    return p.id;
  }));
  const sections = [];
  for (const phase of phases) {
    const tasks = ctx.shown.filter(function (t) {
      return t.phase === phase.id;
    });
    if (tasks.length) sections.push(phaseHtml(ctx, phase.id, phase.name, tasks, phase));
  }
  const other = ctx.shown.filter(function (t) {
    return !known.has(t.phase);
  });
  if (other.length) sections.push(phaseHtml(ctx, "other", "Other", other, null));
  return '<div class="wk-tree">' + sections.join("") + "</div>";
}

// A subtask checkbox: subtask.toggle with the value shown at once. The change is wired in work.js.
export function subtaskToggle(pid, addr, done) {
  run("subtask.toggle", { addr: addr, done: done }, {
    project: pid,
    key: "sub:" + addr,
    value: done,
    label: addr + (done ? " done" : " reopened"),
  });
}
