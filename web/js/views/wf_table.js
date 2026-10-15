// The Workflow Table (R7.114, B-0 and B-4): one row per task that had activity in the range, not one per job.
// It answers what moved, what is stuck, what costs most and what needs the person. Sorted: Needs you, Running,
// Failed, Queued, Done (newest first in each group). Numbers sit in fixed right-aligned columns (rg-num num). The
// model comes from workflow.js layout(); this module only reads it and returns markup (no inline style or handler).

import { chipHtml, esc } from "../dom.js";
import { MISSING, fmtDuration, fmtTokens } from "../format.js";
import { buildHash } from "../router.js";

const FILTERS = [["all", "All"], ["needs", "Needs you"], ["running", "Running"], ["failed", "Failed"],
  ["done", "Done"]];
const GROUP = { needs: 0, running: 1, failed: 2, queued: 3, done: 4 };
const CHIP = { needs: ["Needs you", "warning"], running: ["Running", "sonnet"], failed: ["Failed", "danger"],
  queued: ["Queued", "neutral"], done: ["Done", "success"] };
const TF_RE = /(?:^|,)tf:(needs|running|failed|done)(?:,|$)/;

// The table filter of the route (tf:<key> in f=), or All.
function filterOf(route) {
  const f = route && route.filters && route.filters.f ? String(route.filters.f) : "";
  const m = TF_RE.exec(f);
  return m ? m[1] : "all";
}

// The hash of the table with a filter key and the range of the model.
function filterHref(model, key) {
  const route = model.route || { name: "home", id: null, filters: {} };
  const range = model.range && model.range.key ? model.range.key : "today";
  const f = "range:" + range + (key === "all" ? "" : ",tf:" + key);
  return buildHash({ name: route.name, id: route.id, section: "workflow", view: "table", item: null,
    filters: { f: f } });
}

// The Work item of a task (the Work section, opened on the task).
function workHref(pid, task) {
  return buildHash({ name: "project", id: pid, section: "work", view: null, item: task, filters: {} });
}

// The task title from the Map's cards when the snapshot has them, else the task id.
function titlesOf(model) {
  const map = new Map();
  (model.cards || []).forEach(function (c) {
    if (c && c.task && c.title) map.set((c.pid || "") + "|" + c.task, String(c.title));
  });
  return map;
}

// One row per task: its jobs (in range), and whether the range has it queued or blocked.
function rowsOf(model) {
  const rows = new Map();
  const titles = titlesOf(model);
  const rowFor = function (it) {
    const key = (it.pid || "") + "|" + it.task;
    if (!rows.has(key)) {
      rows.set(key, { pid: it.pid, pname: it.pname, task: it.task, jobs: [], queued: false, blocked: false,
        title: titles.get(key) || "" });
    }
    return rows.get(key);
  };
  (model.items || []).forEach(function (it) {
    if (!it.task) return;
    if (it.kind === "job") rowFor(it).jobs.push(it);
    else if (it.kind === "queue") rowFor(it).queued = true;
    else if (it.kind === "blocked") {
      const row = rowFor(it);
      row.blocked = true;
      row.blockedStart = it.start;
    }
  });
  return Array.from(rows.values());
}

function summarize(row, now) {
  const jobs = row.jobs.slice().sort(function (a, b) {
    return (b.start || 0) - (a.start || 0);
  });
  const last = jobs[0] || null;
  let state = "done";
  if (row.blocked) state = "needs";
  else if (jobs.some(function (j) { return j.live; })) state = "running";
  else if (last && last.word === "failed") state = "failed";
  else if (row.queued) state = "queued";
  else if (last) state = "done";
  const starts = jobs.map(function (j) { return j.start; }).filter(function (v) { return v != null; });
  const ends = jobs.map(function (j) { return j.live ? now : (j.end == null ? now : j.end); });
  const blockedAt = row.blocked ? [row.blockedStart == null ? now : row.blockedStart] : [];
  const first = Math.min.apply(null, starts.concat(blockedAt).concat([Infinity]));
  const latest = Math.max.apply(null, ends.concat([row.blocked ? now : 0]));
  const tokens = jobs.reduce(function (sum, j) { return j.tokensK == null ? sum : sum + j.tokensK; }, 0);
  const hasTokens = jobs.some(function (j) { return j.tokensK != null; });
  return {
    state: state,
    last: last,
    running: jobs.filter(function (j) { return j.live; }).length,
    total: jobs.length,
    tokensK: hasTokens ? tokens : null,
    elapsed: isFinite(first) && latest > 0 ? (latest - first) / 1000 : null,
    updated: Math.max(latest, row.queued ? now : 0),
  };
}

function chipFor(state) {
  const c = CHIP[state];
  return chipHtml(c[0], c[1]);
}

function actionFor(state) {
  if (state === "needs") return { text: "Answer" };
  if (state === "failed") return { text: "Retry in Work" };
  return { text: "Open in Work" };
}

function emptyText(model) {
  const key = filterOf(model.route);
  const label = FILTERS.filter(function (f) { return f[0] === key; })[0];
  return '<p class="wf-hint">' + (key === "all" ? "No tasks in this range."
    : "No tasks match " + esc(label ? label[1] : key) + " in this range.") + ' <a href="' +
    esc(filterHref(model, "all")) + '">Show all</a></p>';
}

function filterNav(model, active) {
  return '<nav class="seg plan-views" aria-label="Filter tasks">' + FILTERS.map(function (f) {
    const on = f[0] === active;
    return '<a href="' + esc(filterHref(model, f[0])) + '"' + (on ? ' aria-current="page"' : "") + ">" +
      esc(f[1]) + "</a>";
  }).join("") + "</nav>";
}

function rowHtml(row, sum, model) {
  const action = actionFor(sum.state);
  const idText = row.task ? esc(row.task) : MISSING;
  const project = model.multi && row.pname ? " · " + esc(row.pname) : "";
  const title = esc(row.title || row.task || MISSING);
  const last = sum.last;
  return "<tr>" + '<td class="wf-id">' + idText + project + "</td>" +
    '<td class="hd-c" title="' + esc(row.title || row.task || "") + '">' + title + "</td>" +
    "<td>" + chipFor(sum.state) + "</td>" +
    "<td>" + esc(last && last.model ? last.model : MISSING) + "</td>" +
    '<td class="rg-num num">' + sum.running + "/" + sum.total + "</td>" +
    '<td class="rg-num num">' + esc(fmtTokens(sum.tokensK)) + "</td>" +
    '<td class="rg-num num">' + esc(fmtDuration(sum.elapsed)) + "</td>" +
    '<td class="rg-num num">' + esc(sum.updated ? fmtDuration((model.now - sum.updated) / 1000) + " ago"
      : MISSING) + "</td>" +
    "<td>" + '<a class="btn btn-small" href="' + esc(workHref(row.pid, row.task)) + '" aria-label="' +
    esc(action.text + " " + (row.task || "")) + '">' + esc(action.text) + "</a></td></tr>";
}

// The Table: filter row, then one row per task. Empty when no task has activity in the range.
export function tableHtml(model) {
  const key = filterOf(model.route);
  const all = rowsOf(model).map(function (row) {
    return { row: row, sum: summarize(row, model.now) };
  });
  all.sort(function (a, b) {
    const g = GROUP[a.sum.state] - GROUP[b.sum.state];
    return g !== 0 ? g : b.sum.updated - a.sum.updated;
  });
  const shown = all.filter(function (x) {
    return key === "all" || x.sum.state === key;
  });
  const nav = filterNav(model, key);
  if (!shown.length) return nav + emptyText(model);
  const head = "<tr>" + ["ID", "Title", "State", "Model", "Jobs", "Tokens", "Elapsed", "Updated"].map(function (h) {
    return '<th scope="col"' + (/^(Jobs|Tokens|Elapsed|Updated)$/.test(h) ? ' class="rg-num"' : "") + ">" + h + "</th>";
  }).join("") + '<th scope="col">Next</th></tr>';
  const body = shown.map(function (x) {
    return rowHtml(x.row, x.sum, model);
  }).join("");
  return nav + '<div class="wf-scroll" tabindex="0" role="region" aria-label="Tasks table">' +
    '<table class="wf-table"><caption class="sr-only">Tasks in this range</caption>' +
    "<thead>" + head + "</thead><tbody>" + body + "</tbody></table></div>";
}
