// Roadmap (WP32). Project scope only. Lanes (the default): one lane per phase with its progress, the estimated and
// the spent tokens, the budget and an Approve button; tasks are compact cards with a status glyph, model, size and a
// Blocked badge when an open blocker names them. Timeline: one bar per phase in plan order, its width proportional
// to the estimated tokens and the spent part filled; there are no calendar dates.
// Reordering always ends in plan.move, which moves a task only within its own phase. The paths are native drag, the
// Up and Down buttons, and Alt+ArrowUp / Alt+ArrowDown on a focused card. The order shown matches `roadmap plan view`,
// which lists the open tasks of each phase in plan order.

import { run } from "../cmd.js";
import { bindKey } from "../keys.js";
import { chipHtml, emptyHtml, esc, meterHtml } from "../dom.js";
import { fmtCount, fmtTokens, MISSING } from "../format.js";
import { pageState } from "./inbox.js";
import { modelChip, STATE_GLYPH, STATE_WORD } from "./tasks.js";
import { showToast } from "./toast.js";

const NO_PLAN = "No plan yet. Ask the lead to run plan import.";
const CROSS_PHASE = "A task moves only within its own phase.";

// The snapshot the last render used. Reorders edit it at once; the next snapshot read replaces it.
let current = null;
let dragId = null;

function phaseOf(task) {
  return task.phase || String(task.id).split(".")[0];
}

function taskById(snap, id) {
  return snap.tasks.find(function (t) {
    return t.id === id;
  }) || null;
}

// The open (not done) task ids of a phase in plan order: the same list `roadmap plan view` prints.
function openIds(snap, pid) {
  return snap.tasks.filter(function (t) {
    return phaseOf(t) === pid && t.state !== "done";
  }).map(function (t) {
    return t.id;
  });
}

function sizeText(k) {
  return typeof k === "number" && Number.isFinite(k) ? "~" + fmtTokens(k) : MISSING;
}

// The estimate of a phase: the tokens of its live (not deferred) tasks, in thousands. Null when none has one.
function estimateK(snap, pid) {
  let sum = 0;
  let any = false;
  for (const t of snap.tasks) {
    if (phaseOf(t) !== pid || t.state === "deferred" || typeof t.tokensK !== "number") continue;
    sum += t.tokensK;
    any = true;
  }
  return any ? sum : null;
}

// Spend and limit of a phase from budget.json. Both are null when the project has no budget for it.
function spendOf(snap, pid) {
  const row = snap.budget && snap.budget.phases ? snap.budget.phases[pid] : null;
  return row ? { spent: row.spent, limit: row.limit } : { spent: null, limit: null };
}

function cardHtml(snap, task, pos, count) {
  const word = STATE_WORD[task.state] || task.state;
  const glyph = STATE_GLYPH[task.state] || "○";
  const blocked = snap.blocked.indexOf(task.id) >= 0;
  const id = esc(task.id);
  const badges = (blocked ? chipHtml("blocked", "danger") : "") +
    (task.needsUser && task.state !== "done" ? chipHtml("needs you", "warning") : "");
  return '<li class="rc is-' + esc(task.state) + (blocked ? " is-blocked" : "") + '" draggable="true" tabindex="0"' +
    ' data-task="' + id + '" data-focus="task:' + id + '" aria-label="' +
    esc(task.id + " " + task.title + ", " + word + (blocked ? ", blocked" : "")) + '">' +
    '<p class="rc-top"><span class="rc-glyph" aria-hidden="true">' + esc(glyph) + '</span>' +
    '<span class="rc-id">' + id + '</span><span class="rc-word">' + esc(word) + "</span></p>" +
    '<p class="rc-title">' + esc(task.title) + "</p>" +
    '<p class="rc-meta">' + (task.model ? modelChip(task.model) : "") +
    '<span class="num">' + esc(sizeText(task.tokensK)) + "</span>" + badges + "</p>" +
    '<p class="rc-move"><button type="button" class="btn btn-small" data-action="plan-move" data-task="' + id +
    '" data-dir="up" aria-label="Move ' + id + ' up"' + (pos === 0 ? " disabled" : "") + ">Up</button>" +
    '<button type="button" class="btn btn-small" data-action="plan-move" data-task="' + id +
    '" data-dir="down" aria-label="Move ' + id + ' down"' + (pos === count - 1 ? " disabled" : "") + ">Down</button>" +
    "</p></li>";
}

// Lanes start open. The phone view stacks them, and each one folds with its header button.
function laneOpen(vm, pid) {
  const saved = vm.prefsOpen["lane:" + pid];
  return typeof saved === "boolean" ? saved : true;
}

function laneHtml(vm, snap, phase) {
  const pid = phase.id;
  const id = esc(pid);
  const open = laneOpen(vm, pid);
  const tasks = snap.tasks.filter(function (t) {
    return phaseOf(t) === pid && t.state !== "done";
  });
  const cards = tasks.map(function (t, i) {
    return cardHtml(snap, t, i, tasks.length);
  }).join("");
  const est = estimateK(snap, pid);
  const money = spendOf(snap, pid);
  const pct = phase.onlyDeferred || phase.progress == null ? null : phase.progress * 100;
  const act = phase.state === "done" ? "" : phase.approved
    ? chipHtml("Approved", "success")
    : '<button type="button" class="btn btn-primary btn-small" data-action="phase-approve" data-phase="' + id +
      '" aria-label="Approve ' + id + " " + esc(phase.name) + '">Approve</button>';
  const budget = money.limit != null ? "budget " + fmtTokens(money.limit) : "no budget";
  const stats = '<div class="lane-stats"><span class="lane-state">' + esc(STATE_WORD[phase.state] || phase.state) +
    "</span>" + '<span class="num">' + esc(fmtCount(phase.done) + "/" + fmtCount(phase.total)) + " done</span>" +
    '<div class="lane-meter">' + meterHtml(pct, phase.state === "done" ? "success" : "accent") + "</div>" +
    '<span class="num">est ' + esc(est == null ? MISSING : sizeText(est)) + "</span>" +
    '<span class="num">spent ' + esc(money.spent == null ? MISSING : fmtTokens(money.spent)) + "</span>" +
    '<span class="num">' + esc(budget) + "</span></div>";
  const body = cards || '<li class="lane-empty">No open tasks in this phase.</li>';
  return '<li class="lane"><div class="lane-head"><button type="button" class="lane-toggle" aria-expanded="' + open +
    '" aria-controls="lane-' + id + '-body" data-action="toggle-item" data-item="lane:' + id +
    '" data-focus="item-lane:' + id + '"><span class="lane-caret" aria-hidden="true">' + (open ? "▾" : "▸") +
    '</span><span class="lane-id">' + id + '</span><span class="lane-name">' + esc(phase.name) + "</span></button>" +
    '<div class="lane-act">' + act + "</div>" + stats + "</div>" +
    '<ol class="lane-cards" id="lane-' + id + '-body" data-lane="' + id + '" aria-label="Tasks in ' + id + '"' +
    (open ? "" : " hidden") + ">" + body + "</ol></li>";
}

function barHtml(snap, phase, max) {
  const pid = phase.id;
  const est = estimateK(snap, pid);
  const spent = spendOf(snap, pid).spent;
  const barPct = est && max ? (est / max) * 100 : 0;
  const spentPct = est && spent != null ? Math.min(100, (spent / est) * 100) : 0;
  const text = (est == null ? "no estimate" : "est " + sizeText(est)) + " · spent " +
    (spent == null ? MISSING : fmtTokens(spent));
  return '<li class="tl-row"><p class="tl-label"><span class="lane-id">' + esc(pid) + '</span><span class="lane-name">' +
    esc(phase.name) + '</span><span class="lane-state">' + esc(STATE_WORD[phase.state] || phase.state) + "</span></p>" +
    '<div class="tl-track" aria-hidden="true"><div class="tl-bar" data-pct="' + barPct + '">' +
    '<div class="tl-spent" data-pct="' + spentPct + '"></div></div></div>' +
    '<p class="tl-text num">' + esc(text) + "</p></li>";
}

function timelineHtml(snap) {
  const max = snap.phases.reduce(function (m, p) {
    return Math.max(m, estimateK(snap, p.id) || 0);
  }, 0);
  return '<ol class="tl" aria-label="Phases by estimated tokens">' + snap.phases.map(function (p) {
    return barHtml(snap, p, max);
  }).join("") + "</ol>" +
    '<p class="page-note">Bar length is the estimate; the filled part is what is spent so far.</p>';
}

function pageHead(vm, snap) {
  const left = snap.tokensLeftK == null ? MISSING : "~" + fmtTokens(snap.tokensLeftK) + " tokens left";
  const id = esc(vm.route.id);
  const timeline = vm.route.view === "timeline";
  return '<div class="page-head"><p class="page-title">Roadmap</p><p class="page-note">' +
    esc(fmtCount(snap.done || 0) + " of " + fmtCount(snap.total || 0) + " items done · " + left) + "</p></div>" +
    '<nav class="seg plan-views" aria-label="Roadmap view">' +
    '<a href="#/p/' + id + '/roadmap"' + (timeline ? "" : ' aria-current="page"') + ">Lanes</a>" +
    '<a href="#/p/' + id + '/roadmap/timeline"' + (timeline ? ' aria-current="page"' : "") + ">Timeline</a></nav>";
}

export function sectionView(vm) {
  if (vm.route.name !== "project") {
    return emptyHtml("The roadmap belongs to one project.", '<a href="#/all/overview">Go to All projects</a>');
  }
  const state = pageState(vm);
  if (state) return state;
  const snap = vm.project.snapshot;
  current = snap;
  if (!snap.phases.length) return emptyHtml(NO_PLAN);
  const body = vm.route.view === "timeline" ? timelineHtml(snap)
    : '<ol class="lanes">' + snap.phases.map(function (p) {
      return laneHtml(vm, snap, p);
    }).join("") + "</ol>";
  return pageHead(vm, snap) + body;
}

// Plan moves. Each one changes the local order at once and sends plan.move; a failure puts the order back.
function move(id, where, ref) {
  const snap = current;
  if (!snap) return;
  const saved = snap.tasks.slice();
  const args = { id: id };
  args[where] = ref;
  run("plan.move", args, {
    label: "Moved " + id,
    apply: function () {
      const list = snap.tasks.slice();
      const from = list.findIndex(function (t) {
        return t.id === id;
      });
      const to = list.findIndex(function (t) {
        return t.id === ref;
      });
      if (from < 0 || to < 0) return;
      const item = list.splice(from, 1)[0];
      const at = list.findIndex(function (t) {
        return t.id === ref;
      });
      list.splice(where === "before" ? at : at + 1, 0, item);
      snap.tasks = list;
    },
    revert: function () {
      snap.tasks = saved;
    },
  });
}

function notice(text) {
  showToast({ text: text, tone: "neutral" });
}

// Up or Down by one open task in the same phase.
function moveBy(id, dir) {
  const snap = current;
  const task = snap && id ? taskById(snap, id) : null;
  if (!task) return;
  const order = openIds(snap, phaseOf(task));
  const at = order.indexOf(id);
  if (at < 0) return;
  if (dir === "up") {
    if (at === 0) return notice(id + " is already first in " + phaseOf(task) + ".");
    move(id, "before", order[at - 1]);
  } else {
    if (at === order.length - 1) return notice(id + " is already last in " + phaseOf(task) + ".");
    move(id, "after", order[at + 1]);
  }
}

function dropOn(id, targetId) {
  const snap = current;
  if (!snap || id === targetId) return;
  const from = taskById(snap, id);
  const to = taskById(snap, targetId);
  if (!from || !to) return;
  if (phaseOf(from) !== phaseOf(to)) return notice(CROSS_PHASE);
  const order = openIds(snap, phaseOf(from));
  move(id, order.indexOf(id) > order.indexOf(targetId) ? "before" : "after", targetId);
}

// A drop on a lane's empty space puts the task at the end of that phase.
function dropIn(id, pid) {
  const snap = current;
  const from = snap ? taskById(snap, id) : null;
  if (!from) return;
  if (phaseOf(from) !== pid) return notice(CROSS_PHASE);
  const order = openIds(snap, pid);
  if (order[order.length - 1] !== id) move(id, "after", order[order.length - 1]);
}

export function pageAction(action, el) {
  if (action === "plan-move") {
    moveBy(el.getAttribute("data-task"), el.getAttribute("data-dir") === "up" ? "up" : "down");
  } else if (action === "phase-approve") {
    const pid = el.getAttribute("data-phase");
    run("phase.approve", { phase: pid }, { label: "Approved " + pid });
  }
}

function cardOf(el) {
  return el && el.closest ? el.closest("[data-task]") : null;
}

function laneOf(el) {
  return el && el.closest ? el.closest("[data-lane]") : null;
}

function onDragStart(event) {
  const card = cardOf(event.target);
  if (!card || !card.closest("#main")) return;
  dragId = card.getAttribute("data-task");
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", dragId);
  }
}

function onDragOver(event) {
  if (!dragId || !(cardOf(event.target) || laneOf(event.target))) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
}

function onDrop(event) {
  if (!dragId) return;
  const id = dragId;
  dragId = null;
  const card = cardOf(event.target);
  const lane = laneOf(event.target);
  if (!card && !lane) return;
  event.preventDefault();
  if (card) {
    dropOn(id, card.getAttribute("data-task"));
  } else {
    dropIn(id, lane.getAttribute("data-lane"));
  }
}

function onAltArrow(dir) {
  const card = cardOf(document.activeElement);
  if (!card || !card.closest("#main")) return;
  moveBy(card.getAttribute("data-task"), dir);
}

// Module setup runs once when the section first loads. The guard keeps the module importable without a page (tests).
if (typeof document !== "undefined") {
  document.addEventListener("dragstart", onDragStart);
  document.addEventListener("dragover", onDragOver);
  document.addEventListener("drop", onDrop);
  document.addEventListener("dragend", function () {
    dragId = null;
  });
  bindKey("Alt+ArrowUp", function () {
    onAltArrow("up");
  });
  bindKey("Alt+ArrowDown", function () {
    onAltArrow("down");
  });
}
