// Details tab (WP29): the task, issue or question named by the route (#/p/<id>/<section>/i/<item>), or the project card
// when nothing is selected. Values that a write changed show at once from pendingValue() (cmd.js), and comments that
// are still being saved show from a short list held here. Rules and definition of done show only when the snapshot
// has them; this build's snapshot has neither for a task yet, so those parts are hidden rather than invented.

import { bannerHtml, emptyHtml, esc, meterHtml } from "../dom.js";
import { pendingValue, run } from "../cmd.js";
import { fmtTokens } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { rowFacts } from "./projects.js";

const STATUSES = [["todo", "To do"], ["partial", "Partial"], ["done", "Done"], ["hold", "On hold"]];
const COMMENT_HOLD_MS = 30000;

export function taskKey(project, id, what) {
  return "task:" + project + ":" + id + ":" + what;
}

export function subKey(project, addr) {
  return "sub:" + project + ":" + addr;
}

export function issueKey(project, id) {
  return "issue:" + project + ":" + id;
}

// A pending value for a control, or the snapshot value when no write is in flight.
export function pick(key, snap, now, fallback) {
  const value = pendingValue(key, snap.fetchedAt, now);
  return value === undefined ? fallback : value;
}

// Comments whose write has not reached a snapshot yet. A settled entry drops once a newer snapshot arrives.
let seq = 0;
const optimistic = [];

export function queueComment(on, text) {
  const entry = { seq: ++seq, on: on, t: text, by: "gui", addedAt: Date.now(), doneAt: null };
  optimistic.push(entry);
  return entry;
}

export function dropComment(entry) {
  const at = optimistic.indexOf(entry);
  if (at >= 0) optimistic.splice(at, 1);
}

export function settleComment(entry) {
  entry.doneAt = Date.now();
}

export function commentsFor(snap, on, now) {
  for (let i = optimistic.length - 1; i >= 0; i--) {
    const entry = optimistic[i];
    const stale = now - entry.addedAt > COMMENT_HOLD_MS;
    const seen = entry.doneAt !== null && snap.fetchedAt > entry.doneAt;
    if (stale || seen) optimistic.splice(i, 1);
  }
  const real = (snap.comments[on] || []).map(function (c) {
    return { by: c.by, at: c.at, t: c.t, pending: false };
  });
  const waiting = optimistic.filter(function (e) {
    return e.on === on;
  }).map(function (e) {
    return { by: e.by, at: null, t: e.t, pending: true };
  });
  return real.concat(waiting);
}

function backHtml() {
  return '<div class="d-back"><button type="button" class="btn-small" data-side="back" data-focus="side-back">' +
    "Back to Projects</button></div>";
}

function sectionHtml(title, body) {
  return '<section class="d-sec" aria-label="' + esc(title) + '"><h3 class="d-h">' + esc(title) + "</h3>" +
    body + "</section>";
}

function listHtml(items, empty) {
  if (!items.length) return '<p class="d-meta">' + esc(empty) + "</p>";
  return '<ul class="d-list">' + items.join("") + "</ul>";
}

function disabledAttr(vm) {
  return vm.conn && vm.conn.ok === false ? " disabled" : "";
}

function projectCard(vm) {
  if (vm.route.name !== "project" || !vm.project) {
    return emptyHtml("Select a project to view details.",
      "<span>Open one from Projects, or go to <a href=\"#/all/overview\">All projects</a>.</span>");
  }
  if (vm.project.notFound) {
    return emptyHtml("This project is not registered.", "<span>Pick another from Projects.</span>");
  }
  const snap = vm.project.snapshot;
  if (!snap) {
    return emptyHtml("Loading this project.", "<span>Details load once snapshot syncs.</span>");
  }
  const facts = rowFacts({ id: snap.id, name: snap.title, progress: snap.progress, needUser: snap.needUser,
    running: snap.runningCount, stale: false }, snap);
  const control = snap.control.stopped ? "Stopped" : snap.control.blocked ? "Blocked" +
    (snap.control.reason ? ": " + snap.control.reason : "") : "Running";
  const pct = facts.progress == null ? 0 : Math.round(facts.progress * 100);
  const rows = [
    ["Progress", pct + "% done (" + (snap.done == null ? "?" : snap.done) + " of " +
      (snap.total == null ? "?" : snap.total) + ")"],
    ["Remaining tasks", snap.tasksLeft == null ? "?" : String(snap.tasksLeft)],
    ["Remaining tokens", fmtTokens(snap.tokensLeftK)],
    ["Needs you", String(snap.needUser == null ? 0 : snap.needUser)],
    ["Open questions", String(snap.questions.length)],
    ["Blocking issues", String(facts.blockers || 0)],
    ["Running jobs", String(snap.runningCount == null ? 0 : snap.runningCount)],
    ["Control", control],
  ];
  const dl = '<dl class="d-dl">' + rows.map(function (r) {
    return "<dt>" + esc(r[0]) + "</dt><dd>" + esc(r[1]) + "</dd>";
  }).join("") + "</dl>";
  return '<div class="d-head"><p class="d-id">' + esc(snap.id || "") + '</p><h3 class="d-title">' +
    esc(snap.title) + '</h3></div><div class="d-meter">' + meterHtml(pct, "accent") + "</div>" +
    sectionHtml("Project", dl) +
    '<p class="d-meta"><a href="#/p/' + esc(snap.id) + '/work">Open Work for this project</a></p>';
}

function statusHtml(task, state, vm) {
  const off = disabledAttr(vm);
  const buttons = STATUSES.map(function (s) {
    return '<button type="button" class="btn" aria-pressed="' + (state === s[0]) + '" data-side="status" data-id="' +
      esc(task.id) + '" data-status="' + esc(s[0]) + '" data-focus="st-' + esc(s[0]) + '" aria-label="' +
      esc("Set status to " + s[1] + " for " + task.id) + '"' + off + ">" +
      esc(s[1]) + "</button>";
  }).join("");
  return sectionHtml("Status", '<div class="seg d-btns" role="group" aria-label="Status">' + buttons + "</div>");
}

// The queued wording follows presence (R7.1 T6): "none" means no session is listening, so the Copy command is offered.
function queuedWord(session) {
  if (session === "watching") return "Queued, a session is picking it up";
  if (session === "open") return "Queued, picked up at the session's next stop";
  if (session === "none") return "Queued: waiting for terminal session";
  return "Queued to start";
}

// POSIX-style quoting for the shell line: a plain path stays bare, any other path is single-quoted.
function shellQuote(text) {
  if (/^[A-Za-z0-9_./-]+$/.test(text)) return text;
  return "'" + text.replace(/'/g, "'\\''") + "'";
}

function launchCommand(path) {
  return "cd " + shellQuote(path) + " && claude \"roadmap watch\"";
}

// Copy the launch command. Without clipboard access the command stays on screen to select by hand.
export function copyLaunch(el) {
  const cmd = el.getAttribute("data-cmd") || "";
  const report = function (ok) {
    el.textContent = ok ? "Copied" : "Copy failed. Please copy manually.";
  };
  if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
    report(false);
    return;
  }
  navigator.clipboard.writeText(cmd).then(function () {
    report(true);
  }, function () {
    report(false);
  });
}

function queueHtml(task, snap, vm, now) {
  const project = vm.route.id;
  const pend = pick(taskKey(project, task.id, "queue"), snap, now, undefined);
  const queued = snap.queue.some(function (q) {
    return q.task === task.id;
  });
  const running = snap.running.some(function (j) {
    return j.task === task.id;
  });
  const waiting = (pend === "start" || queued) && snap.session === "none" && Boolean(snap.project && snap.project.path);
  let word = "Not queued";
  if (pend === "stop") word = "Stop requested";
  else if (pend === "start" || queued) word = queuedWord(snap.session);
  else if (running) word = "Running";
  const off = disabledAttr(vm);
  const startOk = !queued && !running && pend === undefined;
  const stopOk = running && !queued && pend === undefined;
  const buttons = '<button type="button" class="btn" data-side="start" data-id="' + esc(task.id) +
    '" aria-label="' + esc("Start task " + task.id) + '" data-focus="start"' + (startOk ? "" : " disabled") +
    off + ">Start</button>" +
    '<button type="button" class="btn" data-side="stop" data-id="' + esc(task.id) +
    '" aria-label="' + esc("Stop task " + task.id) + '" data-focus="stop"' +
    (stopOk ? "" : " disabled") + off + ">Stop</button>";
  if (!waiting) {
    return sectionHtml("Run", '<p class="d-meta" role="status">' + esc(word) + "</p>" +
      '<div class="d-btns">' + buttons + "</div>");
  }
  const cmd = launchCommand(snap.project.path);
  const copy = '<button type="button" class="btn" data-side="copy-launch" data-cmd="' + esc(cmd) +
    '" aria-label="Copy launch command" data-focus="copy-launch">Copy command</button>';
  return sectionHtml("Run", '<p class="d-meta" role="status">' + esc(word) + "</p>" +
    '<p class="d-meta"><code>' + esc(cmd) + "</code></p>" + '<div class="d-btns">' + buttons + copy + "</div>");
}

function capHtml(task, snap, vm, now) {
  const cap = pick(taskKey(vm.route.id, task.id, "cap"), snap, now, task.capK);
  const off = disabledAttr(vm);
  const field = "cap-" + task.id;
  return sectionHtml("Cap", '<form class="d-form" data-side-form="cap" data-id="' + esc(task.id) + '">' +
    '<label for="' + esc(field) + '">Token cap (thousands) <input id="' + esc(field) +
    '" name="value" type="number" min="0" step="any" inputmode="decimal" value="' +
    esc(cap == null ? "" : cap) + '" data-focus="cap-input"' + off + "></label>" +
    '<button type="submit" class="btn" aria-label="' + esc("Save token cap for " + task.id) +
    '" data-focus="cap-save"' + off + ">Save cap</button>" +
    (cap == null ? "" : '<button type="button" class="btn" data-side="cap-clear" data-id="' + esc(task.id) +
      '" aria-label="' + esc("Clear token cap for " + task.id) + '" data-focus="cap-clear"' + off +
      ">Clear cap</button>") + "</form>");
}

function subsHtml(task, snap, vm, now) {
  const project = vm.route.id;
  const off = disabledAttr(vm);
  const items = (task.subs || []).map(function (sub, index) {
    const addr = task.id + "/" + (index + 1);
    const done = pick(subKey(project, addr), snap, now, sub.d);
    return '<li><label class="d-sub" data-done="' +
      (done === true) + '"><input type="checkbox" data-side="sub" data-addr="' +
      esc(addr) + '"' + (done ? " checked" : "") + ' data-focus="sub-' + esc(addr) + '"' + off + "><span>" +
      esc(sub.t) + "</span></label></li>";
  });
  const field = "sub-new-" + task.id;
  const add = '<form class="d-form" data-side-form="sub-add" data-id="' + esc(task.id) + '">' +
    '<label for="' + esc(field) + '">Add a subtask <input id="' + esc(field) +
    '" name="title" type="text" maxlength="200" data-focus="sub-add"' + off + "></label>" +
    '<button type="submit" class="btn" aria-label="' + esc("Add subtask to " + task.id) +
    '" data-focus="sub-add-btn"' + off + ">Add subtask</button></form>";
  return sectionHtml("Subtasks", listHtml(items, "No subtasks yet.") + add);
}

function commentsHtml(task, snap, vm, now) {
  const off = disabledAttr(vm);
  const items = commentsFor(snap, task.id, now).map(function (c) {
    const who = c.by || "someone";
    const when = c.pending ? "saving" : (c.at || "");
    return '<li class="d-comment"><p>' + esc(c.t) + '</p><p class="d-meta">' + esc(who) +
      (when ? " · " + esc(when) : "") + "</p></li>";
  });
  const field = "c-new-" + task.id;
  const add = '<form class="d-form" data-side-form="comment" data-id="' + esc(task.id) + '">' +
    '<label for="' + esc(field) + '">Add a comment <input id="' + esc(field) +
    '" name="text" type="text" maxlength="2000" data-focus="comment-text"' + off + "></label>" +
    '<button type="submit" class="btn" aria-label="' + esc("Add comment to " + task.id) +
    '" data-focus="comment-btn"' + off + ">Add comment</button></form>";
  return sectionHtml("Comments", listHtml(items, "No comments yet.") + add);
}

function linkedHtml(task, snap) {
  const issues = snap.issues.filter(function (i) {
    return i.tasks.indexOf(task.id) >= 0;
  }).map(function (i) {
    return '<li><a href="#/p/' + esc(snap.id) + '/issues/i/' + esc(i.id) + '">' + esc(i.id) + " " +
      esc(i.title) + "</a></li>";
  });
  const questions = snap.questions.filter(function (q) {
    return q.task === task.id;
  }).map(function (q) {
    return '<li><a href="#/p/' + esc(snap.id) + '/inbox/i/' + esc(q.id) + '">' + esc(q.id) + " " + esc(q.text) +
      "</a></li>";
  });
  const jobs = snap.jobs.filter(function (j) {
    return j.task === task.id;
  }).slice(-3).map(function (j) {
    return "<li>" + esc(j.id) + " " + esc(j.title || "") + " · " + esc(j.status) + "</li>";
  });
  return sectionHtml("Linked", '<p class="d-meta">Issues</p>' + listHtml(issues, "None open.") +
    '<p class="d-meta">Questions</p>' + listHtml(questions, "None open.") +
    '<p class="d-meta">Jobs</p>' + listHtml(jobs, "No jobs yet."));
}

function rulesHtml(task, snap) {
  if (!snap.rules || !snap.rules.length) return "";
  const mine = snap.rules.filter(function (r) {
    return r.scope === "all" || r.scope === "task:" + task.id || r.scope === "phase:" + task.phase;
  });
  if (!mine.length) return "";
  return sectionHtml("Applicable rules",listHtml(mine.map(function (r) {
    return "<li>" + esc(r.text) + "</li>";
  }), ""));
}

// WP55: the features that name this task (its feats in the snapshot).
function featureRowsOf(snap, taskId) {
  const rows = snap.features && Array.isArray(snap.features.rows) ? snap.features.rows : [];
  const task = (snap.tasks || []).find(function (t) {
    return t.id === taskId;
  });
  const feats = task && Array.isArray(task.feats) ? task.feats : [];
  return rows.filter(function (row) {
    return feats.indexOf(row.id) >= 0;
  });
}

// Feature chips link to the Planner with that feature opened. A task with no feature gets a picker that links it.
// The section is left out when the snapshot has no features block (an older build).
function featureHtml(vm, snap, task) {
  if (!snap.features) return "";
  const project = esc(vm.route.id);
  const linked = featureRowsOf(snap, task.id);
  if (linked.length) {
    const chips = linked.map(function (row) {
      return '<li><a class="chip chip-neutral" href="#/p/' + project + "/planner?f=" + encodeURIComponent(row.id) +
        '">' + esc(row.id + " " + row.title) + "</a></li>";
    }).join("");
    return sectionHtml("Feature", '<ul class="d-list">' + chips + "</ul>");
  }
  const rows = Array.isArray(snap.features.rows) ? snap.features.rows : [];
  if (!rows.length) return sectionHtml("Feature", '<p class="d-meta">No features yet.</p>');
  const off = disabledAttr(vm);
  const options = rows.map(function (row) {
    return '<option value="' + esc(row.id) + '">' + esc(row.id + " " + row.title) + "</option>";
  }).join("");
  const field = "feat-link-" + task.id;
  return sectionHtml("Feature", '<p class="d-meta">No feature linked.</p>' +
    '<label for="' + esc(field) + '">Link to feature <select id="' + esc(field) +
    '" data-side="feat-link" data-id="' + esc(task.id) + '" data-focus="feat-link"' + off + ">" +
    '<option value="">Choose a feature</option>' + options + "</select></label>");
}

// The drawer's feature picker (app.js routes the change event here). The write goes through cmd.js run().
export function featureLinkChange(el) {
  const feat = el.value;
  const task = el.getAttribute("data-id");
  if (!feat || !task) return;
  el.blur();
  run("feature.link", { task: task, feats: [feat] }, { label: "Linked " + task + " to " + feat });
}

function taskView(vm, snap, task, now) {
  const state = pick(taskKey(vm.route.id, task.id, "status"), snap, now, task.state);
  const copy = copyButton("task", task.id, task.title, { project: vm.route.id,
    sum: refSummary("task", task, snap) });
  return '<div class="d-head"><p class="d-id">' + esc(task.id) + " · " + esc(task.phase) + (copy ? " " + copy : "") +
    '</p><h3 class="d-title">' +
    esc(task.title) + "</h3>" +
    '<p class="d-meta">' + esc(planLine(task)) + "</p></div>" +
    statusHtml(task, state, vm) + featureHtml(vm, snap, task) + queueHtml(task, snap, vm, now) +
    capHtml(task, snap, vm, now) +
    subsHtml(task, snap, vm, now) + commentsHtml(task, snap, vm, now) + linkedHtml(task, snap) +
    rulesHtml(task, snap) +
    (task.dod ? sectionHtml("Completion criteria",'<p>' + esc(task.dod) + "</p>") : "");
}

function planLine(task) {
  const parts = [];
  if (task.model) parts.push("model " + task.model);
  if (task.thinking) parts.push("thinking " + task.thinking);
  parts.push("about " + fmtTokens(task.tokensK));
  parts.push("check " + task.check);
  return parts.join(" · ");
}

function issueView(vm, snap, issue, now) {
  const closed = pick(issueKey(vm.route.id, issue.id), snap, now, undefined) === "closed";
  const off = disabledAttr(vm);
  const meta = (issue.kind || "issue") + " · " + (closed ? "closed" : issue.status || "open");
  const action = closed ? '<p class="d-meta" role="status">Closed</p>' :
    '<div class="d-btns"><button type="button" class="btn" data-side="close-issue" data-id="' + esc(issue.id) +
    '" aria-label="' + esc("Close issue " + issue.id) + '" data-focus="close-issue"' + off +
    ">Close issue</button></div>";
  return '<div class="d-head"><p class="d-id">' + esc(issue.id) + '</p><h3 class="d-title">' + esc(issue.title) +
    '</h3><p class="d-meta">' + esc(meta) + "</p></div>" +
    sectionHtml("Action", action) +
    sectionHtml("Tasks", listHtml(issue.tasks.map(function (t) {
      return "<li>" + esc(t) + "</li>";
    }), "No tasks linked."));
}

// The snapshot lists open questions only, so the answer controls always show here.
function questionView(vm, question) {
  const off = disabledAttr(vm);
  const options = question.opts.map(function (opt, index) {
    return '<button type="button" class="btn" data-side="answer" data-id="' + esc(question.id) + '" data-value="' +
      esc(opt) + '" aria-label="' + esc("Answer " + opt + " for " + question.id) +
      '" data-focus="ans-' + index + '"' + off + ">" + esc(opt) + "</button>";
  }).join("");
  const field = "ans-new-" + question.id;
  const group = '<div class="d-btns" role="group" aria-label="' + esc("Answers for " + question.id) + '">';
  const answer = sectionHtml("Answer", (options ? group + options + "</div>" : "") +
    '<form class="d-form" data-side-form="answer" data-id="' + esc(question.id) + '">' +
    '<label for="' + esc(field) + '">Other answer <input id="' + esc(field) +
    '" name="value" type="text" maxlength="500" data-focus="answer-text"' + off + "></label>" +
    '<button type="submit" class="btn" aria-label="' + esc("Send answer for " + question.id) +
    '" data-focus="answer-btn"' + off + ">Send answer</button></form>");
  const meta = (question.task ? "For " + question.task + " · " : "") + "open" +
    (question.block ? " · blocks work" : "");
  return '<div class="d-head"><p class="d-id">' + esc(question.id) + '</p><h3 class="d-title">' + esc(question.text) +
    '</h3><p class="d-meta">' + esc(meta) + "</p></div>" + answer;
}

function notOpenView() {
  return bannerHtml("warning", "Item not found or closed.",
    "It may have been closed or answered. Go back to Projects.");
}

// The panel's Details tab. Everything it shows comes from the view model and the write-pending values.
export function detailsView(vm) {
  const now = vm.now;
  const item = vm.route.item;
  if (!item) return projectCard(vm);
  const snap = vm.project && vm.project.snapshot;
  if (vm.route.name !== "project" || !snap) {
    return backHtml() + projectCard(vm);
  }
  const task = snap.tasks.find(function (t) {
    return t.id === item;
  });
  if (task) return backHtml() + taskView(vm, snap, task, now);
  const issue = snap.issues.find(function (i) {
    return i.id === item;
  });
  if (issue) return backHtml() + issueView(vm, snap, issue, now);
  const question = snap.questions.find(function (q) {
    return q.id === item;
  });
  if (question) return backHtml() + questionView(vm, question);
  return backHtml() + notOpenView();
}
