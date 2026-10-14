// Work, Board view (WP31), and the helpers the List and Tree views share: the project's tasks with their live
// status (deferred tasks are not shown), the filter tokens, the status columns and one task card. The card's buttons
// (Start, Done, Hold, Reopen and More) and the keys s d h x change status, and Alt+Up and Alt+Down move a card one
// column. On fine pointers a card can also be dragged to a column, so drag is never the only path. Every write goes
// through cmd.js run(), which gives the toast its Undo. Listeners attach once and act only inside a Work root (.wk).

import { chipHtml, esc, meterHtml } from "../dom.js";
import { fmtTokens } from "../format.js";
import { pendingValue, run } from "../cmd.js";
import { bindKey } from "../keys.js";
import { buildHash } from "../router.js";
import { modelChip, sectionCopyHtml, taskCopyHtml } from "./tasks.js";

export const COLUMNS = [
  { key: "todo", state: "todo", label: "Todo" },
  { key: "doing", state: "partial", label: "Doing" },
  { key: "hold", state: "hold", label: "Hold" },
  { key: "done", state: "done", label: "Done" },
];
export const STATE_LABEL = { todo: "Todo", partial: "Doing", hold: "Hold", done: "Done" };
export const MODELS = ["haiku", "sonnet", "opus", "cursor", "agy"];

export function columnKey(state) {
  for (const col of COLUMNS) {
    if (col.state === state) return col.key;
  }
  return "todo";
}

// Every task that is not deferred, with the status and subtask states a pending write shows until the next snapshot.
export function workTasks(snap, now) {
  const blocked = new Set(snap.blocked || []);
  const names = {};
  for (const phase of snap.phases) names[phase.id] = phase.name;
  const out = [];
  snap.tasks.forEach(function (t, index) {
    if (t.state === "deferred") return;
    const pending = pendingValue("task:" + t.id, snap.fetchedAt, now);
    const subs = t.subs.map(function (s, i) {
      const addr = t.id + "/" + (i + 1);
      const flag = pendingValue("sub:" + addr, snap.fetchedAt, now);
      return { addr: addr, t: s.t, done: flag !== undefined ? flag : s.d };
    });
    out.push({
      id: t.id,
      order: index,
      title: t.title,
      feats: t.feats || [],
      phase: t.phase,
      phaseName: names[t.phase] || t.phase,
      state: pending !== undefined ? pending : t.state,
      model: t.model,
      needsUser: t.needsUser,
      blocked: blocked.has(t.id),
      tokensK: t.tokensK,
      spentK: t.spentK,
      capK: t.capK,
      subs: subs,
      comments: (snap.comments[t.id] || []).length,
      note: t.note,
    });
  });
  return out;
}

// The task shape the copy-reference summary reads (ref.js): the feature ids, and subtasks as {t, d}.
export function copyItem(task) {
  return {
    id: task.id,
    title: task.title,
    state: task.state,
    feats: task.feats,
    subs: task.subs.map(function (s) {
      return { t: s.t, d: s.done };
    }),
  };
}

// Filter tokens: needs, blocked, model:<name>, phase:<id>, status:<todo|doing|hold|done>. Values of one kind match any
// of their listed values; different kinds must all match.
const STATUS_KEYS = COLUMNS.map(function (c) {
  return c.key;
});
const PHASE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$/;

export function parseFilters(text) {
  const F = { tokens: [], needs: false, blocked: false, models: [], phases: [], statuses: [] };
  for (const raw of String(text || "").split(",")) {
    const token = raw.trim();
    if (token === "needs" || token === "blocked") {
      F[token] = true;
      F.tokens.push(token);
    } else if (token.indexOf("model:") === 0 && MODELS.indexOf(token.slice(6)) >= 0) {
      F.models.push(token.slice(6));
      F.tokens.push(token);
    } else if (token.indexOf("phase:") === 0 && PHASE_ID.test(token.slice(6))) {
      F.phases.push(token.slice(6));
      F.tokens.push(token);
    } else if (token.indexOf("status:") === 0 && STATUS_KEYS.indexOf(token.slice(7)) >= 0) {
      F.statuses.push(token.slice(7));
      F.tokens.push(token);
    }
  }
  return F;
}

// The filter text with one token added, or removed when it is already there.
export function toggleToken(text, token) {
  const F = parseFilters(text);
  const list = F.tokens.slice();
  const at = list.indexOf(token);
  if (at >= 0) {
    list.splice(at, 1);
  } else {
    list.push(token);
  }
  return list.join(",");
}

export function matchesFilters(task, F) {
  if (F.needs && !task.needsUser) return false;
  if (F.blocked && !task.blocked) return false;
  if (F.models.length && F.models.indexOf(task.model) < 0) return false;
  if (F.phases.length && F.phases.indexOf(task.phase) < 0) return false;
  if (F.statuses.length && F.statuses.indexOf(columnKey(task.state)) < 0) return false;
  return true;
}

// The link to a task: the same Work view with the item selected, and the same filters.
export function taskHref(ctx, id) {
  return buildHash({ name: "project", id: ctx.pid, section: "work", view: ctx.view, item: id, filters: ctx.filters });
}

function filterChipHtml(token, text, pressed) {
  return '<button type="button" class="wk-chip" aria-pressed="' + (pressed ? "true" : "false") +
    '" data-wk="filter" data-token="' + esc(token) + '" data-focus="wk-chip-' + esc(token) + '">' + esc(text) +
    "</button>";
}

function groupHtml(label, chips) {
  return '<div class="wk-chips" role="group" aria-label="' + esc(label) + '"><span class="wk-chips-label">' +
    esc(label) + "</span>" + chips + "</div>";
}

// The filter chips for Board and List and Tree. Model and phase chips show only the values this project has.
export function filterBarHtml(ctx) {
  const tokens = ctx.F.tokens;
  const pressed = function (token) {
    return tokens.indexOf(token) >= 0;
  };
  const models = MODELS.filter(function (m) {
    return ctx.all.some(function (t) {
      return t.model === m;
    });
  });
  const phases = ctx.snap.phases.filter(function (p) {
    return ctx.all.some(function (t) {
      return t.phase === p.id;
    });
  });
  const flags = filterChipHtml("needs", "Needs you", pressed("needs")) +
    filterChipHtml("blocked", "Blocked", pressed("blocked"));
  const modelChips = models.map(function (m) {
    return filterChipHtml("model:" + m, m, pressed("model:" + m));
  }).join("");
  const phaseChips = phases.map(function (p) {
    return filterChipHtml("phase:" + p.id, p.id + " " + p.name, pressed("phase:" + p.id));
  }).join("");
  const statusChips = COLUMNS.map(function (c) {
    return filterChipHtml("status:" + c.key, c.label, pressed("status:" + c.key));
  }).join("");
  const clear = tokens.length
    ? '<button type="button" class="btn btn-small" data-wk="clear" data-focus="wk-clear">Clear filters</button>'
    : "";
  return '<div class="wk-filters">' + groupHtml("Show", flags) +
    (models.length ? groupHtml("Model", modelChips) : "") +
    (phases.length ? groupHtml("Phase", phaseChips) : "") + groupHtml("Status", statusChips) + clear + "</div>";
}

// The quick actions for a card: the other statuses it can move to, with Reopen for a done task.
function quickTargets(state) {
  const list = [];
  if (state !== "partial") list.push({ state: "partial", label: "Start" });
  if (state === "done") {
    list.push({ state: "todo", label: "Reopen" });
  } else {
    list.push({ state: "done", label: "Done" });
  }
  if (state !== "hold") list.push({ state: "hold", label: "Hold" });
  return list;
}

export function actionsHtml(task) {
  const quick = quickTargets(task.state).map(function (to) {
    return '<button type="button" class="btn btn-small" data-wk="status" data-task="' + esc(task.id) +
      '" data-from="' + esc(task.state) + '" data-to="' + esc(to.state) + '" data-focus="wk-act-' + esc(task.id) +
      "-" + esc(to.state) + '" aria-label="' + esc(to.label + " " + task.id) + '">' + esc(to.label) + "</button>";
  }).join("");
  const more = '<details class="wk-menu"><summary class="btn btn-small" aria-label="' +
    esc("More actions for " + task.id) + '">More</summary><div class="wk-menu-list">' +
    (task.state !== "todo" ? '<button type="button" class="btn btn-small" data-wk="status" data-task="' +
      esc(task.id) + '" data-from="' + esc(task.state) + '" data-to="todo">Move to Todo</button>' : "") +
    '<button type="button" class="btn btn-small" data-wk="run-start" data-task="' + esc(task.id) +
    '">Queue task</button><button type="button" class="btn btn-small" data-wk="run-stop" data-task="' +
    esc(task.id) + '">Stop task</button></div></details>';
  return quick + more;
}

function cardHtml(ctx, task) {
  const copy = taskCopyHtml(ctx.pid, ctx.snap, copyItem(task));
  const flags = [];
  if (task.model) flags.push(modelChip(task.model));
  if (task.needsUser) flags.push(chipHtml("needs you", "warning"));
  if (task.blocked) flags.push(chipHtml("blocked", "danger"));
  const pct = task.capK && task.spentK != null ? Math.min(100, (task.spentK / task.capK) * 100) : null;
  const subsDone = task.subs.filter(function (s) {
    return s.done;
  }).length;
  const meta = [
    '<span class="num">est ' + esc(fmtTokens(task.tokensK)) + "</span>",
    task.spentK != null ? '<span class="num">spent ' + esc(fmtTokens(task.spentK)) + "</span>" : "",
    task.subs.length ? '<span class="num">' + subsDone + "/" + task.subs.length + " subtasks</span>" : "",
    task.comments ? '<span class="num">' + task.comments + (task.comments === 1 ? " comment" : " comments") +
      "</span>" : "",
  ].join("");
  return '<li class="wk-card' + (task.state === "done" ? " is-done" : "") + '" data-wk-task="' + esc(task.id) +
    '" data-state="' + esc(task.state) + '"' +
    (ctx.fine ? ' draggable="true"' : "") + '><div class="wk-card-top"><span class="wk-id num">' + esc(task.id) +
    "</span>" + flags.join("") + '</div><a class="wk-title" href="' + esc(taskHref(ctx, task.id)) +
    '" data-focus="wk-title-' + esc(task.id) + '" title="' + esc(task.title) + '">' + esc(task.title) +
    "</a>" + (pct == null ? "" : meterHtml(pct, "accent")) + '<p class="wk-meta">' + meta + "</p>" +
    '<div class="wk-acts" role="group" aria-label="' + esc("Actions for " + task.id) + '">' + actionsHtml(task) +
    copy + "</div></li>";
}

function columnHtml(ctx, col, items) {
  const on = ctx.col === col.key ? "true" : "false";
  const head = '<h3 class="wk-col-head" id="wk-col-' + col.key + '"><span>' + esc(col.label) +
    '</span><span class="wk-count num">' + items.length + "</span>" +
    sectionCopyHtml(ctx.pid, "board." + col.key, col.label + " column", items.length) + "</h3>";
  const body = items.length
    ? items.map(function (t) {
      return cardHtml(ctx, t);
    }).join("")
    : '<li class="wk-none">No tasks here.</li>';
  return '<section class="wk-col" data-state="' + col.state + '" data-on="' + on +
    '" aria-labelledby="wk-col-' + col.key + '">' + head + '<ul class="wk-cards">' + body + "</ul></section>";
}

// Phone shows one column at a time; this row picks it. On wider screens the tabs are hidden.
function tabsHtml(ctx) {
  const buttons = COLUMNS.map(function (col) {
    const n = ctx.shown.filter(function (t) {
      return columnKey(t.state) === col.key;
    }).length;
    return '<button type="button" class="wk-tab" aria-pressed="' + (ctx.col === col.key ? "true" : "false") +
      '" data-wk="tab" data-col="' + col.key + '" data-focus="wk-tab-' + col.key + '">' + esc(col.label) +
      ' <span class="num">' + n + "</span></button>";
  }).join("");
  return '<div class="seg wk-tabs" role="group" aria-label="Column">' + buttons + "</div>";
}

export function boardView(ctx) {
  const cols = COLUMNS.map(function (col) {
    const items = ctx.shown.filter(function (t) {
      return columnKey(t.state) === col.key;
    });
    return columnHtml(ctx, col, items);
  }).join("");
  const hint = ctx.fine
    ? "Drag a card to another column, or use its buttons. Keys: s Start, d Done, h Hold, x Reopen. " +
      "Alt+Up and Alt+Down move the focused card one column."
    : "Use buttons or keys s/d/h/x.";
  return '<p class="wk-hint">' + esc(hint) + "</p>" + tabsHtml(ctx) + '<div class="wk-board">' + cols + "</div>";
}

// Change a task's status. The card moves at once (cmd.js keeps the value until the snapshot agrees), and the
// focus goes back to the card's title so keyboard users keep their place.
export function setStatus(pid, id, to, from) {
  if (!pid || !id || !STATE_LABEL[to] || to === from) return;
  run("task.status", { id: id, status: to }, {
    project: pid,
    key: "task:" + id,
    value: to,
    label: id + " set to " + STATE_LABEL[to],
  });
  focusTitle(id);
}

export function focusTitle(id) {
  if (typeof window === "undefined") return;
  window.setTimeout(function () {
    const el = document.querySelector('[data-focus="wk-title-' + id + '"]');
    if (el) el.focus({ preventScroll: true });
  }, 0);
}

// The card or list row that holds keyboard focus, when it is inside a Work root.
function focusedRow() {
  const el = typeof document !== "undefined" ? document.activeElement : null;
  const row = el && el.closest ? el.closest("[data-wk-task]") : null;
  return row && row.closest(".wk") ? row : null;
}

function keyStatus(to) {
  return function (event) {
    const row = focusedRow();
    if (!row) return;
    event.preventDefault();
    setStatus(row.closest(".wk").getAttribute("data-project"), row.getAttribute("data-wk-task"), to,
      row.getAttribute("data-state"));
  };
}

function isTypingTarget(target) {
  return Boolean(target) && /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName || "");
}

function onAltArrow(event) {
  if (!event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
  if (isTypingTarget(event.target)) return;
  const card = focusedRow();
  if (!card || !card.classList.contains("wk-card")) return;
  event.preventDefault();
  const at = COLUMNS.findIndex(function (c) {
    return c.state === card.getAttribute("data-state");
  });
  const step = event.key === "ArrowUp" ? -1 : 1;
  const next = COLUMNS[Math.min(COLUMNS.length - 1, Math.max(0, at + step))];
  setStatus(card.closest(".wk").getAttribute("data-project"), card.getAttribute("data-wk-task"), next.state,
    card.getAttribute("data-state"));
}

// Drag between columns. dragging holds the card that is moving; a drop on a column sets its status.
let dragging = null;

function columnOf(target) {
  const col = target && target.closest ? target.closest("section.wk-col") : null;
  return col && col.closest(".wk") ? col : null;
}

function cardOf(target) {
  const card = target && target.closest ? target.closest("li.wk-card") : null;
  return card && card.closest(".wk") ? card : null;
}

function clearDragMarks() {
  for (const el of document.querySelectorAll(".is-over, .is-dragging")) {
    el.classList.remove("is-over", "is-dragging");
  }
}

function onDragStart(event) {
  const card = cardOf(event.target);
  if (!card || !event.dataTransfer) return;
  dragging = {
    pid: card.closest(".wk").getAttribute("data-project"),
    id: card.getAttribute("data-wk-task"),
    from: card.getAttribute("data-state"),
  };
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", dragging.id);
  card.classList.add("is-dragging");
}

function onDragOver(event) {
  const col = columnOf(event.target);
  if (!dragging || !col) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  col.classList.add("is-over");
}

function onDragLeave(event) {
  const col = columnOf(event.target);
  if (!col || col.contains(event.relatedTarget)) return;
  col.classList.remove("is-over");
}

function onDrop(event) {
  const col = columnOf(event.target);
  if (!dragging || !col) return;
  event.preventDefault();
  const moving = dragging;
  dragging = null;
  clearDragMarks();
  setStatus(moving.pid, moving.id, col.getAttribute("data-state"), moving.from);
}

export function finePointer() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" &&
    window.matchMedia("(pointer: fine)").matches;
}

bindKey("s", keyStatus("partial"));
bindKey("d", keyStatus("done"));
bindKey("h", keyStatus("hold"));
bindKey("x", keyStatus("todo"));
if (typeof document !== "undefined") {
  document.addEventListener("keydown", onAltArrow);
  document.addEventListener("dragstart", onDragStart);
  document.addEventListener("dragover", onDragOver);
  document.addEventListener("dragleave", onDragLeave);
  document.addEventListener("drop", onDrop);
  document.addEventListener("dragend", function () {
    dragging = null;
    clearDragMarks();
  });
}
