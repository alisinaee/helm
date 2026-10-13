// Phases: the main column of the project view. One row per phase (name, state word, meter, done/total, tokens
// left, percent) that expands to its task rows. Outside the chosen minimal view a running phase opens by itself.
// Deferred phases are dimmed and carry a chip. The phase rows are buttons, so Enter and Space toggle them.

import { chipHtml, esc, meterHtml, sectionHtml } from "../dom.js";
import { fmtCount, fmtPercent, fmtTokens, MISSING } from "../format.js";
import { deferredRowHtml, jobChipHtml, STATE_GLYPH, STATE_WORD, taskRowHtml } from "./tasks.js";

const TONE = { done: "success", partial: "accent", todo: "accent", hold: "warning" };

// The phase the person is working in: the first partial phase, else the first unfinished phase with tasks.
export function activePhaseId(phases) {
  const partial = phases.find(function (p) {
    return p.state === "partial" && !p.onlyDeferred;
  });
  if (partial) return partial.id;
  const open = phases.find(function (p) {
    return p.state !== "done" && !p.onlyDeferred;
  });
  return open ? open.id : null;
}

// The effective open state of a phase: an explicit choice wins, expanded mode opens all, and the chosen minimal
// view keeps phase rows only. Otherwise a running phase opens by itself, and so does the active phase.
export function phaseIsOpen(vm, phase, activeId) {
  const saved = vm.prefsOpen["phase:" + phase.id];
  if (typeof saved === "boolean") return saved;
  if (vm.mode === "expanded") return true;
  if (vm.modeChosen) return false;
  return phase.runningCount > 0 || phase.id === activeId;
}

function deferOpen(vm, phase) {
  const saved = vm.prefsOpen["defer:" + phase.id];
  return typeof saved === "boolean" ? saved : vm.mode === "expanded";
}

function countText(phase) {
  if (phase.onlyDeferred) return fmtCount(phase.deferred) + " deferred";
  if (!phase.total) return "no tasks";
  return fmtCount(phase.done) + "/" + fmtCount(phase.total);
}

function leftText(phase) {
  if (phase.onlyDeferred || phase.remainingK == null) return MISSING;
  return "~" + fmtTokens(phase.remainingK);
}

function phaseRowHtml(vm, phase, open) {
  const glyphKey = phase.onlyDeferred ? "deferred" : phase.state;
  const glyph = STATE_GLYPH[glyphKey] || "○";
  const word = STATE_WORD[glyphKey] || phase.state;
  const pct = phase.onlyDeferred || phase.progress == null ? null : phase.progress * 100;
  const runChip = phase.runningCount
    ? chipHtml("▶ " + fmtCount(phase.runningCount), "success").replace("</span>",
      '<span class="ph-run-word"> running</span></span>') : "";
  const classes = "phase-row" + (open ? " is-open" : "") + (phase.state === "done" ? " is-done" : "") +
    (phase.onlyDeferred ? " is-deferred" : "") + (phase.runningCount ? " has-run" : "");
  return '<button type="button" class="' + classes + '" aria-expanded="' + open + '" aria-controls="phase-' +
    esc(phase.id) + '-body" data-action="toggle-item" data-item="phase:' + esc(phase.id) +
    '" data-focus="item-phase:' + esc(phase.id) + '">' +
    '<span class="ph-name"><span class="ph-caret" aria-hidden="true">' + (open ? "▾" : "▸") + "</span>" +
    '<span class="ph-glyph" aria-hidden="true">' + glyph + "</span>" +
    '<span class="ph-id">' + esc(phase.id) + "</span>" +
    '<span class="ph-title" title="' + esc(phase.name) + '">' + esc(phase.name) + "</span>" +
    '<span class="ph-word">' + esc(word) + "</span>" + runChip + "</span>" +
    '<span class="ph-meter">' + meterHtml(pct, TONE[phase.state] || "accent") + "</span>" +
    '<span class="ph-count num">' + esc(countText(phase)) + "</span>" +
    '<span class="ph-left num">' + esc(leftText(phase)) + "</span>" +
    '<span class="ph-pct num">' + esc(pct == null ? MISSING : fmtPercent(pct)) + "</span></button>";
}

function jobsByTaskOf(phase, tasks, jobById) {
  const liveIds = {};
  tasks.forEach(function (t) {
    if (t.state !== "deferred") liveIds[t.id] = true;
  });
  const byTask = {};
  const floats = [];
  phase.running.concat(phase.recent).forEach(function (id) {
    const job = jobById[id];
    if (!job) return;
    if (job.task && liveIds[job.task]) {
      (byTask[job.task] = byTask[job.task] || []).push(job);
    } else {
      floats.push(job);
    }
  });
  return { byTask: byTask, floats: floats };
}

function phaseBodyHtml(vm, phase, tasks, jobById) {
  const placed = jobsByTaskOf(phase, tasks, jobById);
  const live = tasks.filter(function (t) {
    return t.state !== "deferred";
  });
  const defs = tasks.filter(function (t) {
    return t.state === "deferred";
  });
  let html = "";
  if (placed.floats.length) {
    html += '<div class="job-chips phase-floats">' + placed.floats.map(jobChipHtml).join("") + "</div>";
  }
  if (live.length) {
    html += live.map(function (t) {
      return taskRowHtml(t, placed.byTask[t.id] || []);
    }).join("");
  } else if (!placed.floats.length) {
    html += '<p class="phase-empty">No tasks in this phase.</p>';
  }
  if (defs.length) {
    const open = deferOpen(vm, phase);
    const listId = "defer-" + phase.id + "-list";
    html += '<button type="button" class="defer-toggle" aria-expanded="' + open + '" aria-controls="' + listId +
      '" data-action="toggle-item" data-item="defer:' + esc(phase.id) + '" data-focus="item-defer:' +
      esc(phase.id) + '">' + (open ? "▾" : "▸") + " " + fmtCount(defs.length) + " deferred</button>" +
      '<div class="defer-list" id="' + listId + '"' + (open ? "" : " hidden") + ">" +
      defs.map(deferredRowHtml).join("") + "</div>";
  }
  return html;
}

function phaseHtml(vm, phase, activeId, tasks, jobById) {
  const open = phaseIsOpen(vm, phase, activeId);
  const bodyId = "phase-" + phase.id + "-body";
  const body = open ? phaseBodyHtml(vm, phase, tasks, jobById) : "";
  return '<div class="phase">' + phaseRowHtml(vm, phase, open) + '<div class="phase-body" id="' + bodyId +
    '"' + (open ? "" : " hidden") + ">" + body + "</div></div>";
}

export function phasesSection(vm) {
  const snap = vm.project.snapshot;
  const activeId = activePhaseId(snap.phases);
  const jobById = {};
  snap.jobs.forEach(function (job) {
    jobById[job.id] = job;
  });
  const rows = snap.phases.map(function (phase) {
    const tasks = snap.tasks.filter(function (t) {
      return t.phase === phase.id;
    });
    return phaseHtml(vm, phase, activeId, tasks, jobById);
  }).join("");
  const head = '<div class="phase-grid ph-head" aria-hidden="true"><span>Phase</span><span>Progress</span>' +
    "<span>Items</span><span>Tokens left</span><span>Done</span></div>";
  return sectionHtml({
    id: "phases",
    title: "Phases",
    summary: fmtCount(snap.done) + " of " + fmtCount(snap.total) + " items done",
    open: vm.open.phases,
    body: head + '<div class="phase-list">' + rows + "</div>",
  });
}
