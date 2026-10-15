// Inbox (WP30): the open questions as cards: a vertical list of option buttons (label and description, the
// recommended one first, the default highlighted), an "Other…" text box, a countdown when the question has a timeout,
// and the task it belongs to. Needs-you tasks sit below. Across projects the cards are grouped by project. An answer
// goes through cmd.js run() (op question.answer); the card collapses until the next snapshot.
// Keys: 1 to 6 answer the focused question's option in that position (or the first open card) on the Inbox and
// Overview pages.
// The helpers pageState, collect and inboxPreviewHtml are shared with overview.js and activity.js.

import { bannerHtml, chipHtml, emptyHtml, esc, skeletonHtml } from "../dom.js";
import { fmtDuration } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { bindKey } from "../keys.js";
import { pendingValue, run } from "../cmd.js";
import { currentRoute, projectHash } from "../router.js";

const KEY_MAX = 6;
const REC_SUFFIX = " (recommended)";
const TIME_UP = "Time expired; applying default choice.";
let counting = false;

// A stored option is "Label", "Label: description" or "Label (recommended): description" (services/questions.py).
export function optionParts(stored) {
  const text = String(stored || "");
  const cut = text.indexOf(": ");
  let label = (cut < 0 ? text : text.slice(0, cut)).trim();
  const recommended = label.endsWith(REC_SUFFIX);
  if (recommended) label = label.slice(0, -REC_SUFFIX.length).trim();
  return { label: label, desc: cut < 0 ? "" : text.slice(cut + 2).trim(), recommended: recommended };
}

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

// The Head screen's entry for one ledger id (H1 ...), for the "Open in Head" links.
export function headHash(pid, id) {
  return projectHash(pid, "head") + "?id=" + encodeURIComponent(id);
}

// The answer key of a Head ask: a reply on it shows as "answered" until the next snapshot.
export function headAskKey(pid, id) {
  return "headask:" + pid + ":" + id;
}

// The Head ledger rows with status needs-you (snap.head.rows), across the scopes, in snapshot order.
export function headAsks(scopes) {
  const asks = [];
  for (const s of scopes) {
    const rows = s.snap.head && Array.isArray(s.snap.head.rows) ? s.snap.head.rows : [];
    for (const row of rows) {
      if (row && row.status === "needs-you") asks.push({ pid: s.id, pname: s.name, snap: s.snap, row: row });
    }
  }
  return asks;
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
  return { questions: questions, needs: needs, asks: headAsks(scopes) };
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

// One option button: its key (1 to 6), label, description, and badges. The recommended option is listed first.
function optionHtml(pid, q, part, index) {
  const isDefault = part.label === q.def;
  const key = index < KEY_MAX ? '<span class="qc-key" aria-hidden="true">' + (index + 1) + "</span> " : "";
  const desc = part.desc ? ' <span class="qc-foot">' + esc(part.desc) + "</span>" : "";
  const rec = part.recommended ? ' <span class="qc-def">recommended</span>' : "";
  const dflt = isDefault ? ' <span class="qc-def">default</span>' : "";
  return '<button type="button" class="btn qc-opt' + (isDefault ? " btn-primary is-default" : "") +
    '" data-action="inbox-answer" data-project="' + esc(pid) + '" data-qid="' + esc(q.id) +
    '" data-value="' + esc(part.label) + '" aria-label="' + esc("Choose " + part.label + " for " + q.id) +
    '" data-focus="ans-' + esc(pid) + "-" + esc(q.id) + "-" + index + '">' +
    key + esc(part.label) + rec + dflt + desc + "</button>";
}

// The options as a vertical list (one button per row), then the free-text box that every question has.
function answerHtml(pid, q) {
  const parts = q.opts.map(optionParts);
  const order = parts.map(function (p, i) {
    return i;
  }).sort(function (a, b) {
    return (parts[b].recommended ? 1 : 0) - (parts[a].recommended ? 1 : 0) || a - b;
  });
  const buttons = order.map(function (i, n) {
    return optionHtml(pid, q, parts[i], n);
  }).join("");
  const list = buttons
    ? '<div class="nz-list" role="group" aria-label="' + esc("Answers for " + q.id) + '">' + buttons + "</div>"
    : "";
  return list + '<form class="nz-row" data-form="inbox-question-answer" data-project="' + esc(pid) +
    '" data-qid="' + esc(q.id) + '" aria-label="' + esc("Other answer for " + q.id) + '">' +
    '<label><span class="qc-id">Other…</span> <input name="value" required placeholder="Type an answer"></label> ' +
    '<button type="submit" class="btn">Send</button></form>';
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
  const task = q.task ? ' <a class="qc-task" href="' + esc(itemHash(pid, q.task)) + '" aria-label="' +
    esc("View task " + q.task) + '">' + esc(q.task) + "</a>" : "";
  const blocks = q.block ? chipHtml("Blocks work", "warning") : "";
  const copy = copyButton("question", q.id, q.id + " " + q.text, { project: pid, sum: refSummary("question", q) });
  const options = answerHtml(pid, Object.assign({}, q, { opts: Array.isArray(q.opts) ? q.opts : [] }));
  let timer = "";
  if (q.askedMs != null && q.timeoutS != null) {
    const deadline = q.askedMs + q.timeoutS * 1000;
    const word = q.def ? "Defaults to " + q.def + " in " : "Times out in ";
    timer = '<p class="qc-foot"><span class="qc-timer" data-deadline-ms="' + esc(deadline) + '" data-word="' +
      esc(word) + '">' + esc(countdownText(deadline, word, now)) + "</span></p>";
  }
  return '<article class="qc' + (q.block ? " is-blocking" : "") + '" data-pid="' + esc(pid) + '" data-qid="' +
    esc(q.id) + '"><header class="qc-head"><span class="qc-id">' + esc(q.id) + "</span>" +
    (showProject ? " " + chipHtml(entry.pname, "neutral") : "") + task + " " + blocks + copy + "</header>" +
    '<h3 class="qc-text">' + esc(q.text) + "</h3>" + options + timer + "</article>";
}

function needRowHtml(entry, showProject) {
  return '<li class="nz-row"><span class="nz-kind">Needs you</span> <a href="' +
    esc(itemHash(entry.pid, entry.item.id)) + '" aria-label="' + esc("View task " + entry.item.id) + '">' +
    esc(entry.item.id) + "</a> " + esc(entry.item.title) +
    (showProject ? " " + chipHtml(entry.pname, "neutral") : "") + "</li>";
}

// One Head ask: its kind, summary, age and the head's note, then the reply form (head.set note) and the Head link.
// A reply made on this page shows one line until the next snapshot drops it.
export function headAskCardHtml(entry, now, showProject) {
  const pid = entry.pid;
  const row = entry.row;
  const id = String(row.id);
  const answered = pendingValue(headAskKey(pid, id), entry.snap.fetchedAt, now);
  if (answered !== undefined) {
    return '<article class="qc is-answered" data-pid="' + esc(pid) + '" data-id="' + esc(id) + '">' +
      '<p class="qc-line">' + esc(id) + " answered: <strong>" + esc(answered) + "</strong></p></article>";
  }
  const kind = row.kind ? chipHtml(row.kind, "neutral") : "";
  const age = typeof row.age === "number" ? '<span class="qc-id">Waiting ' + esc(fmtDuration(row.age * 60)) +
    "</span>" : "";
  const note = typeof row.note === "string" && row.note.trim() ? row.note : "The head needs your answer.";
  return '<article class="qc" data-pid="' + esc(pid) + '" data-id="' + esc(id) + '">' +
    '<header class="qc-head"><span class="qc-id">' + esc(id) + "</span> " + kind +
    (showProject ? " " + chipHtml(entry.pname, "neutral") : "") + " " + age + "</header>" +
    '<h3 class="qc-text">' + esc(row.sum || "") + "</h3>" +
    '<p class="qc-foot">' + esc(note) + "</p>" +
    '<form data-op="head.set" data-project="' + esc(pid) + '" data-id="' + esc(id) +
    '" data-form="inbox-head-ask" aria-label="' + esc("Answer " + id) + '">' +
    '<label><span class="qc-id">Your answer</span> <input name="note" required placeholder="Type an answer"></label> ' +
    '<button type="submit" class="btn">Answer</button></form>' +
    '<p class="qc-foot"><a href="' + esc(headHash(pid, id)) + '" aria-label="' + esc("Open " + id + " in Head") +
    '">Open in Head</a></p></article>';
}

// The full Inbox page: question cards (grouped by project in All projects), then the Head asks, then the needs-you
// tasks.
export function inboxBody(vm) {
  const now = Date.now();
  const scopes = scopeSnapshots(vm);
  const showProject = vm.route.name !== "project";
  const c = collect(scopes);
  if (!c.questions.length && !c.needs.length && !c.asks.length) return emptyHtml("Inbox empty. No actions pending.");
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
  if (c.asks.length) {
    html += '<section class="ov-card" aria-labelledby="inbox-asks-h"><h2 class="ov-h" id="inbox-asks-h">' +
      "Head asks</h2>" + c.asks.map(function (e) {
        return headAskCardHtml(e, now, showProject);
      }).join("") + "</section>";
  }
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
    rows.push('<li class="nz-row"><span class="nz-kind">Question</span> <a href="' + esc(inboxHash(vm)) +
      '" aria-label="' + esc("View question " + e.q.id) + '">' +
      esc(e.q.id) + "</a> " + esc(e.q.text) + (showProject ? " " + chipHtml(e.pname, "neutral") : "") + "</li>");
  }
  for (const e of c.asks) {
    rows.push('<li class="nz-row"><span class="nz-kind">Head ask</span> <a href="' + esc(headHash(e.pid, e.row.id)) +
      '" aria-label="' + esc("Open " + e.row.id + " in Head") + '">' + esc(e.row.id) + "</a> " +
      esc(e.row.sum || "") + (showProject ? " " + chipHtml(e.pname, "neutral") : "") + "</li>");
  }
  for (const e of c.needs) rows.push(needRowHtml(e, showProject));
  if (!rows.length) return '<p class="placeholder">Inbox empty. No actions pending.</p>';
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

// A reply on a Head ask: the form's note goes through cmd.js run() as head.set (the same op as the Head screen's
// status and note writes), with no status change, so the head still decides what the ask becomes.
function onAskSubmit(event) {
  const form = event.target;
  if (form && form.getAttribute && form.getAttribute("data-form") === "inbox-question-answer") {
    onQuestionTextSubmit(event, form);
    return;
  }
  if (!form || !form.getAttribute || form.getAttribute("data-form") !== "inbox-head-ask") return;
  event.preventDefault();
  const pid = form.getAttribute("data-project");
  const id = form.getAttribute("data-id");
  const field = form.elements.namedItem("note");
  const value = field ? String(field.value || "").trim() : "";
  if (!value) return;
  run("head.set", { id: id, note: value }, {
    project: pid,
    key: headAskKey(pid, id),
    value: value,
    label: id + " answered: " + value,
  });
}

if (typeof document !== "undefined") document.addEventListener("submit", onAskSubmit);

// The "Other…" box of a question card: free text goes through the same question.answer op as an option button.
function onQuestionTextSubmit(event, form) {
  event.preventDefault();
  const pid = form.getAttribute("data-project");
  const qid = form.getAttribute("data-qid");
  const field = form.elements.namedItem("value");
  const value = field ? String(field.value || "").trim() : "";
  if (!value) return;
  sendAnswer(pid, qid, value);
}

function onAnswerPage() {
  const section = currentRoute().section;
  return section === "inbox" || section === "overview";
}

function sendAnswer(pid, qid, value) {
  run("question.answer", { id: qid, value: value }, {
    project: pid,
    key: questionKey(pid, qid),
    value: value,
    label: qid + " answered: " + value,
  });
}

function answerButton(el) {
  sendAnswer(el.getAttribute("data-project"), el.getAttribute("data-qid"), el.getAttribute("data-value"));
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

// The keys 1 to 6 answer the focused card's option in that position (the list order, recommended first).
function onDigit(index) {
  return function () {
    if (!onAnswerPage()) return;
    const card = focusedCard();
    const button = card ? card.querySelectorAll(".qc-opt")[index] : null;
    if (button) answerButton(button);
  };
}

for (let n = 1; n <= KEY_MAX; n++) bindKey(String(n), onDigit(n - 1));

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  watchCountdowns();
  const found = collect(scopeSnapshots(vm));
  const open = found.questions.length + found.asks.length;
  const sectionCopy = copyButton("section", "inbox.questions", "open questions",
    { project: vm.route.id, sum: refSummary("section", { count: open }) });
  return '<div class="page-head"><h2 class="page-title">Inbox</h2>' + sectionCopy + "</div>" + inboxBody(vm);
}
