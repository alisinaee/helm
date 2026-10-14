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
let ticking = false;

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
  return { roots: roots, kids: kids };
}

// The last FINISHED_MAX jobs that have ended, newest first.
export function finishedJobs(snap) {
  return (snap.jobs || []).filter(function (j) {
    return j.status !== "running";
  }).sort(function (a, b) {
    return (b.endedMs || 0) - (a.endedMs || 0);
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
      return c.role || c.model || "worker";
    }).join(", "), "neutral")
    : "";
  const badge = job.task && blocked.indexOf(job.task) !== -1 ? chipHtml("blocked", "danger") : "";
  const label = job.title || job.id;
  const stop = '<button type="button" class="btn btn-small" data-action="agent-stop" data-project="' + esc(pid) +
    '" data-task="' + esc(job.task || "") + '" data-focus="stop-' + esc(pid) + "-" + esc(job.id) + '"' +
    (job.task ? "" : " disabled") + ' aria-label="Stop ' + esc(label) + '">Stop</button>';
  const tokens = job.tokensK == null ? MISSING : fmtTokens(job.tokensK);
  const row = '<li class="ag-row" data-depth="' + depth + '"><div class="row-grid rg-agent">' +
    '<span class="rg-chips">' + chipHtml(job.model || "model", "neutral") +
    (job.role ? chipHtml(job.role, "neutral") : "") + badge + "</span>" +
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

function finishedHtml(job) {
  const word = STATUS_WORDS[job.status] || job.status;
  const kind = job.status === "failed" ? "danger" : "success";
  const tokens = job.tokensK == null ? MISSING : fmtTokens(job.tokensK);
  return '<li class="act-row row-grid rg-fin"><span class="act-time num">' +
    esc(fmtDuration(job.elapsedS)) + "</span>" +
    '<span class="act-main"><span class="act-sum">' + esc(job.title || job.id) + "</span> " +
    chipHtml(job.model || "model", "neutral") + " " + chipHtml(word, kind) + "</span>" +
    '<span class="act-tok num">' + esc(tokens) + "</span></li>";
}

// One block per project in view: its live tree and its finished jobs.
function projectBlock(entry, now, showName) {
  const snap = entry.snap;
  const tree = agentTree(snap);
  const blocked = snap.blocked || [];
  const heading = showName ? '<h3 class="grp-h">' + esc(entry.name) + "</h3>" : "";
  const head = '<li class="row-grid rg-agent rg-head" aria-hidden="true"><span>Model</span><span>Job</span>' +
    '<span>Task</span><span class="rg-num">Elapsed</span><span class="rg-num">Tokens</span><span></span><span></span>' +
    "</li>";
  const live = tree.roots.length
    ? '<ul class="ag-list" aria-label="Running agents">' + head + tree.roots.map(function (job) {
      return agentRowHtml(job, entry.id, tree, blocked, now, 0);
    }).join("") + "</ul>"
    : emptyHtml("No agents running.");
  const done = finishedJobs(snap);
  const past = done.length
    ? '<ol class="act-list" aria-label="Last finished jobs">' + done.map(finishedHtml).join("") + "</ol>"
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
