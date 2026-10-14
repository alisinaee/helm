// Issues (WP32). Project scope only. A new-issue form on top (title, task link, blocker toggle), then the issues with
// three filters: Open (the default), Blockers and All. Close is one click. The title opens the issue's details
// (#/p/<id>/issues/i/<I n>). An open blocker marks its task Blocked everywhere: the snapshot's blocked list does that.
// The snapshot carries open issues only, so closed ones are not listed here yet.

import { run } from "../cmd.js";
import { chipHtml, emptyHtml, esc } from "../dom.js";
import { fmtCount, MISSING } from "../format.js";
import { itemHash, pageState } from "./inbox.js";

const TITLE_MAX = 120;
const FILTERS = [["open", "Open"], ["blockers", "Blockers"], ["all", "All"]];
const KIND_TONE = { blocker: "danger", risk: "warning", bug: "neutral", question: "neutral" };

function filterOf(vm) {
  const f = vm.route.filters ? vm.route.filters.f : null;
  return f === "blockers" || f === "all" ? f : "open";
}

function rowsFor(snap, filter) {
  if (filter === "blockers") {
    return snap.issues.filter(function (issue) {
      return issue.kind === "blocker";
    });
  }
  return snap.issues.slice();
}

function filterNav(vm, snap, filter) {
  const base = "#/p/" + encodeURIComponent(vm.route.id) + "/issues";
  const blockers = snap.issues.filter(function (i) {
    return i.kind === "blocker";
  }).length;
  const counts = { open: snap.issues.length, blockers: blockers, all: snap.issues.length };
  return '<nav class="seg iss-filters" aria-label="Filter issues">' + FILTERS.map(function (f) {
    const key = f[0];
    const href = base + (key === "open" ? "" : "?f=" + key);
    return '<a href="' + esc(href) + '"' + (key === filter ? ' aria-current="true"' : "") + ">" +
      esc(f[1] + " " + fmtCount(counts[key])) + "</a>";
  }).join("") + "</nav>";
}

function taskOptions(snap) {
  const open = snap.tasks.filter(function (t) {
    return t.state !== "done";
  });
  return open.map(function (t) {
    return '<option value="' + esc(t.id) + '">' + esc(t.id + " " + t.title) + "</option>";
  }).join("");
}

function formHtml(snap) {
  return '<form class="iss-form" data-form="issue-new" aria-labelledby="iss-new-h">' +
    '<h2 class="ov-h" id="iss-new-h">New issue</h2>' +
    '<p class="iss-fld"><label class="iss-label" for="iss-title">Title</label>' +
    '<input class="iss-input" id="iss-title" name="title" type="text" maxlength="' + TITLE_MAX +
    '" autocomplete="off" aria-describedby="iss-title-help iss-title-err"></p>' +
    '<p class="iss-help" id="iss-title-help">Brief one-line summary.</p>' +
    '<p class="iss-err" id="iss-title-err" role="alert"></p>' +
    '<p class="iss-fld"><label class="iss-label" for="iss-task">Task (optional)</label>' +
    '<select class="iss-input" id="iss-task" name="task"><option value="">No task</option>' +
    taskOptions(snap) + "</select></p>" +
    '<p class="iss-fld iss-check"><label><input name="blocker" type="checkbox"> ' +
    "<span>Blocks linked task until closed.</span></label></p>" +
    '<p><button type="submit" class="btn btn-primary" data-focus="issue-submit">Add issue</button></p></form>';
}

function linksHtml(vm, issue) {
  if (!issue.tasks.length) return '<p class="iss-links">No task linked.</p>';
  const links = issue.tasks.map(function (taskId) {
    return '<a href="' + esc(itemHash(vm.route.id, taskId)) + '">' + esc(taskId) + "</a>";
  }).join(", ");
  return '<p class="iss-links">' + (issue.kind === "blocker" ? "Blocks " : "Linked to ") + links + "</p>";
}

function rowHtml(vm, issue) {
  const id = esc(issue.id);
  const detail = "#/p/" + encodeURIComponent(vm.route.id) + "/issues/i/" + encodeURIComponent(issue.id);
  return '<li class="iss is-' + esc(issue.kind || "issue") + '" data-issue="' + id + '">' +
    '<p class="iss-top row-grid">' + chipHtml(issue.kind || "issue", KIND_TONE[issue.kind] || "neutral") +
    chipHtml("sev " + (issue.sev == null ? MISSING : issue.sev), "neutral") +
    '<span class="iss-status rg-num">' + esc(issue.status || "open") + "</span></p>" +
    '<p class="iss-title"><a href="' + esc(detail) + '">' + id + " " + esc(issue.title) + "</a></p>" +
    linksHtml(vm, issue) +
    '<p class="iss-act"><button type="button" class="btn btn-small" data-action="issue-close" data-issue="' + id +
    '" aria-label="Close ' + id + '">Close</button></p></li>';
}

export function sectionView(vm) {
  if (vm.route.name !== "project") {
    return emptyHtml("Issues belong to one project.", '<a href="#/all/overview">Go to All projects</a>');
  }
  const state = pageState(vm);
  if (state) return state;
  const snap = vm.project.snapshot;
  const filter = filterOf(vm);
  const rows = rowsFor(snap, filter);
  const blockers = snap.issues.filter(function (i) {
    return i.kind === "blocker";
  }).length;
  const list = rows.length
    ? '<ul class="iss-list" aria-label="Issues">' + rows.map(function (issue) {
      return rowHtml(vm, issue);
    }).join("") + "</ul>"
    : emptyHtml(filter === "blockers" ? "No open blockers." : "No open issues.");
  const note = filter === "all" ? '<p class="page-note">Closed issues are not shown here yet.</p>' : "";
  return '<div class="page-head"><p class="page-title">Issues</p><p class="page-note">' +
    esc(fmtCount(snap.issues.length) + " open · " + fmtCount(blockers) + " blockers") + "</p></div>" +
    formHtml(snap) + filterNav(vm, snap, filter) + list + note;
}

export function pageAction(action, el) {
  if (action === "issue-close") {
    const id = el.getAttribute("data-issue");
    run("issue.close", { id: id }, { label: "Closed " + id });
  }
}

function onSubmit(event) {
  const form = event.target;
  if (!form || form.getAttribute("data-form") !== "issue-new") return;
  event.preventDefault();
  const title = form.elements.title.value.trim();
  const err = form.querySelector(".iss-err");
  if (!title) {
    if (err) err.textContent = "Give the issue a title.";
    form.elements.title.focus();
    return;
  }
  if (err) err.textContent = "";
  const task = form.elements.task.value;
  const blocker = form.elements.blocker.checked;
  form.reset();
  run("issue.new", { title: title, kind: blocker ? "blocker" : "bug", sev: 2, tasks: task ? [task] : [] },
    { label: "Issue added" });
}

// Module setup runs once when the section first loads. The guard keeps the module importable without a page (tests).
if (typeof document !== "undefined") {
  document.addEventListener("submit", onSubmit);
}
