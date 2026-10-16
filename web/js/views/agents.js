// Agents (WP34): the running jobs as a tree (a lead job with its workers indented under it), and the finished jobs, the
// whole history newest first (R7.60). The first AGENT_PAGE finished rows show at once; Load more shows the next ones,
// from the snapshot or, past it, from the paged read GET .../jobs?offset&limit. Each finished row has a checkbox, and
// Remove selected (op job.remove, person only, Undo in the toast) is the only way a finished job leaves the history.
// Stop per running row (op task.stop). Elapsed time ticks in the browser from the job's start time. The swimlane
// timeline is LATER. A worker is a job whose parent is the lead job (the parent and role fields come from WP20).
// The history controls carry data-agent (not data-action) and are wired once, below, by document listeners.

import { getJson } from "../api.js";
import { run } from "../cmd.js";
import { chipHtml, emptyHtml, esc } from "../dom.js";
import { MISSING, fmtDuration, fmtTokens } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { itemHash, pageState, scopeSnapshots } from "./inbox.js";

const AGENT_PAGE = 10;
const STATUS_WORDS = { done: "Done", failed: "Failed" };
const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const ENGINES = { haiku: "Haiku 5.5", sonnet: "Sonnet 5.5", opus: "Opus 5.5", head: "head · Opus 5.5",
  agy: "agy · Gemini 3.8 Flash", opencode: "opencode", cursor: "cursor · auto" };
const LEVEL_SUFFIX = /-(low|medium|high|xhigh|max)$/;
let ticking = false;

// Finished-history state per project: the visible count, the rows read from the paged route, the server total, the
// number of rows known at the last render, and the loading and error state of a page. Selected finished jobs are kept
// as "project\njob id" keys, so a selection survives a re-render.
const history = new Map();
const picked = new Set();

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

function endMs(job) {
  return typeof job.endedMs === "number" ? job.endedMs : Date.parse(job.ended || "") || 0;
}

function byEndDesc(a, b) {
  return endMs(b) - endMs(a);
}

// The finished jobs of a snapshot, newest first. The snapshot holds the whole job file, so none is cut here.
export function finishedJobs(snap) {
  return (snap.jobs || []).filter(function (j) {
    return j.status !== "running";
  }).sort(byEndDesc);
}

// One finished job from the paged route (the job file's shape), in the snapshot's normalised fields.
function shapeRow(j) {
  const started = Date.parse(j.started || "");
  const ended = Date.parse(j.ended || "");
  return {
    id: String(j.id || ""),
    title: j.title || "",
    model: j.model || null,
    status: j.status || "",
    task: j.task || null,
    elapsedS: typeof j.elapsed_s === "number" ? j.elapsed_s : null,
    tokensK: typeof j.tokensK === "number" ? j.tokensK : null,
    startedMs: isNaN(started) ? null : started,
    endedMs: isNaN(ended) ? null : ended,
    parent: j.parent || null,
    role: j.role || null,
    effort: j.effort || null,
    engineModel: j.engine_model || null,
  };
}

function historyOf(pid) {
  let hist = history.get(pid);
  if (!hist) {
    hist = { visible: AGENT_PAGE, rows: [], total: null, known: 0, loading: false, error: "" };
    history.set(pid, hist);
  }
  return hist;
}

// Every finished job of a project: the snapshot's, plus the rows read from the paged route, deduped by id, newest
// first.
function historyRows(pid, snap) {
  const seen = new Set();
  const out = [];
  for (const job of finishedJobs(snap).concat(historyOf(pid).rows)) {
    if (seen.has(job.id)) continue;
    seen.add(job.id);
    out.push(job);
  }
  return out.sort(byEndDesc);
}

// Elapsed seconds for a running job, from its start time (so the figure ticks without a new snapshot).
function elapsedText(job, now) {
  if (job.startedMs == null) return MISSING;
  return fmtDuration(Math.max(0, now - job.startedMs) / 1000);
}

// The eight cells every Agents row uses, in order: lead (live dot or select checkbox), model, title, task, effort,
// elapsed, tokens, action. The header, a running row and a finished row all go through here so the tracks cannot drift.
function agentCells(lead, model, title, task, effort, elapsed, tokens, action) {
  return '<span class="ag-lead">' + lead + "</span>" + '<span class="rg-chips ag-model">' + model + "</span>" +
    '<span class="rg-main">' + title + "</span>" + '<span class="rg-chips ag-task">' + task + "</span>" +
    effort + elapsed + tokens + '<span class="ag-act">' + action + "</span>";
}

const STOP_ICON = '<svg class="ico" aria-hidden="true" focusable="false" viewBox="0 0 16 16"><rect x="4" y="4" ' +
  'width="8" height="8" rx="1.5" fill="currentColor"/></svg>';
const SHORT_EFFORT = { medium: "med", default: "–", "not set": "–" };

function shortEffort(effort, model, engineModel) {
  const word = effortLabel(effort, model, engineModel);
  return SHORT_EFFORT[word] || word;
}

// One running job and, nested under it, its workers. pid is the project the job belongs to.
export function agentRowHtml(job, pid, tree, blocked, now, depth) {
  const children = tree.kids.get(job.id) || [];
  const taskHtml = job.task
    ? '<a href="' + esc(itemHash(pid, job.task)) + '" title="' + esc(job.task) +
      '" aria-label="' + esc("Task " + job.task) + '">' + esc(job.task) + "</a>"
    : '<span class="mt-label" title="No task assigned">No task assigned</span>';
  const handed = children.length
    ? chipHtml("Delegated to " + children.map(function (c) {
      return c.role || engineLabel(c.model, c.engineModel);
    }).join(", "), "neutral")
    : "";
  const badge = job.task && blocked.indexOf(job.task) !== -1 ? chipHtml("blocked", "danger") : "";
  const label = job.title || job.id;
  const stop = '<button type="button" class="ag-icon" data-action="agent-stop" data-project="' + esc(pid) +
    '" data-task="' + esc(job.task || "") + '" data-focus="stop-' + esc(pid) + "-" + esc(job.id) + '"' +
    (job.task ? "" : " disabled") + ' aria-label="Stop ' + esc(job.task || label) + '" title="Stop">' +
    STOP_ICON + "</button>";
  const tokens = job.tokensK == null ? MISSING : fmtTokens(job.tokensK);
  const claimed = job.status === "claimed" ? chipHtml("claimed", "neutral") : "";
  const model = chipHtml(engineLabel(job.model, job.engineModel), "neutral") +
    (job.role ? chipHtml(job.role, "neutral") : "") + claimed + badge;
  const effort = '<span class="rg-chips ag-effort">' +
    esc(shortEffort(job.effort, job.model, job.engineModel)) + "</span>";
  const title = '<span class="rg-t ag-title" title="' + esc(label) + '">' + esc(label) + "</span>" +
    (handed || "");
  const elapsed = '<span class="rg-num num" data-started-ms="' +
    esc(String(job.startedMs == null ? "" : job.startedMs)) + '">' + esc(elapsedText(job, now)) + "</span>";
  const tokenCell = '<span class="rg-num num">' + esc(tokens) + "</span>";
  const row = '<li class="ag-row" data-depth="' + depth + '"><div class="row-grid rg-agent">' +
    agentCells('<span class="ag-dot" role="img" aria-label="Running" title="Running"></span>', model, title, taskHtml,
      effort, elapsed, tokenCell,
      stop + copyButton("job", job.id, label, { project: pid, sum: refSummary("job", job) })) + "</div>";
  if (!children.length) return row + "</li>";
  return row + '<ul class="ag-kids" aria-label="Workers of ' + esc(label) + '">' + children.map(function (child) {
    return agentRowHtml(child, pid, tree, blocked, now, depth + 1);
  }).join("") + "</ul></li>";
}

// A finished job on the same tracks as the running rows: model and status, title, task, elapsed, tokens, the row's
// select checkbox (in the Stop cell, which a finished row has no use for), and the copy-reference button.
function finishedHtml(job, pid) {
  const word = STATUS_WORDS[job.status] || job.status;
  const kind = job.status === "failed" ? "danger" : "success";
  const label = job.title || job.id;
  const tokens = job.tokensK == null ? MISSING : fmtTokens(job.tokensK);
  const task = job.task ? '<a href="' + esc(itemHash(pid, job.task)) + '" title="' + esc(job.task) + '">' +
    esc(job.task) + "</a>" : "";
  const check = '<input type="checkbox" data-agent="select" data-project="' + esc(pid) + '" data-id="' +
    esc(job.id) + '" data-focus="sel-' + esc(pid) + "-" + esc(job.id) + '" aria-label="' + esc("Select " + label) +
    '"' + (picked.has(pid + "\n" + job.id) ? " checked" : "") + ">";
  const model = chipHtml(engineLabel(job.model, job.engineModel), "neutral");
  const effort = '<span class="rg-chips ag-effort">' +
    esc(shortEffort(job.effort, job.model, job.engineModel)) + "</span>";
  const title = '<span class="rg-t ag-title" title="' + esc(label) + '">' + esc(label) + "</span>" +
    chipHtml(word, kind);
  const elapsed = '<span class="rg-num num">' + esc(fmtDuration(job.elapsedS)) + "</span>";
  const tokenCell = '<span class="rg-num num">' + esc(tokens) + "</span>";
  return '<li class="ag-row"><div class="row-grid rg-agent">' +
    agentCells(check, model, title, task, effort, elapsed, tokenCell,
      copyButton("job", job.id, label, { project: pid, sum: refSummary("job", job) })) + "</div></li>";
}

// The count line and the controls under the finished list: Remove selected (its count of picked rows of this project)
// and Load more while the history has rows beyond those shown. An error of the last page is shown as an alert.
function historyControls(pid, all, hist) {
  const selected = Array.from(picked).filter(function (key) {
    return key.indexOf(pid + "\n") === 0;
  }).length;
  const total = hist.total == null ? all.length : Math.max(hist.total, all.length);
  const more = hist.total == null || all.length < hist.total;
  const attrs = ' data-project="' + esc(pid) + '"';
  return '<div class="ag-foot"><p class="ov-sum" aria-live="polite">Showing ' +
    esc(String(Math.min(hist.visible, all.length))) +
    " of " + esc(String(total)) + " · " + esc(String(selected)) + " selected</p>" +
    (hist.error ? '<p class="ov-sum" role="alert">' + esc(hist.error) + "</p>" : "") +
    '<span class="ag-foot-btns">' +
    '<button type="button" class="btn btn-small" data-agent="remove"' + attrs + (selected ? "" : " disabled") + ">" +
    "Remove selected</button> " +
    (more ? '<button type="button" class="btn btn-small" data-agent="more"' + attrs +
      (hist.loading ? " disabled" : "") + ">Load more</button>" : "") + "</span></div>";
}

// One block per project in view: its live tree and its finished jobs.
function projectBlock(entry, now, showName) {
  const snap = entry.snap;
  const tree = agentTree(snap);
  const blocked = snap.blocked || [];
  const heading = showName ? '<h3 class="grp-h">' + esc(entry.name) + "</h3>" : "";
  const head = '<li class="ag-row" aria-hidden="true"><div class="row-grid rg-agent rg-head">' +
    agentCells("", "Model", "Title", "Task", '<span class="ag-effort">Effort</span>',
      '<span class="rg-num">Elapsed</span>', '<span class="rg-num">Tokens</span>', "") + "</div></li>";
  const live = tree.roots.length
    ? '<ul class="ag-list" aria-label="Running agents">' + head + tree.roots.map(function (job) {
      return agentRowHtml(job, entry.id, tree, blocked, now, 0);
    }).join("") + "</ul>"
    : emptyHtml("No agents running.");
  const hist = historyOf(entry.id);
  const all = historyRows(entry.id, snap);
  hist.known = all.length;
  const past = all.length
    ? '<ol class="ag-list" aria-label="Last finished jobs">' + head +
      all.slice(0, hist.visible).map(function (job) {
        return finishedHtml(job, entry.id);
      }).join("") + "</ol>" + historyControls(entry.id, all, hist)
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
  const note = "Live. Workers sit under the job that started them. The square stops that task.";
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

function rerender() {
  document.dispatchEvent(new Event("rb:render"));
}

// A row's checkbox: the selection follows it.
function pickRow(el) {
  const key = el.getAttribute("data-project") + "\n" + el.getAttribute("data-id");
  if (el.checked) picked.add(key);
  else picked.delete(key);
  rerender();
}

// Load more: reveal the rows already known, else read the next page after them from the paged route. One page is
// requested at a time; a failed page shows its alert and the button stays.
function loadMore(pid) {
  const hist = historyOf(pid);
  if (hist.loading) return;
  if (hist.known > hist.visible) {
    hist.visible += AGENT_PAGE;
    rerender();
    return;
  }
  hist.loading = true;
  hist.error = "";
  const url = "/api/v1/projects/" + encodeURIComponent(pid) + "/jobs?offset=" + hist.known + "&limit=" + AGENT_PAGE;
  getJson(url).then(function (res) {
    const data = res && res.data;
    if (!res || res.status !== 200 || !data || !Array.isArray(data.rows)) throw new Error("page");
    const have = new Set(hist.rows.map(function (r) {
      return r.id;
    }));
    for (const raw of data.rows) {
      const row = shapeRow(raw);
      if (row.id && !have.has(row.id)) {
        have.add(row.id);
        hist.rows.push(row);
      }
    }
    hist.total = typeof data.total === "number" ? data.total : hist.known + data.rows.length;
    if (!data.rows.length) hist.total = hist.known;
    hist.visible = hist.known + data.rows.length;
  }).catch(function () {
    hist.error = "Could not load more jobs. Try Load more again.";
  }).finally(function () {
    hist.loading = false;
    rerender();
  });
}

// Remove selected: job.remove on the picked rows of one project (person only; the toast offers Undo). The rows leave
// this page's cache at once, and the snapshot that follows the write drops them from the snapshot too.
function removeSelected(pid) {
  const prefix = pid + "\n";
  const ids = [];
  for (const key of picked) {
    if (key.indexOf(prefix) === 0) ids.push(key.slice(prefix.length));
  }
  if (!ids.length) return;
  const hist = historyOf(pid);
  run("job.remove", { ids: ids }, { project: pid, label: "Removed " + ids.length + " job(s)" }).then(function (data) {
    if (!data) return;
    for (const id of ids) picked.delete(prefix + id);
    hist.rows = hist.rows.filter(function (row) {
      return ids.indexOf(row.id) === -1;
    });
    rerender();
  });
}

// The history controls are in the page's markup with data-agent, so they are wired once here (the page's data-action
// list in app.js is not used for them). A checkbox fires change; the two buttons fire click.
if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("change", function (event) {
    const el = event.target;
    if (el && el.getAttribute && el.getAttribute("data-agent") === "select") pickRow(el);
  });
  document.addEventListener("click", function (event) {
    const el = event.target && event.target.closest ? event.target.closest("[data-agent]") : null;
    if (!el) return;
    const action = el.getAttribute("data-agent");
    const pid = el.getAttribute("data-project");
    if (action === "more") loadMore(pid);
    else if (action === "remove") removeSelected(pid);
  });
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
