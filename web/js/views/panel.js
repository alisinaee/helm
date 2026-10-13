// Right panel (WP29): one <aside> with two tabs, Projects and Details. The tab comes from the saved panelTab, except
// that selecting an item (a route with /i/<item>) opens Details once. Esc with an item selected goes back to Projects
// (and keeps the sheet open); j and k move between the project rows. Every write goes through cmd.js run(), which
// shows the change at once, posts it, and gives an Undo toast. The handlers sit on #side, which survives re-renders.

import { esc } from "../dom.js";
import { run } from "../cmd.js";
import { bindKey } from "../keys.js";
import { buildHash, currentRoute } from "../router.js";
import { updateUi } from "../state.js";
import { showToast } from "./toast.js";
import { projectsView } from "./projects.js";
import { dropComment, detailsView, issueKey, queueComment, settleComment, subKey, taskKey } from "./details.js";

let rerender = function () {};
let lastItem = null;

function tabButton(id, label, tab) {
  const on = id === tab;
  return '<button type="button" role="tab" id="tab-' + esc(id) + '" class="side-tab" aria-selected="' + on +
    '" aria-controls="side-body" data-side="tab" data-tab="' + esc(id) + '" data-focus="tab-' + esc(id) + '">' +
    esc(label) + "</button>";
}

// The panel's inner markup: the tabs, a close button (the sheet at phone width needs one), and the active body.
export function panelView(vm) {
  const route = vm.route;
  let tab = vm.ui.panelTab === "details" ? "details" : "projects";
  if (route.item && route.item !== lastItem) tab = "details";
  lastItem = route.item || null;
  if (tab !== vm.ui.panelTab) {
    updateUi(function (ui) {
      ui.panelTab = tab;
    });
  }
  const body = tab === "details" ? detailsView(vm) : projectsView(vm);
  return '<div class="side-tabs" role="tablist" aria-label="Panel">' +
    tabButton("projects", "Projects", tab) + tabButton("details", "Details", tab) +
    '<button type="button" class="btn-small side-close" data-action="panel-close" aria-label="Close panel" ' +
    'data-focus="side-close">Close</button></div>' +
    '<div class="side-body" id="side-body" role="tabpanel" aria-labelledby="tab-' + esc(tab) + '">' + body + "</div>";
}

function projectId() {
  const route = currentRoute();
  if (route.name === "project") return route.id;
  showToast({ text: "Choose a project first.", tone: "danger" });
  return null;
}

function selectTab(tab) {
  updateUi(function (ui) {
    ui.panelTab = tab === "details" ? "details" : "projects";
  });
  rerender();
}

// Back to Projects: drop the item from the route (the hash change re-renders) and show the Projects tab.
function backToProjects() {
  updateUi(function (ui) {
    ui.panelTab = "projects";
  });
  const route = currentRoute();
  window.location.hash = buildHash(Object.assign({}, route, { item: null }));
}

async function setStatus(el) {
  const project = projectId();
  if (!project) return;
  const id = el.getAttribute("data-id");
  const status = el.getAttribute("data-status");
  await run("task.status", { id: id, status: status }, {
    project: project,
    key: taskKey(project, id, "status"),
    value: status,
    label: id + " set to " + status,
  });
}

async function queueTask(el, op) {
  const project = projectId();
  if (!project) return;
  const id = el.getAttribute("data-id");
  const starting = op === "task.start";
  await run(op, { id: id }, {
    project: project,
    key: taskKey(project, id, "queue"),
    value: starting ? "start" : "stop",
    label: starting ? "Queued " + id + " to start" : "Stop requested for " + id,
  });
}

// Cap in thousands of tokens. An empty field clears the cap; anything that is not a number of 0 or more is refused.
async function setCap(id, raw) {
  const project = projectId();
  if (!project) return;
  const text = String(raw == null ? "" : raw).trim();
  let value = null;
  if (text !== "") {
    value = Number(text);
    if (!Number.isFinite(value) || value < 0) {
      showToast({ text: "A cap is a number of thousands of tokens, 0 or more.", tone: "danger" });
      return;
    }
  }
  await run("task.cap", { id: id, value: value }, {
    project: project,
    key: taskKey(project, id, "cap"),
    value: value,
    label: value == null ? "Cap cleared for " + id : "Cap set for " + id,
  });
}

async function toggleSub(el) {
  const project = projectId();
  if (!project) return;
  const addr = el.getAttribute("data-addr");
  const done = el.checked === true;
  await run("subtask.toggle", { addr: addr, done: done }, {
    project: project,
    key: subKey(project, addr),
    value: done,
    label: addr + (done ? " done" : " reopened"),
  });
}

async function addSub(form) {
  const project = projectId();
  if (!project) return;
  const input = form.elements.title;
  const title = String(input.value || "").trim();
  if (!title) {
    showToast({ text: "Type the subtask first.", tone: "danger" });
    return;
  }
  const id = form.getAttribute("data-id");
  input.value = "";
  input.blur();
  await run("subtask.add", { id: id, title: title }, { project: project, label: "Subtask added to " + id });
}

async function addComment(form) {
  const project = projectId();
  if (!project) return;
  const input = form.elements.text;
  const text = String(input.value || "").trim();
  if (!text) {
    showToast({ text: "Type the comment first.", tone: "danger" });
    return;
  }
  const id = form.getAttribute("data-id");
  const entry = queueComment(id, text);
  input.value = "";
  input.blur();
  const data = await run("comment.add", { on: id, text: text, by: "gui" }, {
    project: project,
    label: "Comment added",
    revert: function () {
      dropComment(entry);
    },
  });
  if (data) settleComment(entry);
}

async function answerQuestion(id, value) {
  const project = projectId();
  if (!project) return;
  await run("question.answer", { id: id, value: value }, { project: project, label: "Answer sent for " + id });
}

async function closeIssue(el) {
  const project = projectId();
  if (!project) return;
  const id = el.getAttribute("data-id");
  await run("issue.close", { id: id }, {
    project: project,
    key: issueKey(project, id),
    value: "closed",
    label: "Issue " + id + " closed",
  });
}

function onClick(event) {
  const el = event.target && event.target.closest ? event.target.closest("[data-side]") : null;
  if (!el) return;
  const kind = el.getAttribute("data-side");
  if (kind === "tab") selectTab(el.getAttribute("data-tab"));
  else if (kind === "back") backToProjects();
  else if (kind === "status") setStatus(el);
  else if (kind === "start") queueTask(el, "task.start");
  else if (kind === "stop") queueTask(el, "task.stop");
  else if (kind === "cap-clear") setCap(el.getAttribute("data-id"), "");
  else if (kind === "answer") answerQuestion(el.getAttribute("data-id"), el.getAttribute("data-value"));
  else if (kind === "close-issue") closeIssue(el);
}

function onChange(event) {
  const el = event.target;
  if (el && el.getAttribute && el.getAttribute("data-side") === "sub") toggleSub(el);
}

function onSubmit(event) {
  const form = event.target;
  if (!form || !form.getAttribute) return;
  event.preventDefault();
  const kind = form.getAttribute("data-side-form");
  if (kind === "cap") setCap(form.getAttribute("data-id"), form.elements.value.value);
  else if (kind === "sub-add") addSub(form);
  else if (kind === "comment") addComment(form);
  else if (kind === "answer") {
    const input = form.elements.value;
    const value = String(input.value || "").trim();
    if (!value) {
      showToast({ text: "Type the answer first.", tone: "danger" });
      return;
    }
    input.value = "";
    input.blur();
    answerQuestion(form.getAttribute("data-id"), value);
  }
}

function isTyping(target) {
  return Boolean(target) && (target.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName));
}

// Esc with an item selected goes back to Projects. It stops here so keys.js does not also close the sheet.
function onEscape(event) {
  if (event.key !== "Escape" || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
  const help = document.getElementById("help");
  if (help && help.open) return;
  if (isTyping(event.target)) return;
  if (!currentRoute().item) return;
  event.stopPropagation();
  backToProjects();
}

// Move focus between project rows, j down and k up. Does nothing while the panel is hidden.
function moveRow(step) {
  const app = document.getElementById("app");
  if (!app || app.getAttribute("data-panel") !== "open") return;
  const rows = Array.from(document.querySelectorAll("#side .p-row"));
  if (!rows.length) return;
  const at = rows.indexOf(document.activeElement);
  let next = at + step;
  if (at < 0) next = step > 0 ? 0 : rows.length - 1;
  next = Math.min(rows.length - 1, Math.max(0, next));
  rows[next].focus();
}

export function initPanel(opts) {
  rerender = opts.render;
  const side = document.getElementById("side");
  if (side) {
    side.addEventListener("click", onClick);
    side.addEventListener("change", onChange);
    side.addEventListener("submit", onSubmit);
  }
  bindKey("j", function () {
    moveRow(1);
  });
  bindKey("k", function () {
    moveRow(-1);
  });
  window.addEventListener("keydown", onEscape, true);
}
