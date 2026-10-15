// Task rows and job chips. A task row is 32 px high with fixed right-aligned columns: tokens, thinking, model,
// check and needs-you. Titles are cut with an ellipsis; a note is cut at 2 lines with the full text in title.
// Running jobs show a chip with a live timer (the timer text is filled in by running.js, not by the render).
// A title is edited in place: double-click it, or focus it and press Enter, Space or F2. Enter saves (task.rename,
// with Undo), Escape cancels. Leaving the field saves a valid title and keeps focus where the user moved it. The editor
// replaces the title text only, so the row grid does not move.

import { run } from "../cmd.js";
import { chipHtml, esc } from "../dom.js";
import { fmtDuration, fmtTokens, MISSING } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { parseRoute } from "../router.js";
import { showToast } from "./toast.js";

const MODEL_KINDS = ["haiku", "sonnet", "opus", "cursor", "agy"];
export const TITLE_MAX = 120;
// A renamed title shows at once; it lasts until the snapshot that follows the write, or this long at most.
const RENAME_SHOW_MS = 10000;
// Keyed by project and task id, so the same id in another project never shows this title.
const renamed = new Map();
let editing = null;

export const STATE_GLYPH = { done: "●", partial: "◐", todo: "○", hold: "⏸", deferred: "◌" };
export const STATE_WORD = {
  done: "done", partial: "in progress", todo: "to do", hold: "on hold", deferred: "deferred",
};

export function modelKind(model) {
  return MODEL_KINDS.indexOf(model) >= 0 ? model : "neutral";
}

export function modelChip(model) {
  return chipHtml(model || "model?", modelKind(model));
}

// Copy-reference buttons (R7.12, ref.js). Each one is a sibling of the row's toggles and links, never nested in them.
// The task object is snapshot-shaped: feats, and subs as {t, d}.
export function taskCopyHtml(project, snap, task) {
  return copyButton("task", task.id, task.id + " " + task.title, {
    project: project,
    sum: refSummary("task", task, snap),
  });
}

export function phaseCopyHtml(project, phase) {
  return copyButton("phase", phase.id, phase.name, { project: project, sum: refSummary("phase", phase, null) });
}

export function sectionCopyHtml(project, id, label, count) {
  return copyButton("section", id, label, { project: project, sum: refSummary("section", count, null) });
}

// A subtask ref is the task id, ".s", and the 1-based index (the same index as the subtask address).
export function subCopyHtml(project, taskId, index, sub) {
  return copyButton("sub", taskId + ".s" + (index + 1), sub.t, { project: project, sum: refSummary("sub", sub, null) });
}

function tokensText(k) {
  if (typeof k !== "number" || !Number.isFinite(k)) return MISSING;
  return "~" + fmtTokens(k);
}

// A timer for a running job. With a start time it ticks in the browser; without one it shows the snapshot value.
export function timerHtml(job) {
  if (job.startedMs != null) {
    return '<span class="timer num" data-started-ms="' + esc(job.startedMs) + '">' + MISSING + "</span>";
  }
  return '<span class="timer num">' + esc(fmtDuration(job.elapsedS)) + "</span>";
}

export function jobChipHtml(job) {
  const running = job.status === "running";
  const ok = job.status === "done";
  const label = running ? "running" : (ok ? "done" : "failed");
  const glyph = running ? "●" : (ok ? "✓" : "✗");
  const cls = "job-chip " + (running ? "is-running" : (ok ? "is-done" : "is-failed"));
  const tail = running ? timerHtml(job) : '<span class="num">' + esc(fmtDuration(job.elapsedS)) + "</span>";
  return '<span class="' + cls + '" title="' + esc(job.title) + '"><span aria-hidden="true">' + glyph + "</span> " +
    esc(label) + ' <span class="job-id">' + esc(job.id) + "</span>" + modelChip(job.model) + tail + "</span>";
}

function noteHtml(task) {
  if (!task.note) return "";
  return '<span class="t-note" title="' + esc(task.note) + '">' + esc(task.note) + "</span>";
}

function idHtml(task) {
  const glyph = STATE_GLYPH[task.state] || "○";
  return '<span class="t-id"><span aria-hidden="true">' + glyph + "</span> " + esc(task.id) +
    ' <span class="sr-only">' + esc(STATE_WORD[task.state] || task.state) + "</span></span>";
}

function renameKey(project, id) {
  return project + "\n" + id;
}

// The project of the page on screen (the route), used for the rename key and the write.
function currentProject() {
  if (typeof window === "undefined") return "";
  const route = parseRoute(window.location.hash);
  return route.name === "project" ? route.id : "";
}

// Drop every renamed title whose time is up, so the map cannot grow without limit.
function sweepRenamed(now) {
  renamed.forEach(function (entry, key) {
    if (now >= entry.until) renamed.delete(key);
  });
}

// The title a row shows: the one the page just wrote (until the next snapshot) or the snapshot's own title.
// An entry ends when its time is up or when the snapshot already carries the same title.
function shownTitle(project, task) {
  const key = renameKey(project, task.id);
  const entry = renamed.get(key);
  if (!entry) return task.title;
  if (Date.now() >= entry.until || entry.title === task.title) {
    renamed.delete(key);
    return task.title;
  }
  return entry.title;
}

// copy is the optional copy-reference button (taskCopyHtml); it goes at the end of the title cell.
function rowHtml(task, cls, cells, jobs, copy) {
  const jobHtml = jobs && jobs.length ? '<span class="job-chips">' + jobs.map(jobChipHtml).join("") + "</span>" : "";
  const project = currentProject();
  const title = shownTitle(project, task);
  return '<div class="task-row ' + cls + '">' + idHtml(task) +
    '<span class="t-main"><span class="t-title" title="' + esc(title) + '" tabindex="0" role="button" ' +
    'aria-label="Edit title for ' + esc(task.id) + '" data-tt-id="' + esc(task.id) + '" data-tt-project="' +
    esc(project) + '">' + esc(title) + "</span>" +
    noteHtml(task) + jobHtml + (copy || "") + "</span>" + cells + "</div>";
}

// One active task (todo, partial, done or hold) with its jobs; jobs are the running and recent jobs of the task.
export function taskRowHtml(task, jobs, copy) {
  const running = (jobs || []).some(function (j) {
    return j.status === "running";
  });
  const done = task.state === "done";
  const cls = (done ? "is-done" : "") + (running ? " is-run" : "");
  const cells = '<span class="t-tokens num">' + esc(tokensText(task.tokensK)) + "</span>" +
    '<span class="t-think">' + esc(task.thinking || "") + "</span>" +
    '<span class="t-model">' + (task.model ? modelChip(task.model) : "") + "</span>" +
    '<span class="t-check">' + (task.check && task.check !== "none"
      ? chipHtml("✓ " + task.check + " " + tokensText(task.checkK), modelKind(task.check))
      : "") + "</span>" +
    '<span class="t-needs">' + (task.needsUser && !done
      ? '<span class="chip chip-warning" title="this task waits on you">needs you</span>'
      : "") + "</span>";
  return rowHtml(task, cls, cells, jobs, copy);
}

// A deferred task: muted, with one deferred chip in place of the token and model cells.
export function deferredRowHtml(task, copy) {
  const cells = '<span class="t-tokens"></span><span class="t-think"></span>' +
    '<span class="t-model">' + chipHtml("deferred", "defer") + "</span>" +
    '<span class="t-check"></span><span class="t-needs"></span>';
  return rowHtml(task, "is-deferred", cells, [], copy);
}

export function taskListHtml(tasks) {
  return tasks.map(function (t) {
    return taskRowHtml(t, []);
  }).join("");
}

// Check a title the way the server does, before any write. Returns {title} (trimmed) or {error}.
export function checkTitle(text) {
  const title = String(text == null ? "" : text).trim();
  if (!title) return { error: "The title is empty. Type a title, or press Escape to keep the old one." };
  const length = Array.from(title).length;
  if (length > TITLE_MAX) {
    return { error: "The title is " + length + " characters. The limit is " + TITLE_MAX + "." };
  }
  if (/[\u0000-\u001f\u007f]/.test(title)) return { error: "Tabs and line breaks are not allowed in a title." };
  return { title: title };
}

function setShown(project, id, title) {
  const now = Date.now();
  sweepRenamed(now);
  renamed.set(renameKey(project, id), { title: title, until: now + RENAME_SHOW_MS });
}

// Put the title text back in place of the editor. Focus returns to the title only after a key (Enter, Escape), so a
// blur caused by a click on another control keeps that focus.
function endEdit(text, refocus) {
  const ed = editing;
  editing = null;
  ed.span.textContent = text;
  ed.span.title = text;
  ed.input.replaceWith(ed.span);
  if (refocus) ed.span.focus({ preventScroll: true });
}

// Save a valid, changed title; otherwise restore the old one. fromKey is true for Enter and false for a blur.
function commitEdit(fromKey) {
  const ed = editing;
  const check = checkTitle(ed.input.value);
  if (check.error) {
    showToast({ text: check.error, tone: "danger" });
    if (fromKey) {
      ed.input.focus();
    } else {
      endEdit(ed.prior, false);
    }
    return;
  }
  const id = ed.id;
  const project = ed.project;
  const prior = ed.prior;
  const title = check.title;
  endEdit(title, fromKey);
  if (title === prior) return;
  run("task.rename", { id: id, title: title }, {
    label: id + " renamed",
    project: project || undefined,
    apply: function () {
      setShown(project, id, title);
    },
    revert: function () {
      setShown(project, id, prior);
    },
  });
}

function onEditKey(event) {
  if (!editing) return;
  if (event.key === "Enter") {
    event.preventDefault();
    event.stopPropagation();
    commitEdit(true);
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    endEdit(editing.prior, true);
  }
}

function startEdit(span) {
  if (editing && !editing.input.isConnected) editing = null;
  if (editing || !span || !span.isConnected) return;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "iss-input";
  input.value = span.textContent;
  input.setAttribute("aria-label", "Title of " + span.getAttribute("data-tt-id"));
  editing = {
    id: span.getAttribute("data-tt-id"),
    project: span.getAttribute("data-tt-project") || "",
    span: span,
    input: input,
    prior: span.textContent,
  };
  input.addEventListener("keydown", onEditKey);
  input.addEventListener("blur", function () {
    if (editing && editing.input === input) commitEdit(false);
  });
  span.replaceWith(input);
  input.focus();
  input.select();
}

function titleSpanOf(target) {
  return target && target.closest ? target.closest(".t-title[data-tt-id]") : null;
}

if (typeof document !== "undefined") {
  document.addEventListener("dblclick", function (event) {
    const span = titleSpanOf(event.target);
    if (!span) return;
    event.preventDefault();
    startEdit(span);
  });
  // The title is a button: Enter, Space and F2 start the edit when the title itself has focus. The target check keeps
  // the Enter that saves an edit from opening the editor again.
  document.addEventListener("keydown", function (event) {
    if (editing) return;
    const span = titleSpanOf(event.target);
    if (!span) return;
    if (event.key !== "F2" && event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    startEdit(span);
  });
}
