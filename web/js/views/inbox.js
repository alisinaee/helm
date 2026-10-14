// Inbox (WP30): the open questions as cards, one button per option (the default is highlighted), a countdown when the
// question has a timeout, and the task it belongs to. Needs-you tasks sit below. Across projects the cards are grouped
// by project. An answer goes through cmd.js run() (op question.answer); the card collapses until the next snapshot.
// Keys: "a", then 1 to 4, answers the focused question (or the first open one) on the Inbox and Overview pages.
// The helpers pageState, collect and inboxPreviewHtml are shared with overview.js and activity.js.

import { bannerHtml, chipHtml, emptyHtml, esc, skeletonHtml } from "../dom.js";
import { fmtDuration } from "../format.js";
import { bindKey } from "../keys.js";
import { pendingValue, run } from "../cmd.js";
import { currentRoute, projectHash } from "../router.js";

const ARM_MS = 2000;
const KEY_MAX = 4;
const TIME_UP = "Time is up. The default applies shortly.";
let armedUntil = 0;
let counting = false;

export function questionKey(pid, qid) {
  return "question:" + pid + ":" + qid;
}

// The snapshots in view as {id, name, snap}: the project's one, or one per registered project in All projects.
export function scopeSnapshots(vm) {
  return (vm.snapshotList || []).map(function (snap) {
    return { id: snap.id, name: snap.title, snap: snap };
  });
}

// The hash of a task in the Work section, for links from questions, blockers and needs-you rows.
export function itemHash(pid, taskId) {
  return projectHash(pid, "work") + "/i/" + encodeURIComponent(taskId);
}

// The Inbox link for the scope in view: the project's Inbox, or All projects' Inbox.
export function inboxHash(vm) {
  return vm.route.name === "project" ? projectHash(vm.route.id, "inbox") : "#/all/inbox";
}

// The page-level state shared by Overview, Inbox and Activity: a banner or an empty state, or null when the page has
// content to show.
export function pageState(vm) {
  if (vm.route.name === "project") {
    const p = vm.project;
    if (p.notFound) return emptyHtml("No project with that id.", '<a href="#/all/overview">Go to All projects</a>');
    if (!p.snapshot) {
      if (p.error) return bannerHtml("danger", "Could not load this project. Retrying.", p.error.message);
      return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90"]) + "</div>";
    }
    return null;
  }
  if (vm.projectsError && !vm.projects) {
    return bannerHtml("danger", "Could not load projects. Retrying.", vm.projectsError.message);
  }
  if (!vm.projects || vm.home.loading) return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90"]) + "</div>";
  if (!vm.projects.length) {
    return emptyHtml("No projects yet.", "Run <code class=\"code\">roadmap project add &lt;path&gt;</code>.");
  }
  if (!(vm.snapshotList || []).length) return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90"]) + "</div>";
  return null;
}

// Open questions and needs-you tasks across the scopes, in snapshot order.
export function collect(scopes) {
  const questions = [];
  const needs = [];
  for (const s of scopes) {
    for (const q of s.snap.questions) questions.push({ pid: s.id, pname: s.name, snap: s.snap, q: q });
    for (const item of s.snap.needsYou) {
      if (item.kind === "task") needs.push({ pid: s.id, pname: s.name, item: item });
    }
  }
  return { questions: questions, needs: needs };
}

// The countdown line for a deadline. The text is filled in by tickCountdowns, so a poll does not re-render it.
function countdownText(deadlineMs, word, now) {
  const left = (deadlineMs - now) / 1000;
  return left <= 0 ? TIME_UP : word + fmtDuration(left);
}

export function tickCountdowns(root, now) {
  for (const el of root.querySelectorAll("[data-deadline-ms]")) {
    const text = countdownText(Number(el.getAttribute("data-deadline-ms")), el.getAttribute("data-word") || "", now);
    if (el.textContent !== text) el.textContent = text;
  }
}

// One ticker per page, and a redraw hook, so the countdown text is written after every render.
export function watchCountdowns() {
  if (counting || typeof document === "undefined") return;
  counting = true;
  window.setInterval(function () {
    tickCountdowns(document, Date.now());
  }, 1000);
  const main = document.getElementById("main");
  if (main && typeof MutationObserver === "function") {
    const observer = new MutationObserver(function () {
      tickCountdowns(main, Date.now());
    });
    observer.observe(main, { childList: true, subtree: true });
  }
}

function optionHtml(pid, q, opt, index) {
  const isDefault = opt === q.def;
  const key = index < KEY_MAX ? '<span class="qc-key" aria-hidden="true">' + (index + 1) + "</span> " : "";
  return '<button type="button" class="btn qc-opt' + (isDefault ? " btn-primary is-default" : "") +
    '" data-action="inbox-answer" data-project="' + esc(pid) + '" data-qid="' + esc(q.id) +
    '" data-value="' + esc(opt) + '" data-focus="ans-' + esc(pid) + "-" + esc(q.id) + "-" + index + '">' +
    key + esc(opt) + (isDefault ? ' <span class="qc-def">default</span>' : "") + "</button>";
}

// One question card. A card answered in this page shows one line until the next snapshot drops it.
export function questionCardHtml(entry, now, showProject) {
  const pid = entry.pid;
  const q = entry.q;
  const answered = pendingValue(questionKey(pid, q.id), entry.snap.fetchedAt, now);
  if (answered !== undefined) {
    return '<article class="qc is-answered" data-pid="' + esc(pid) + '" data-qid="' + esc(q.id) + '">' +
      '<p class="qc-line">' + esc(q.id) + " answered: <strong>" + esc(answered) + "</strong></p></article>";
  }
  const task = q.task ? ' <a class="qc-task" href="' + esc(itemHash(pid, q.task)) + '">' + esc(q.task) + "</a>" : "";
  const blocks = q.block ? chipHtml("Blocks work", "warning") : "";
  const options = q.opts.length
    ? '<div class="qc-opts row-grid" role="group" aria-label="Answers for ' + esc(q.id) + '">' +
      q.opts.map(function (opt, i) {
        return optionHtml(pid, q, opt, i);
      }).join("") + "</div>"
    : '<p class="qc-foot">This question has no options. Answer it in the terminal.</p>';
  let timer = "";
  if (q.askedMs != null && q.timeoutS != null) {
    const deadline = q.askedMs + q.timeoutS * 1000;
    const word = q.def ? "Defaults to " + q.def + " in " : "Times out in ";
    timer = '<p class="qc-foot"><span class="qc-timer" data-deadline-ms="' + esc(deadline) + '" data-word="' +
      esc(word) + '">' + esc(countdownText(deadline, word, now)) + "</span></p>";
  }
  return '<article class="qc' + (q.block ? " is-blocking" : "") + '" data-pid="' + esc(pid) + '" data-qid="' +
    esc(q.id) + '"><header class="qc-head"><span class="qc-id">' + esc(q.id) + "</span>" +
    (showProject ? " " + chipHtml(entry.pname, "neutral") : "") + task + " " + blocks + "</header>" +
    '<h3 class="qc-text">' + esc(q.text) + "</h3>" + options + timer + "</article>";
}

function needRowHtml(entry, showProject) {
  return '<li class="nz-row"><span class="nz-kind">Needs you</span> <a href="' +
    esc(itemHash(entry.pid, entry.item.id)) + '">' + esc(entry.item.id) + "</a> " + esc(entry.item.title) +
    (showProject ? " " + chipHtml(entry.pname, "neutral") : "") + "</li>";
}

// The full Inbox page: question cards (grouped by project in All projects), then the needs-you tasks.
export function inboxBody(vm) {
  const now = Date.now();
  const scopes = scopeSnapshots(vm);
  const showProject = vm.route.name !== "project";
  const c = collect(scopes);
  if (!c.questions.length && !c.needs.length) return emptyHtml("All quiet. Nothing needs you.");
  let html = "";
  for (const s of scopes) {
    const cards = c.questions.filter(function (e) {
      return e.pid === s.id;
    });
    if (!cards.length) continue;
    const head = showProject ? '<h3 class="grp-h"><a href="' + esc(projectHash(s.id, "inbox")) + '">' +
      esc(s.name) + "</a></h3>" : "";
    html += '<div class="grp">' + head + cards.map(function (e) {
      return questionCardHtml(e, now, false);
    }).join("") + "</div>";
  }
  if (!c.questions.length) html += '<p class="placeholder">No open questions.</p>';
  if (c.needs.length) {
    html += '<section class="ov-card" aria-labelledby="inbox-needs-h"><h2 class="ov-h" id="inbox-needs-h">' +
      "Needs you</h2><ul class=\"nz-list\">" + c.needs.map(function (e) {
        return needRowHtml(e, showProject);
      }).join("") + "</ul></section>";
  }
  return html;
}

// The Overview preview: up to limit rows, questions first, with no answer buttons. Links go to the Inbox.
export function inboxPreviewHtml(vm, limit) {
  const scopes = scopeSnapshots(vm);
  const showProject = vm.route.name !== "project";
  const c = collect(scopes);
  const rows = [];
  for (const e of c.questions) {
    rows.push('<li class="nz-row"><span class="nz-kind">Question</span> <a href="' + esc(inboxHash(vm)) + '">' +
      esc(e.q.id) + "</a> " + esc(e.q.text) + (showProject ? " " + chipHtml(e.pname, "neutral") : "") + "</li>");
  }
  for (const e of c.needs) rows.push(needRowHtml(e, showProject));
  if (!rows.length) return '<p class="placeholder">All quiet. Nothing needs you.</p>';
  const more = rows.length > limit
    ? '<p class="ov-more"><a href="' + esc(inboxHash(vm)) + '">Open Inbox (' + (rows.length - limit) +
      " more)</a></p>"
    : "";
  return '<ul class="nz-list">' + rows.slice(0, limit).join("") + "</ul>" + more;
}

// The card that the "1" to "4" keys answer: the focused one, else the first open card on the page.
function focusedCard() {
  const active = document.activeElement;
  const near = active && active.closest ? active.closest(".qc[data-qid]:not(.is-answered)") : null;
  return near || document.querySelector("#main .qc[data-qid]:not(.is-answered)");
}

function onAnswerPage() {
  const section = currentRoute().section;
  return section === "inbox" || section === "overview";
}

function answerButton(el) {
  const pid = el.getAttribute("data-project");
  const qid = el.getAttribute("data-qid");
  const value = el.getAttribute("data-value");
  run("question.answer", { id: qid, value: value }, {
    project: pid,
    key: questionKey(pid, qid),
    value: value,
    label: qid + " answered: " + value,
  });
}

// Click entry point for the page's buttons (app.js sends these data-action values here): an answer, an Undo on an
// activity line, and the one-hour Override from the limit banner.
export function pageAction(action, el) {
  const pid = el.getAttribute("data-project");
  if (action === "inbox-answer") {
    answerButton(el);
  } else if (action === "undo-line") {
    const label = el.closest(".act-row") ? el.closest(".act-row").querySelector(".act-sum") : null;
    run("undo", { activity: el.getAttribute("data-activity") }, {
      project: pid,
      label: "Undone: " + (label ? label.textContent : "change"),
    });
  } else if (action === "override") {
    run("control.override", { hours: 1 }, { project: pid, label: "Override set for 1 hour" });
  }
}

function onArm() {
  if (onAnswerPage()) armedUntil = Date.now() + ARM_MS;
}

function onDigit(index) {
  return function () {
    if (Date.now() > armedUntil || !onAnswerPage()) return;
    armedUntil = 0;
    const card = focusedCard();
    const button = card ? card.querySelectorAll(".qc-opt")[index] : null;
    if (button) answerButton(button);
  };
}

bindKey("a", onArm);
bindKey("1", onDigit(0));
bindKey("2", onDigit(1));
bindKey("3", onDigit(2));
bindKey("4", onDigit(3));

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  watchCountdowns();
  return '<div class="page-head"><h2 class="page-title">Inbox</h2></div>' + inboxBody(vm);
}
