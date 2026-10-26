// Work items (R9.20, R9.23 M8/M9; docs/WORK-MODEL.md section 3). The Work board, List and Tree show the snapshot's
// work[] rows only (never an agent task as a card), the P column chip, and the grouping of agents and jobs under their
// Work item. Row fields: id, title, kind, status, prio ("P0".."P3"), badges, progress {done,total}. Optional fields
// the snapshot may add: owner, outcome and tasks [{id,state,model,job}] (the agent tasks of the item). Every value is
// escaped; the Accept button runs the work.accept op through cmd.js.

import { chipHtml, esc, meterHtml } from "../dom.js";
import { run, runBatch } from "../cmd.js";
import { buildHash } from "../router.js";

export const WI_COLUMNS = [
  { key: "backlog", status: "Backlog", label: "Backlog" },
  { key: "todo", status: "Todo", label: "Todo" },
  { key: "doing", status: "Doing", label: "Doing" },
  { key: "review", status: "Review", label: "Review" },
  { key: "done", status: "Done", label: "Done" },
  { key: "wontfix", status: "Won't do", label: "Won't do" },
];
const ISSUE_KINDS = ["bug", "risk", "question", "blocker"];
let addOpen = false;
let addError = "";
let issuesOnly = false;
let addKind = "task";
let dragId = "";
let current = [];
const PRIO = /^P[0-3]$/;
const NO_ITEM = "No Work item";

let asksOf = {};
let pidOf = "";

export function workItems(snap) {
  asksOf = snap && snap.askOf && typeof snap.askOf === "object" ? snap.askOf : {};
  pidOf = snap && snap.id ? String(snap.id) : "";
  current = snap && Array.isArray(snap.work) ? snap.work.filter(function (w) {
    return w && w.id;
  }) : null;
  return current;
}

function colOf(w) {
  const hit = WI_COLUMNS.filter(function (c) {
    return c.status === w.status;
  })[0];
  return hit ? hit.key : "todo";
}

// P0 first; inside one prio the snapshot order is the rank (work.move swaps neighbours).
function byPrio(a, b) {
  const pa = PRIO.test(a.prio) ? a.prio : "P9";
  const pb = PRIO.test(b.prio) ? b.prio : "P9";
  return pa < pb ? -1 : pa > pb ? 1 : 0;
}

// The P chip in its fixed narrow track; blank (an empty cell) when the prio is not P0-P3.
export function prioChip(prio) {
  return PRIO.test(prio) ? '<span class="chip wi-p wi-' + prio.toLowerCase() + '">' + prio + "</span>" : "";
}

// The prio of the Work item an ask row is bound to (a work:W3 link), "" when none.
export function prioOfRow(snap, row) {
  const items = workItems(snap);
  if (!items || !row || !Array.isArray(row.links)) return "";
  for (const link of row.links) {
    const ref = String(link && typeof link === "object" ? link.ref : link || "");
    if (ref.indexOf("work:") !== 0) continue;
    const w = items.filter(function (x) {
      return x.id === ref.slice(5);
    })[0];
    if (w) return w.prio || "";
  }
  return "";
}

function agentsHref(pid, task) {
  return buildHash({ name: "project", id: pid, section: "agents", item: task || "" });
}

function progressHtml(w) {
  const p = w.progress || {};
  const total = Number(p.total) || 0;
  const done = Number(p.done) || 0;
  return '<span class="wi-prog">' + meterHtml(total ? (done / total) * 100 : 0, done === total && total ? "success" :
    "accent") + '<span class="num wi-n">' + done + "/" + total + "</span></span>";
}

function badgesHtml(w) {
  return (w.badges || []).map(function (b) {
    return chipHtml(b, b === "running" ? "success" : "warning");
  }).join("");
}

function ownerText(w) {
  return w.owner ? esc(w.owner) : "owner unknown";
}

function acceptHtml(pid, w) {
  return w.status === "Review" ? '<button type="button" class="btn btn-small" data-wi="accept" data-work="' +
    esc(w.id) + '" data-focus="wi-accept-' + esc(w.id) + '">Accept</button>' : "";
}

// The read-only agent task rows of a Work item: status, model, job; each links to Agents.
function tasksHtml(pid, w) {
  const rows = Array.isArray(w.tasks) ? w.tasks : [];
  if (!rows.length) return '<p class="wk-meta">Agent tasks: unknown (' + esc((w.progress && w.progress.total) || 0) +
    " linked).</p>";
  return '<ul class="wi-tasks">' + rows.map(function (t) {
    return '<li class="wi-task"><a href="' + esc(agentsHref(pid, t.id)) + '">' + esc(t.id) + "</a>" +
      "<span>" + esc(t.state || "unknown") + "</span><span>" + esc(t.model || "unknown") + "</span><span>" +
      esc(t.job || "no job") + "</span></li>";
  }).join("") + "</ul>";
}

// ask:H12 chips of the head asks bound to the tasks of a Work item; each opens that ask in Head.
function asksHtml(pid, w) {
  const ids = [];
  (Array.isArray(w.tasks) ? w.tasks : []).forEach(function (t) {
    (asksOf[String(t.id)] || []).forEach(function (id) {
      if (ids.indexOf(id) < 0) ids.push(id);
    });
  });
  return ids.length ? '<p class="wi-asks">' + ids.map(function (id) {
    return '<a class="chip chip-neutral" href="#/p/' + esc(pid || pidOf) + "/head?id=" + encodeURIComponent(id) +
      '" title="Open ' + esc(id) + ' in Head">ask:' + esc(id) + "</a>";
  }).join(" ") + "</p>" : "";
}

function drawerHtml(pid, w) {
  return '<details class="wi-d"><summary class="wk-title" data-focus="wi-title-' + esc(w.id) + '">' + esc(w.title) +
    '</summary><p class="wi-outcome">' + (w.outcome ? esc(w.outcome) : "Outcome unknown.") + "</p>" +
    tasksHtml(pid, w) + asksHtml(pid, w) + "</details>";
}

function kindBadge(w) {
  if (w.kind !== "issue") return "";
  const sub = ISSUE_KINDS.indexOf(w.issue) >= 0 ? w.issue : "issue";
  const sev = Number(w.sev) > 0 ? " S" + Number(w.sev) : "";
  return '<span class="chip wi-kind wi-kind-' + sub + '" title="Issue">' + esc(sub + sev) + "</span>";
}

function canDrag() {
  return typeof matchMedia === "function" && matchMedia("(pointer:fine)").matches;
}

// The op that moves w into column `to`, or null when that move is not allowed. Todo, Doing and Review are derived,
// so the only drops are the person's intent states, Todo meaning "clear Backlog / Won't do", and reopen into Doing.
function moveFor(w, to) {
  const st = w.status;
  const open = st !== "Review" && st !== "Done";
  if (to === colOf(w)) return null;
  if ((to === "backlog" || to === "wontfix") && open) {
    return { op: "work.set", args: { id: w.id, state: to }, label: w.id + (to === "backlog" ? " to Backlog" :
      " set to Won't do") };
  }
  if (to === "todo" && (st === "Backlog" || st === "Won't do")) {
    return { op: "work.set", args: { id: w.id, state: "todo" }, label: w.id + " back to Todo" };
  }
  if (to === "doing" && !open) return { op: "work.reopen", args: { id: w.id }, label: w.id + " reopened" };
  return null;
}

function menuHtml(w) {
  const items = WI_COLUMNS.filter(function (c) {
    return moveFor(w, c.key);
  }).map(function (c) {
    return '<button type="button" data-wi="move" data-work="' + esc(w.id) + '" data-to="' + c.key + '">' +
      (c.key === "doing" ? "Reopen" : "Move to " + esc(c.label)) + "</button>";
  });
  if (w.status === "Review") {
    items.unshift('<button type="button" data-wi="accept" data-work="' + esc(w.id) + '">Accept</button>');
  }
  ["up", "down"].forEach(function (d) {
    items.push('<button type="button" data-wi="rank" data-work="' + esc(w.id) + '" data-dir="' + d + '">Move ' + d +
      "</button>");
  });
  return '<details class="wk-menu wi-menu"><summary aria-label="Actions for ' + esc(w.id) + '">...</summary>' +
    '<div class="wk-menu-list">' + items.join("") + "</div></details>";
}

function cardHtml(pid, w) {
  return '<li class="wk-card wi-card' + (w.status === "Done" ? " is-done" : "") + '" data-work-item="' + esc(w.id) +
    '" tabindex="0" data-focus="wi-card-' + esc(w.id) + '"' + (canDrag() ? ' draggable="true"' : "") +
    '><div class="wk-card-top"><span class="wk-id">' + esc(w.id) + "</span>" + prioChip(w.prio) + kindBadge(w) +
    badgesHtml(w) + menuHtml(w) + "</div>" + drawerHtml(pid, w) + progressHtml(w) + '<div class="wk-meta"><span>' +
    ownerText(w) + "</span>" + acceptHtml(pid, w) + "</div></li>";
}

function tabsHtml(ctx, items) {
  return '<div class="seg wk-tabs" role="group" aria-label="Column">' + WI_COLUMNS.map(function (c) {
    const n = items.filter(function (w) {
      return colOf(w) === c.key;
    }).length;
    return '<button type="button" class="wk-tab" aria-pressed="' + (ctx.col === c.key ? "true" : "false") +
      '" data-wk="tab" data-col="' + c.key + '" aria-controls="wk-col-' + c.key + '" data-focus="wk-tab-' + c.key +
      '">' + esc(c.label) + ' <span class="num">' + n + "</span></button>";
  }).join("") + "</div>";
}

function optionsHtml(values, pick) {
  return values.map(function (v) {
    return '<option value="' + esc(v[0]) + '"' + (v[0] === pick ? " selected" : "") + ">" + esc(v[1]) + "</option>";
  }).join("");
}

// The quick add form (R7.24): title, kind (+ issue kind and severity), prio and outcome; server wording errors inline.
function addFormHtml() {
  if (!addOpen) return "";
  const prios = ["P0", "P1", "P2", "P3"].map(function (p) {
    return [p, p];
  });
  return '<form class="wi-add" data-wi="add-form" data-kind="' + (addKind === "issue" ? "issue" : "task") +
    '" novalidate><label>Title<input name="title" maxlength="60" required autocomplete="off" ' +
    'data-focus="wi-add-title" placeholder="What should be done"></label>' +
    '<label>Kind<select name="kind" data-wi="add-kind">' +
    optionsHtml([["task", "Task"], ["issue", "Issue"]], addKind) + '</select></label><label class="wi-iss">Issue' +
    '<select name="issue">' + optionsHtml(ISSUE_KINDS.map(function (k) {
      return [k, k];
    }), "bug") + '</select></label><label class="wi-iss">Severity<select name="sev">' +
    optionsHtml([["1", "S1"], ["2", "S2"], ["3", "S3"]], "2") + '</select></label><label>Prio<select name="prio">' +
    optionsHtml(prios, "P2") + '</select></label><label class="wi-out">Outcome (optional)<input name="outcome" ' +
    'maxlength="240" autocomplete="off"></label><span class="wi-add-acts"><button type="submit" class="btn ' +
    'btn-small">Add</button><button type="button" class="btn btn-small" data-wi="add-cancel">Cancel</button></span>' +
    (addError ? '<p class="wi-err" role="alert">' + esc(addError) + "</p>" : "") + "</form>";
}

function barHtml() {
  return '<div class="wi-bar"><button type="button" class="btn btn-small" data-wi="add-open" data-focus="wi-add">' +
    '+ Add</button><button type="button" class="wk-chip" data-wi="issues" aria-pressed="' + (issuesOnly ? "true" :
    "false") + '" data-focus="wi-issues">Issues</button><p class="wk-hint">Drag a card, or use its menu or ' +
    "Alt+arrows. Accept a card in Review to move it to Done.</p></div>" + addFormHtml();
}

function visible(items) {
  return issuesOnly ? items.filter(function (w) {
    return w.kind === "issue";
  }) : items;
}

export function workBoardView(ctx) {
  const items = visible(workItems(ctx.snap)).slice().sort(byPrio);
  const cols = WI_COLUMNS.map(function (c) {
    const mine = items.filter(function (w) {
      return colOf(w) === c.key;
    });
    const plus = c.key === "todo" ? '<button type="button" class="btn btn-small wi-plus" data-wi="add-open" ' +
      'aria-label="Add a Work item">+</button>' : "";
    return '<section class="wk-col" data-state="' + c.key + '" data-on="' + (ctx.col === c.key ? "true" : "false") +
      '" aria-labelledby="wk-col-' + c.key + '"><h3 class="wk-col-head" id="wk-col-' + c.key + '"><span>' +
      esc(c.label) + '</span><span class="wk-count num">' + mine.length + "</span>" + plus +
      '</h3><ul class="wk-cards">' +
      (mine.length ? mine.map(function (w) {
        return cardHtml(ctx.pid, w);
      }).join("") : '<li class="wk-none">No Work items here.</li>') + "</ul></section>";
  }).join("");
  return barHtml() + tabsHtml(ctx, items) + '<div class="wk-board wi-board">' + cols + "</div>";
}

const LIST_HEAD = [["ID", ""], ["P", ""], ["Work item", ""], ["Status", ""], ["Progress", ""], ["Owner", ""],
  ["", ""]];

function rowHtml(pid, w) {
  return '<li class="wi-row" data-work-item="' + esc(w.id) + '"><span class="wi-c wk-id" data-l="ID">' + esc(w.id) +
    '</span><span class="wi-c" data-l="P">' + prioChip(w.prio) + '</span><span class="wi-c wi-t" data-l="Work item">' +
    drawerHtml(pid, w) + '</span><span class="wi-c" data-l="Status">' + esc(w.status || "unknown") + badgesHtml(w) +
    '</span><span class="wi-c" data-l="Progress">' + progressHtml(w) + '</span><span class="wi-c" data-l="Owner">' +
    ownerText(w) + '</span><span class="wi-c">' + acceptHtml(pid, w) + "</span></li>";
}

function headRow() {
  return '<li class="wi-row wi-head" aria-hidden="true">' + LIST_HEAD.map(function (h) {
    return '<span class="wi-c">' + esc(h[0]) + "</span>";
  }).join("") + "</li>";
}

export function workListView(ctx) {
  const items = workItems(ctx.snap).slice().sort(byPrio);
  return '<ul class="wi-list" aria-label="Work items">' + headRow() + items.map(function (w) {
    return rowHtml(ctx.pid, w);
  }).join("") + "</ul>";
}

// The Tree: one fold per status column, the Work items of that status as rows.
export function workTreeView(ctx) {
  const items = workItems(ctx.snap).slice().sort(byPrio);
  return WI_COLUMNS.map(function (c) {
    const mine = items.filter(function (w) {
      return colOf(w) === c.key;
    });
    return '<details class="wi-fold"' + (c.key === "done" || c.key === "wontfix" ? "" : " open") +
      "><summary>" + esc(c.label) +
      ' <span class="num wk-count">' + mine.length + '</span></summary><ul class="wi-list">' + headRow() +
      mine.map(function (w) {
        return rowHtml(ctx.pid, w);
      }).join("") + "</ul></details>";
  }).join("");
}

// The Overview's work list: open Work items (not Done), P column first.
export function overviewWorkHtml(snap) {
  const items = (workItems(snap) || []).filter(function (w) {
    return w.status !== "Done" && w.status !== "Won't do";
  }).sort(byPrio);
  if (!items.length) return "";
  return '<ul class="wi-list wi-ov">' + items.slice(0, 8).map(function (w) {
    return '<li class="wi-row wi-row-ov"><span class="wi-c" data-l="P">' + prioChip(w.prio) +
      '</span><span class="wi-c wk-id" data-l="ID">' + esc(w.id) +
      '</span><span class="wi-c wi-t" data-l="Work item">' +
      '<a href="' + esc(buildHash({ name: "project", id: snap.id, section: "work", item: w.id })) + '">' +
      esc(w.title) + '</a></span><span class="wi-c" data-l="Status">' + esc(w.status || "unknown") +
      '</span><span class="wi-c" data-l="Progress">' + progressHtml(w) + "</span></li>";
  }).join("") + "</ul>";
}

// Agent task id -> {id, title} of its Work item, from the work rows' tasks lists. Empty when the snapshot has none.
export function taskWorkMap(snap) {
  const map = new Map();
  (workItems(snap) || []).forEach(function (w) {
    (Array.isArray(w.tasks) ? w.tasks : []).forEach(function (t) {
      if (t && t.id) map.set(String(t.id), { id: String(w.id), title: String(w.title || "") });
    });
  });
  return map;
}

// The header text of a group: "W3 Work board like Trello" or "No Work item".
export function groupLabel(work) {
  return work ? work.id + " " + work.title : NO_ITEM;
}

// Stable-group a list by its Work item: groups in first-seen order, "No Work item" last. items are read with
// taskOf(item) (an agent task id); with an empty map the list is returned as one ungrouped run.
export function groupByWork(items, taskOf, map) {
  if (!map || !map.size) return [{ work: null, label: "", items: items }];
  const groups = new Map();
  items.forEach(function (it) {
    const w = map.get(String(taskOf(it) || "")) || null;
    const key = w ? w.id : "";
    if (!groups.has(key)) groups.set(key, { work: w, label: groupLabel(w), items: [] });
    groups.get(key).items.push(it);
  });
  const all = Array.from(groups.values());
  return all.filter(function (g) {
    return g.work;
  }).concat(all.filter(function (g) {
    return !g.work;
  }));
}

function render() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event("hashchange"));
}

function projectOfEl(el) {
  const root = el.closest(".wk");
  return root ? root.getAttribute("data-project") : null;
}

function byId(id) {
  return (current || []).filter(function (w) {
    return w.id === id;
  })[0] || null;
}

function sameColumn(w) {
  return visible(current || []).filter(function (x) {
    return colOf(x) === colOf(w);
  }).sort(byPrio);
}

function rank(id, dir, project) {
  run("work.move", { id: id, dir: dir }, { project: project, label: id + " moved " + dir });
}

function submitAdd(form) {
  const data = new FormData(form);
  const title = String(data.get("title") || "").trim();
  if (!title) {
    addError = "Title is required.";
    render();
    return;
  }
  const kind = String(data.get("kind") || "task");
  const args = { title: title, kind: kind, prio: String(data.get("prio") || "P2") };
  const outcome = String(data.get("outcome") || "").trim();
  if (outcome) args.outcome = outcome;
  if (kind === "issue") {
    args.issue = String(data.get("issue") || "bug");
    args.sev = String(data.get("sev") || "2");
  }
  run("work.add", args, { project: projectOfEl(form), label: "Work item added", onError: function (message) {
    addError = message;
    render();
  } }).then(function (reply) {
    if (!reply) return;
    addOpen = false;
    addError = "";
    render();
  });
}

function onClick(event) {
  const el = event.target && event.target.closest ? event.target.closest("[data-wi]") : null;
  if (!el) return;
  const how = el.getAttribute("data-wi");
  const id = el.getAttribute("data-work");
  const project = projectOfEl(el);
  const menu = el.closest("details.wi-menu");
  if (menu) menu.open = false;
  if (how === "accept") {
    run("work.accept", { id: id }, { project: project, label: id + " accepted" });
  } else if (how === "add-open") {
    addOpen = true;
    addError = "";
    render();
    window.setTimeout(function () {
      const input = document.querySelector('.wi-add [name="title"]');
      if (input) input.focus({ preventScroll: true });
    }, 0);
  } else if (how === "add-cancel") {
    addOpen = false;
    addError = "";
    render();
  } else if (how === "issues") {
    issuesOnly = !issuesOnly;
    render();
  } else if (how === "move") {
    const w = byId(id);
    const m = w ? moveFor(w, el.getAttribute("data-to")) : null;
    if (m) run(m.op, m.args, { project: project, label: m.label });
  } else if (how === "rank") {
    rank(id, el.getAttribute("data-dir"), project);
  }
}

function onSubmit(event) {
  const form = event.target;
  if (!form || !form.getAttribute || form.getAttribute("data-wi") !== "add-form") return;
  event.preventDefault();
  submitAdd(form);
}

function onChange(event) {
  const el = event.target;
  if (!el || !el.getAttribute || el.getAttribute("data-wi") !== "add-kind") return;
  addKind = el.value === "issue" ? "issue" : "task";
  const form = el.closest("form");
  if (form) form.setAttribute("data-kind", addKind);
}

// Alt+Left/Right moves a focused card to the nearest allowed column in that direction; Alt+Up/Down is the rank.
function onKey(event) {
  const card = event.target && event.target.closest ? event.target.closest(".wi-card") : null;
  if (!card || !event.altKey || event.target !== card) return;
  const w = byId(card.getAttribute("data-work-item"));
  if (!w) return;
  const project = projectOfEl(card);
  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    event.preventDefault();
    rank(w.id, event.key === "ArrowUp" ? "up" : "down", project);
    return;
  }
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  const step = event.key === "ArrowLeft" ? -1 : 1;
  const keys = WI_COLUMNS.map(function (c) {
    return c.key;
  });
  for (let i = keys.indexOf(colOf(w)) + step; i >= 0 && i < keys.length; i += step) {
    const m = moveFor(w, keys[i]);
    if (m) {
      run(m.op, m.args, { project: project, label: m.label });
      return;
    }
  }
}

function colEl(event) {
  return event.target && event.target.closest ? event.target.closest(".wi-board .wk-col") : null;
}

function clearOver() {
  document.querySelectorAll(".wk-col.is-over").forEach(function (c) {
    c.classList.remove("is-over");
  });
}

// What a drop at this event would do: a column move, a same-column reorder (drop on a card), or nothing.
function dropPlan(event) {
  const w = byId(dragId);
  const col = colEl(event);
  if (!w || !col) return null;
  const to = col.getAttribute("data-state");
  if (to === colOf(w)) {
    const target = event.target.closest(".wi-card");
    const tw = target ? byId(target.getAttribute("data-work-item")) : null;
    if (!tw || tw.id === w.id || tw.prio !== w.prio) return null;
    const list = sameColumn(w);
    const steps = list.indexOf(tw) - list.indexOf(w);
    return steps ? { rank: steps } : null;
  }
  const m = moveFor(w, to);
  return m ? { move: m } : null;
}

function onDragStart(event) {
  const card = event.target && event.target.closest ? event.target.closest(".wi-card") : null;
  if (!card) return;
  dragId = card.getAttribute("data-work-item");
  card.classList.add("is-dragging");
  if (event.dataTransfer) {
    event.dataTransfer.setData("text/plain", dragId);
    event.dataTransfer.effectAllowed = "move";
  }
}

function onDragOver(event) {
  if (!dragId) return;
  const plan = dropPlan(event);
  clearOver();
  if (!plan) return;
  event.preventDefault();
  colEl(event).classList.add("is-over");
}

function onDrop(event) {
  const plan = dragId ? dropPlan(event) : null;
  const w = byId(dragId);
  const project = colEl(event) ? projectOfEl(colEl(event)) : null;
  clearOver();
  dragId = "";
  if (!plan || !w) return;
  event.preventDefault();
  if (plan.move) {
    run(plan.move.op, plan.move.args, { project: project, label: plan.move.label });
    return;
  }
  const dir = plan.rank < 0 ? "up" : "down";
  const items = [];
  for (let i = 0; i < Math.abs(plan.rank); i++) items.push({ op: "work.move", args: { id: w.id, dir: dir } });
  runBatch(items, { project: project, done: w.id + " reordered" });
}

function onDragEnd() {
  dragId = "";
  clearOver();
  document.querySelectorAll(".wi-card.is-dragging").forEach(function (c) {
    c.classList.remove("is-dragging");
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("click", onClick);
  document.addEventListener("submit", onSubmit);
  document.addEventListener("change", onChange);
  document.addEventListener("keydown", onKey);
  document.addEventListener("dragstart", onDragStart);
  document.addEventListener("dragover", onDragOver);
  document.addEventListener("drop", onDrop);
  document.addEventListener("dragend", onDragEnd);
}
