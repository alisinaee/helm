// Running now: the running jobs with live timers, then the last 6 finished jobs with duration and tokens.
// Timers are not part of the HTML: each timer element carries its start time, and tickTimers() writes the text once
// a second and right after every redraw (a MutationObserver on #main). So a tick never re-renders the section.

import { chipHtml, esc, sectionHtml } from "../dom.js";
import { fmtCount, fmtDuration, fmtTokens, MISSING } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { modelChip, timerHtml } from "./tasks.js";

let watching = false;

// Write the elapsed time into every timer under root. Writes only when the text changed, so the observer settles.
export function tickTimers(root) {
  const now = Date.now();
  const timers = root.querySelectorAll("[data-started-ms]");
  for (const el of timers) {
    const started = Number(el.getAttribute("data-started-ms"));
    const text = fmtDuration((now - started) / 1000);
    if (el.textContent !== text) el.textContent = text;
  }
}

// Start the once-a-second ticker and the observer. Safe to call on every render; it does nothing without a page.
export function watchTimers() {
  if (watching || typeof document === "undefined") return;
  watching = true;
  window.setInterval(function () {
    tickTimers(document);
  }, 1000);
  const main = document.getElementById("main");
  if (main && typeof MutationObserver === "function") {
    const observer = new MutationObserver(function () {
      tickTimers(main);
    });
    observer.observe(main, { childList: true, subtree: true });
  }
}

// The copy-reference button of a job row (ref rb:<project>/job/<id>). pid is the project slug of the snapshot.
function jobCopyHtml(job, pid) {
  return copyButton("job", job.id, job.title || job.id, { project: pid, sum: refSummary("job", job) });
}

function runItemHtml(job, pid) {
  return '<div class="row-grid run-item"><span class="rg-chips"><span class="rdot" aria-hidden="true"></span>' +
    '<span class="run-id">' + esc(job.id) + "</span>" +
    (job.task ? chipHtml(job.task, "neutral") : "") + modelChip(job.model) +
    (job.status === "claimed" ? chipHtml("claimed", "neutral") : "") + "</span>" +
    '<p class="run-title rg-t" title="' + esc(job.title) + '">' + esc(job.title) + "</p>" +
    '<span class="rg-num">' + timerHtml(job) + "</span>" + jobCopyHtml(job, pid) + "</div>";
}

// The model chip already says "haiku" or "opus", so a title that starts with that word and a colon drops it.
// The title attribute keeps the full text.
const KNOWN_MODELS = ["haiku", "sonnet", "opus", "cursor", "agy"];

export function shortTitle(job) {
  const title = job.title || "";
  if (!job.model || KNOWN_MODELS.indexOf(job.model) < 0) return title;
  const prefix = job.model + ": ";
  return title.toLowerCase().indexOf(prefix) === 0 ? title.slice(prefix.length) : title;
}

function finishedRowHtml(job, pid) {
  const ok = job.status === "done";
  const tokens = typeof job.tokensK === "number" ? "~" + fmtTokens(job.tokensK) : MISSING;
  return '<li class="fin-row row-grid"><div class="fin-main">' +
    '<p class="fin-meta"><span class="fin-state">' + (ok ? "✓ done" : "✗ failed") + "</span>" +
    modelChip(job.model) + "</p>" +
    '<p class="fin-title rg-t" title="' + esc(job.title) + '">' + esc(shortTitle(job)) + "</p></div>" +
    '<span class="rg-num">' + esc(fmtDuration(job.elapsedS)) + "</span>" +
    '<span class="rg-num">' + esc(tokens) + "</span>" + jobCopyHtml(job, pid) + "</li>";
}

export function runningSection(vm) {
  watchTimers();
  const snap = vm.project.snapshot;
  const pid = snap.id;
  const running = snap.running;
  const finished = snap.jobs.filter(function (job) {
    return job.status !== "running";
  }).sort(function (a, b) {
    return (b.endedMs || 0) - (a.endedMs || 0);
  }).slice(0, 6);
  let body = running.length
    ? '<div class="run-list">' + running.map(function (job) {
      return runItemHtml(job, pid);
    }).join("") + "</div>"
    : '<p class="placeholder">Nothing is running.</p>';
  body += '<p class="sub-head">Recently finished <span class="sub-note">duration and tokens</span></p>';
  body += finished.length
    ? '<ul class="fin-list">' + finished.map(function (job) {
      return finishedRowHtml(job, pid);
    }).join("") + "</ul>"
    : '<p class="placeholder">No finished jobs yet.</p>';
  return sectionHtml({
    id: "running",
    title: "Running now",
    summary: fmtCount(running.length) + " running",
    open: vm.open.running,
    body: body,
  });
}
