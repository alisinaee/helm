// Agents (WP34): the running jobs as a tree (a lead job with its workers indented under it), the last 10 finished jobs,
// and a Stop button per row (op task.stop). Elapsed time ticks in the browser from the job's start time. The swimlane
// timeline is LATER. A worker is a job whose parent is the lead job (the parent and role fields come from WP20).

import { run } from "../cmd.js";
import { chipHtml, emptyHtml, esc } from "../dom.js";
import { MISSING, fmtDuration, fmtTokens } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { itemHash, pageState, scopeSnapshots } from "./inbox.js";

const FINISHED_MAX = 10;
const STATUS_WORDS = { done: "Done", failed: "Failed" };
const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const ENGINES = { haiku: "Haiku 5.5", sonnet: "Sonnet 5.5", opus: "Opus 5.5", head: "head · Opus 5.5",
  agy: "agy · Gemini 3.8 Flash", opencode: "opencode", cursor: "cursor · auto" };
const LEVEL_SUFFIX = /-(low|medium|high|xhigh|max)$/;
let ticking = false;

// The engine of a job: a bare model word maps to its engine name. A job with a recorded engine model shows the engine
// and that model: "cursor · grok-4.7" (the effort suffix is shown as the effort), "opencode · laguna-s-2.1".
// Unknown strings are shown as they are; no model is a dash.
export function engineLabel(model, engineModel) {
  const text = String(model || "").trim().toLowerCase();
  const exact = String(engineModel || "").trim().toLowerCase();
  if (exact && text === "cursor") return "cursor · " + exact.replace(LEVEL_SUFFIX, "");
  if (exact && text === "opencode") return "opencode · " + exact;
  if (!text) return "—";
  return ENGINES[text] || String(model).trim();
}

// The thinking effort of a job: the recorded level when there is one; else the level in its engine model name
// (cursor grok-4.7-xhigh is xhigh); else the engine default ("default" for Haiku, Sonnet, Opus, head and agy) or
// "not set" (cursor auto, opencode and anything unknown). Never blank.
export function effortLabel(effort, model, engineModel) {
  const text = String(effort || "").trim().toLowerCase();
  if (EFFORTS.indexOf(text) !== -1) return text;
  const level = LEVEL_SUFFIX.exec(String(engineModel || "").trim().toLowerCase());
  if (level) return level[1];
  return /^(haiku|sonnet|opus|head|agy)\b/.test(String(model || "").trim().toLowerCase()) ? "default" : "not set";
}

// The worker tree of one snapshot's running jobs: the roots (jobs whose parent is not running) and the children map.
export function agentTree(snap) {
  const running = snap.running || [];
  const ids = new Set(running.map(function (j) {
    return j.id;
  }));
  const kids = new Map();
  for (const job of running) {
    if (job.parent && ids.has(job.parent)) {
      if (!kids.has(job.parent)) kids.set(job.parent, []);
      kids.get(job.parent).push(job);
    }
  }
  const roots = running.filter(function (j) {
    return !(j.parent && ids.has(j.parent));
  });
  // Newest first: the latest started job sits at the top, workers too.
  const byStartDesc = function (a, b) {
    return startMs(b) - startMs(a);
  };
  roots.sort(byStartDesc);
  return { roots: roots, kids: kids };
}

function startMs(job) {
  if (typeof job.startedMs === "number") return job.startedMs;
  const t = Date.parse(job.started || "");
  return isNaN(t) ? 0 : t;
}

// The last FINISHED_MAX jobs that have ended, newest first.
export function finishedJobs(snap) {
  return (snap.jobs || []).filter(function (j) {
    return j.status !== "running";
  }).sort(function (a, b) {
    return (typeof b.endedMs === "number" ? b.endedMs : Date.parse(b.ended || "") || 0) -
      (typeof a.endedMs === "number" ? a.endedMs : Date.parse(a.ended || "") || 0);
  }).slice(0, FINISHED_MAX);
}

// Elapsed seconds for a running job, from its start time (so the figure ticks without a new snapshot).
function elapsedText(job, now) {
  if (job.startedMs == null) return MISSING;
  return fmtDuration(Math.max(0, now - job.startedMs) / 1000);
}

// One running job and, nested under it, its workers. pid is the project the job belongs to.
export function agentRowHtml(job, pid, tree, blocked, now, depth) {
  const children = tree.kids.get(job.id) || [];
  const taskHtml = job.task
    ? '<a href="' + esc(itemHash(pid, job.task)) + '" aria-label="' + esc("Task " + job.task) + '">' +
      esc(job.task) + "</a>"
    : '<span class="mt-label">No task assigned</span>';
  const handed = children.length
    ? chipHtml("Delegated to " + children.map(function (c) {
      return c.role || engineLabel(c.model, c.engineModel);
    }).join(", "), "neutral")
    : "";
  const badge = job.task && blocked.indexOf(job.task) !== -1 ? chipHtml("blocked", "danger") : "";
  const label = job.title || job.id;
  const stop = '<button type="button" class="btn btn-small" data-action="agent-stop" data-project="' + esc(pid) +
    '" data-task="' + esc(job.task || "") + '" data-focus="stop-' + esc(pid) + "-" + esc(job.id) + '"' +
    (job.task ? "" : " disabled") + ' aria-label="Stop ' + esc(label) + '">Stop</button>';
  const tokens = job.tokensK == null ? "not yet" : fmtTokens(job.tokensK);
  const row = '<li class="ag-row" data-depth="' + depth + '"><div class="row-grid rg-agent">' +
    '<span class="rg-chips">' + chipHtml(engineLabel(job.model, job.engineModel), "neutral") +
    (job.role ? chipHtml(job.role, "neutral") : "") + badge + "</span>" +
    '<span class="rg-chips ag-effort">' + esc(effortLabel(job.effort, job.model, job.engineModel)) + "</span>" +
    '<span class="rg-main"><span class="rg-t ag-title" title="' + esc(label) + '">' + esc(label) + "</span>" +
    (handed ? " " + handed : "") + "</span>" +
    '<span class="rg-chips">' + taskHtml + "</span>" +
    '<span class="rg-num num" data-started-ms="' + esc(String(job.startedMs == null ? "" : job.startedMs)) + '">' +
    esc(elapsedText(job, now)) + "</span>" +
    '<span class="rg-num num">' + esc(tokens) + "</span>" + stop +
    copyButton("job", job.id, label, { project: pid, sum: refSummary("job", job) }) + "</div>";
  if (!children.length) return row + "</li>";
  return row + '<ul class="ag-kids" aria-label="Workers of ' + esc(label) + '">' + children.map(function (child) {
    return agentRowHtml(child, pid, tree, blocked, now, depth + 1);
  }).join("") + "</ul></li>";
}

// A finished job on the same tracks as the running rows: model and status, title, task, elapsed, tokens, an empty
// Stop cell, and the copy-reference button.
function finishedHtml(job, pid) {
  const word = STATUS_WORDS[job.status] || job.status;
  const kind = job.status === "failed" ? "danger" : "success";
  const label = job.title || job.id;
  const tokens = job.tokensK == null ? "unknown" : fmtTokens(job.tokensK);
  const task = job.task ? '<a href="' + esc(itemHash(pid, job.task)) + '">' + esc(job.task) + "</a>" : "";
  return '<li class="ag-row"><div class="row-grid rg-agent">' +
    '<span class="rg-chips">' + chipHtml(engineLabel(job.model, job.engineModel), "neutral") +
    chipHtml(word, kind) + "</span>" +
    '<span class="rg-chips ag-effort">' + esc(effortLabel(job.effort, job.model, job.engineModel)) + "</span>" +
    '<span class="rg-main"><span class="rg-t ag-title" title="' + esc(label) + '">' + esc(label) + "</span></span>" +
    '<span class="rg-chips">' + task + "</span>" +
    '<span class="rg-num num">' + esc(fmtDuration(job.elapsedS)) + "</span>" +
    '<span class="rg-num num">' + esc(tokens) + "</span><span></span>" +
    copyButton("job", job.id, label, { project: pid, sum: refSummary("job", job) }) + "</div></li>";
}

// One block per project in view: its live tree and its finished jobs.
function projectBlock(entry, now, showName) {
  const snap = entry.snap;
  const tree = agentTree(snap);
  const blocked = snap.blocked || [];
  const heading = showName ? '<h3 class="grp-h">' + esc(entry.name) + "</h3>" : "";
  const head = '<li class="row-grid rg-agent rg-head" aria-hidden="true">' +
    '<span>Model</span><span class="ag-effort">Effort</span>' +
    '<span>Job</span><span>Task</span><span class="rg-num">Elapsed</span><span class="rg-num">Tokens</span>' +
    "<span></span><span></span>" +
    "</li>";
  const live = tree.roots.length
    ? '<ul class="ag-list" aria-label="Running agents">' + head + tree.roots.map(function (job) {
      return agentRowHtml(job, entry.id, tree, blocked, now, 0);
    }).join("") + "</ul>"
    : emptyHtml("No agents running.");
  const done = finishedJobs(snap);
  const past = done.length
    ? '<ol class="ag-list" aria-label="Last finished jobs">' + done.map(function (job) {
      return finishedHtml(job, entry.id);
    }).join("") + "</ol>"
    : '<p class="ov-sum">No finished jobs yet.</p>';
  return '<section class="ov-card" aria-label="Agents">' + heading + live +
    '<h3 class="ov-h">Recently finished jobs</h3>' + past + "</section>";
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  const scopes = scopeSnapshots(vm);
  const now = Date.now();
  const showName = vm.route.name !== "project";
  const note = "Live. Workers sit under the job that started them. Stop asks the project to stop that task.";
  return '<div class="page-head"><h2 class="page-title">Agents</h2><p class="page-note">' + esc(note) + "</p></div>" +
    scopes.map(function (entry) {
      return projectBlock(entry, now, showName);
    }).join("");
}

// Stop per row: task.stop on the row's task. Undo (queue.remove) is offered by the toast.
export function pageAction(action, el) {
  if (action !== "agent-stop") return;
  const task = el.getAttribute("data-task");
  if (!task) return;
  const pid = el.getAttribute("data-project");
  run("task.stop", { id: task }, { project: pid, label: "Stop requested for " + task });
}

// Refresh the elapsed text every second without a re-render (one ticker per page).
export function watchElapsed() {
  if (ticking || typeof window === "undefined") return;
  ticking = true;
  window.setInterval(function () {
    const now = Date.now();
    for (const el of document.querySelectorAll("[data-started-ms]")) {
      const started = Number(el.getAttribute("data-started-ms"));
      if (Number.isNaN(started) || el.getAttribute("data-started-ms") === "") continue;
      const text = fmtDuration(Math.max(0, now - started) / 1000);
      if (el.textContent !== text) el.textContent = text;
    }
  }, 1000);
}

watchElapsed();
