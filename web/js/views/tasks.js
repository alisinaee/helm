// Task rows and job chips. A task row is 32 px high with fixed right-aligned columns: tokens, thinking, model,
// check and needs-you. Titles are cut with an ellipsis; a note is cut at 2 lines with the full text in title.
// Running jobs show a chip with a live timer (the timer text is filled in by running.js, not by the render).

import { chipHtml, esc } from "../dom.js";
import { fmtDuration, fmtTokens, MISSING } from "../format.js";

const MODEL_KINDS = ["haiku", "sonnet", "opus", "cursor", "agy"];

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

function rowHtml(task, cls, cells, jobs) {
  const jobHtml = jobs && jobs.length ? '<span class="job-chips">' + jobs.map(jobChipHtml).join("") + "</span>" : "";
  return '<div class="task-row ' + cls + '">' + idHtml(task) +
    '<span class="t-main"><span class="t-title" title="' + esc(task.title) + '">' + esc(task.title) + "</span>" +
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
