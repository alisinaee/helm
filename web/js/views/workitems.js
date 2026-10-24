// Work items (R9.20, R9.23 M8/M9; docs/WORK-MODEL.md section 3). The Work board, List and Tree show the snapshot's
// work[] rows only (never an agent task as a card), the P column chip, and the grouping of agents and jobs under their
// Work item. Row fields: id, title, kind, status, prio ("P0".."P3"), badges, progress {done,total}. Optional fields
// the snapshot may add: owner, outcome and tasks [{id,state,model,job}] (the agent tasks of the item). Every value is
// escaped; the Accept button runs the work.accept op through cmd.js.

import { chipHtml, esc, meterHtml } from "../dom.js";
import { run } from "../cmd.js";
import { buildHash } from "../router.js";

export const WI_COLUMNS = [
  { key: "backlog", status: "Backlog", label: "Backlog" },
  { key: "todo", status: "Todo", label: "Todo" },
  { key: "doing", status: "Doing", label: "Doing" },
  { key: "review", status: "Review", label: "Review" },
  { key: "done", status: "Done", label: "Done" },
];
const COL_OF = { "Won't do": "done" };
const PRIO = /^P[0-3]$/;
const NO_ITEM = "No Work item";

let asksOf = {};
let pidOf = "";

export function workItems(snap) {
  asksOf = snap && snap.askOf && typeof snap.askOf === "object" ? snap.askOf : {};
  pidOf = snap && snap.id ? String(snap.id) : "";
  return snap && Array.isArray(snap.work) ? snap.work.filter(function (w) {
    return w && w.id;
  }) : null;
}

function colOf(w) {
  const hit = WI_COLUMNS.filter(function (c) {
    return c.status === w.status;
  })[0];
  return hit ? hit.key : COL_OF[w.status] || "todo";
}

function num(id) {
  const m = /(\d+)/.exec(String(id));
  return m ? Number(m[1]) : 0;
}

function byPrio(a, b) {
  const pa = PRIO.test(a.prio) ? a.prio : "P9";
  const pb = PRIO.test(b.prio) ? b.prio : "P9";
  return pa < pb ? -1 : pa > pb ? 1 : num(a.id) - num(b.id);
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

function cardHtml(pid, w) {
  return '<li class="wk-card wi-card' + (w.status === "Done" ? " is-done" : "") + '" data-work-item="' + esc(w.id) +
    '"><div class="wk-card-top"><span class="wk-id">' + esc(w.id) + "</span>" + prioChip(w.prio) + badgesHtml(w) +
    "</div>" + drawerHtml(pid, w) + progressHtml(w) + '<div class="wk-meta"><span>' + ownerText(w) + "</span>" +
    acceptHtml(pid, w) + "</div></li>";
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

export function workBoardView(ctx) {
  const items = workItems(ctx.snap).slice().sort(byPrio);
  const cols = WI_COLUMNS.map(function (c) {
    const mine = items.filter(function (w) {
      return colOf(w) === c.key;
    });
    return '<section class="wk-col" data-state="' + c.key + '" data-on="' + (ctx.col === c.key ? "true" : "false") +
      '" aria-labelledby="wk-col-' + c.key + '"><h3 class="wk-col-head" id="wk-col-' + c.key + '"><span>' +
      esc(c.label) + '</span><span class="wk-count num">' + mine.length + '</span></h3><ul class="wk-cards">' +
      (mine.length ? mine.map(function (w) {
        return cardHtml(ctx.pid, w);
      }).join("") : '<li class="wk-none">No Work items here.</li>') + "</ul></section>";
  }).join("");
  return '<p class="wk-hint">Work items only. Accept a card in Review to move it to Done.</p>' +
    tabsHtml(ctx, items) + '<div class="wk-board wi-board">' + cols + "</div>";
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
    return '<details class="wi-fold"' + (c.key === "done" ? "" : " open") + "><summary>" + esc(c.label) +
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

function onClick(event) {
  const el = event.target && event.target.closest ? event.target.closest('[data-wi="accept"]') : null;
  const root = el ? el.closest(".wk") : null;
  if (!root) return;
  const id = el.getAttribute("data-work");
  run("work.accept", { id: id }, { project: root.getAttribute("data-project"), label: id + " accepted" });
}

if (typeof document !== "undefined") document.addEventListener("click", onClick);
