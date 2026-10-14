// Task rows and job chips. A task row is 32 px high with fixed right-aligned columns: tokens, thinking, model,
// check and needs-you. Titles are cut with an ellipsis; a note is cut at 2 lines with the full text in title.
// Running jobs show a chip with a live timer (the timer text is filled in by running.js, not by the render).
// A title is edited in place: double-click it, or focus it and press F2. Enter saves (task.rename, with Undo),
// Escape or leaving the field cancels. The editor replaces the title text only, so the row grid does not move.

import { run } from "../cmd.js";
import { chipHtml, esc } from "../dom.js";
import { fmtDuration, fmtTokens, MISSING } from "../format.js";
import { showToast } from "./toast.js";

const MODEL_KINDS = ["haiku", "sonnet", "opus", "cursor", "agy"];
export const TITLE_MAX = 120;
// A renamed title shows at once; it lasts until the snapshot that follows the write, or this long at most.
const RENAME_SHOW_MS = 10000;
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

// The title a row shows: the one the page just wrote (until the next snapshot) or the snapshot's own title.
function shownTitle(task) {
  const entry = renamed.get(task.id);
  return entry && Date.now() < entry.until ? entry.title : task.title;
}

function rowHtml(task, cls, cells, jobs) {
  const jobHtml = jobs && jobs.length ? '<span class="job-chips">' + jobs.map(jobChipHtml).join("") + "</span>" : "";
  const title = shownTitle(task);
  return '<div class="task-row ' + cls + '">' + idHtml(task) +
    '<span class="t-main"><span class="t-title" title="' + esc(title) + '" tabindex="0" data-tt-id="' +
    esc(task.id) + '">' + esc(title) + "</span>" +
    noteHtml(task) + jobHtml + "</span>" + cells + "</div>";
}

// One active task (todo, partial, done or hold) with its jobs; jobs are the running and recent jobs of the task.
export function taskRowHtml(task, jobs) {
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
  return rowHtml(task, cls, cells, jobs);
}

// A deferred task: muted, with one deferred chip in place of the token and model cells.
export function deferredRowHtml(task) {
  const cells = '<span class="t-tokens"></span><span class="t-think"></span>' +
    '<span class="t-model">' + chipHtml("deferred", "defer") + "</span>" +
    '<span class="t-check"></span><span class="t-needs"></span>';
  return rowHtml(task, "is-deferred", cells, []);
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

function setShown(id, title) {
  renamed.set(id, { title: title, until: Date.now() + RENAME_SHOW_MS });
}

// Put the title text back in place of the editor, with the given text.
function endEdit(text) {
  const ed = editing;
  editing = null;
  ed.span.textContent = text;
  ed.span.title = text;
  ed.input.replaceWith(ed.span);
  ed.span.focus({ preventScroll: true });
}

function commitEdit() {
  const ed = editing;
  const check = checkTitle(ed.input.value);
  if (check.error) {
    showToast({ text: check.error, tone: "danger" });
    ed.input.focus();
    return;
  }
  const id = ed.id;
  const prior = ed.prior;
  const title = check.title;
  endEdit(title);
  if (title === prior) return;
  run("task.rename", { id: id, title: title }, {
    label: id + " renamed",
    apply: function () {
      setShown(id, title);
    },
    revert: function () {
      setShown(id, prior);
    },
  });
}

function onEditKey(event) {
  if (!editing) return;
  if (event.key === "Enter") {
    event.preventDefault();
    commitEdit();
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    endEdit(editing.prior);
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
  editing = { id: span.getAttribute("data-tt-id"), span: span, input: input, prior: span.textContent };
  input.addEventListener("keydown", onEditKey);
  input.addEventListener("blur", function () {
    if (editing && editing.input === input) endEdit(editing.prior);
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
  document.addEventListener("keydown", function (event) {
    if (event.key !== "F2" || editing) return;
    const span = titleSpanOf(document.activeElement);
    if (!span) return;
    event.preventDefault();
    startEdit(span);
  });
}
