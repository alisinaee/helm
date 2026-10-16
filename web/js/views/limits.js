// Limits, simple (R7.28 A, docs/LIMITS-SIMPLE-SPEC.md). Two blocks on the Tokens screen: the weekly stop (one switch
// and one percent, for all projects: a global pct row on the week) and the share per project (one number and one
// daily or weekly choice per project: a project pct row). Both save with limit.set and remove with limit.rm, and
// nothing else. The server judges the rows (services/limits.py evaluate()): a row warns at 80% and stops at 100%.
// Caps for tasks, phases, models and whole projects are CLI features and are not edited here.

import { esc } from "../dom.js";
import { MISSING, fmtPercent } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { run } from "../cmd.js";
import { showToast } from "./toast.js";

const WEEKLY_MIN = 50;
const STATE_WORDS = { ok: "ok", warn: "Warning at 80%", block: "Stopped", unknown: "≈ not enough data" };
const STATE_SHORT = { ok: "ok", warn: "Warn 80%", block: "Stopped", unknown: "No data" };
const STATE_TONE = { ok: "neutral", warn: "warning", block: "danger", unknown: "neutral" };

function snapsOf(vm) {
  return vm.snapshotList || [];
}

function metersOf(snap) {
  return snap && Array.isArray(snap.meters) ? snap.meters : [];
}

function projectsOf(vm) {
  if (vm.projects && vm.projects.length) return vm.projects;
  return snapsOf(vm).map(function (s) {
    return { id: s.id, name: s.title || s.id };
  });
}

// The project a copy reference names: the project view's own project. The All view names none (no first-project slug).
function scopePid(vm) {
  return vm.route && vm.route.name === "project" ? vm.route.id || null : null;
}

function stateKey(row) {
  return STATE_WORDS[row.state] ? row.state : "unknown";
}

// The weekly stop row of one snapshot's meter rows: the global percent on the week, else the weekly stop of
// autonomy.json (an acct row). Null when the stop is off. The top bar uses the same rule (weeklyStopRow).
export function weeklyStopRow(rows) {
  if (!Array.isArray(rows)) return null;
  const global = rows.find(function (r) {
    return r.scope === "global" && r.kind === "pct" && r.window === "week";
  });
  return global || rows.find(function (r) {
    return r.kind === "acct";
  }) || null;
}

// The weekly share is known only from a fresh reading whose weekly reset has not passed (the server sets the
// percent to null then); a stale reading reads unknown here, the same as the limit row on the Tokens screen.
export function weekKnown(usage) {
  return Boolean(usage) && typeof usage.weeklyPercent === "number" && usage.stale !== true;
}

// The age of a stale reading in words: "31 h old", "12 min old". Empty when the age is not known.
export function oldText(usage) {
  if (!usage || typeof usage.ageNow !== "number") return "";
  const s = Math.max(0, usage.ageNow);
  if (s < 3600) return Math.max(1, Math.floor(s / 60)) + " min old";
  return Math.round(s / 3600) + " h old";
}

function weeklyRow(vm) {
  for (const snap of snapsOf(vm)) {
    const hit = weeklyStopRow(metersOf(snap));
    if (hit) return hit;
  }
  return null;
}

// The first stored project row that is a daily or weekly percent: the one this screen edits. Other rows are CLI rules.
function shareRowOf(vm, pid) {
  const snap = snapsOf(vm).find(function (s) {
    return s.id === pid;
  });
  return metersOf(snap).find(function (r) {
    return r.scope === "project" && r.kind === "pct" && (r.window === "day" || r.window === "week") &&
      r.src === "limits";
  }) || null;
}

// A project's own stop (autonomy.json) is read through; it is shown as a note when the global stop does not cover it.
function ownStopsHtml(vm, globalValue) {
  const names = projectsOf(vm);
  return snapsOf(vm).map(function (snap) {
    const auto = metersOf(snap).find(function (r) {
      return r.src === "autonomy" && r.kind === "acct";
    });
    if (!auto || (globalValue !== null && Number(auto.limit) >= globalValue)) return "";
    const p = names.find(function (x) {
      return x.id === snap.id;
    });
    return '<p class="page-note">' + esc((p ? p.name : snap.id) + " stops at " + Number(auto.limit) + "% on its own.") +
      "</p>";
  }).join("");
}

// The weekly stop: one on/off switch and one percent. The form submits on Enter.
export function weeklyStopHtml(vm) {
  const row = weeklyRow(vm);
  const on = row !== null;
  const pid = scopePid(vm);
  const shown = on ? Number(row.limit) : 95;
  const chip = on ? '<span class="chip chip-' + esc(STATE_TONE[stateKey(row)]) + '">' +
    esc(STATE_WORDS[stateKey(row)]) + "</span>" : "";
  const toggle = '<button type="button" class="btn" role="switch" aria-checked="' + (on ? "true" : "false") +
    '" aria-label="' + (on ? "Weekly stop, on" : "Weekly stop, off") + '" data-action="lim-weekly" data-row="' +
    esc(on ? row.id : "") + '" data-focus="weekly-toggle">' + (on ? "On" : "Off") + "</button>";
  const copy = copyButton("section", "tokens.weekly", "Weekly stop", { project: pid,
    sum: refSummary("section", 1) });
  const state = on ? chip : '<span class="chip chip-neutral">Off</span>';
  return '<section class="lim-block" aria-labelledby="lim-weekly-h">' +
    '<div class="lim-bar"><h3 id="lim-weekly-h" class="lim-h">Weekly stop</h3>' + copy + "</div>" +
    '<form class="row-grid rg-weekly" data-form="weekly" data-project="' + esc(pid || "") + '" data-row="' +
    esc(on ? row.id : "") + '" data-on="' + (on ? "true" : "false") + '">' + toggle +
    '<label class="rg-main">Stop agents at <input class="lim-text" type="text" size="3" maxlength="3" ' +
    'inputmode="numeric" pattern="[0-9]*" value="' + esc(String(shown)) + '" aria-label="Weekly stop percent, ' +
    WEEKLY_MIN + ' to 100"> % of my weekly usage</label>' + state + "</form>" +
    ownStopsHtml(vm, on ? shown : null) + "</section>";
}

function shareOption(value, text, selected) {
  return '<option value="' + value + '"' + (selected ? " selected" : "") + ">" + text + "</option>";
}

// One project's share row: name, one number (empty = no limit), daily or weekly, used, state.
function shareLineHtml(vm, p) {
  const snap = snapsOf(vm).find(function (s) {
    return s.id === p.id;
  });
  const row = shareRowOf(vm, p.id);
  const week = snap && snap.weekUse ? snap.weekUse : {};
  const win = row ? row.window : "week";
  const used = row ? row.used : week.estPts;
  const usedText = used == null ? MISSING : "≈ " + fmtPercent(used);
  const others = metersOf(snap).filter(function (r) {
    return r.scope === "project" && r.src === "limits" && r !== row;
  }).length;
  const chip = row ? '<span class="chip chip-' + esc(STATE_TONE[stateKey(row)]) + '" title="' +
    esc(STATE_WORDS[stateKey(row)]) + '">' + esc(STATE_SHORT[stateKey(row)]) + "</span>" :
    '<span class="chip chip-neutral">No limit</span>';
  const numId = "lim-share-" + p.id;
  const winId = "lim-win-" + p.id;
  return '<form class="row-grid rg-share" data-form="share" data-project="' + esc(p.id) + '" data-row="' +
    esc(row ? row.id : "") + '" data-window="' + esc(win) + '" data-name="' + esc(p.name) + '">' +
    '<span class="rg-t">' + esc(p.name) + (others ? ' <span class="page-note">+ ' + others + " CLI rules</span>" : "") +
    "</span>" +
    '<span class="rg-main"><input id="' + esc(numId) + '" class="lim-text" type="text" size="3" maxlength="3" ' +
    'pattern="[0-9]*" inputmode="numeric" placeholder="none" value="' +
    esc(row ? String(row.limit) : "") + '" aria-label="' +
    esc("Limit for " + p.name + ", percent; empty for no limit") + '"> %' +
    '<select id="' + esc(winId) + '" class="lim-select" data-field="window" aria-label="' +
    esc("Daily or weekly for " + p.name) + '">' +
    shareOption("day", "daily", win === "day") + shareOption("week", "weekly", win === "week") +
    "</select></span>" +
    '<span class="rg-num" title="Used so far">' + esc(usedText) + "</span>" +
    '<span class="rg-state">' + chip + "</span></form>";
}

// The share per project: one row per registered project. Collapsed when no project has a limit.
export function shareRowsHtml(vm) {
  const projects = projectsOf(vm);
  const anySet = projects.some(function (p) {
    return shareRowOf(vm, p.id) !== null;
  });
  const copy = copyButton("section", "tokens.share", "Share per project", { project: scopePid(vm),
    sum: refSummary("section", projects.length) });
  return '<details class="lim-block lim-share-block"' + (anySet ? " open" : "") + ">" +
    '<summary class="lim-h">Share per project (optional): name, limit % per day or week, used, state</summary>' + copy +
    projects.map(function (p) {
      return shareLineHtml(vm, p);
    }).join("") + "</details>";
}

// Save the weekly stop (limit.set, global pct on the week). The value must be a whole percent from 50 to 100.
function setWeekly(form) {
  const input = form.querySelector("input");
  const value = Number(input ? input.value.trim() : "");
  if (!Number.isInteger(value) || value < WEEKLY_MIN || value > 100) {
    showToast({ text: "Enter a whole percent from 50 to 100.", tone: "danger" });
    return;
  }
  run("limit.set", { scope: "global", window: "week", kind: "pct", value: value, action: "block" },
    { project: form.getAttribute("data-project") || null, label: "Weekly stop set to " + value + "%" });
}

// Save one project's share. An empty number removes the row (no limit). A changed window removes the old row first,
// because a row is keyed by its window.
async function setShare(form) {
  const pid = form.getAttribute("data-project");
  const id = form.getAttribute("data-row") || "";
  const was = form.getAttribute("data-window");
  const name = form.getAttribute("data-name") || pid;
  const input = form.querySelector("input");
  const select = form.querySelector("select");
  const raw = input ? input.value.trim() : "";
  if (raw === "") {
    if (id) run("limit.rm", { id: id }, { project: pid, label: name + ": no limit" });
    return;
  }
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1 || value > 100) {
    showToast({ text: "Enter a whole percent from 1 to 100, or leave it empty for no limit.", tone: "danger" });
    return;
  }
  const win = select && select.value === "day" ? "day" : "week";
  if (id && was !== win) await run("limit.rm", { id: id }, { project: pid, label: name + ": old window removed" });
  run("limit.set", { scope: "project", window: win, kind: "pct", value: value, action: "block" },
    { project: pid, label: name + " up to " + value + "% " + (win === "day" ? "a day" : "a week") });
}

// Actions for this module. Returns true when it handled the action (app.js then re-renders).
export function limitAction(action, el) {
  if (action !== "lim-weekly") return false;
  const form = el.closest ? el.closest("form") : null;
  if (!form) return true;
  if (el.getAttribute("aria-checked") === "true") {
    const id = form.getAttribute("data-row");
    if (id) run("limit.rm", { id: id }, { project: form.getAttribute("data-project") || null,
      label: "Weekly stop off" });
  } else {
    setWeekly(form);
  }
  return true;
}

// Submit and change handlers, attached once to <main> (patch() replaces its children, not the element). Enter in a
// number field submits its form; choosing daily or weekly saves the row with the number already there.
let listening = false;

export function attachLimitListeners() {
  if (listening || typeof document === "undefined") return;
  const main = document.getElementById("main");
  if (!main) return;
  listening = true;
  main.addEventListener("submit", function (event) {
    const form = event.target;
    const kind = form && form.getAttribute ? form.getAttribute("data-form") : null;
    if (kind !== "weekly" && kind !== "share") return;
    event.preventDefault();
    if (kind === "share") {
      setShare(form);
    } else if (form.getAttribute("data-on") === "true") {
      setWeekly(form);
    } else {
      showToast({ text: "Turn the weekly stop on first.", tone: "danger" });
    }
  });
  main.addEventListener("change", function (event) {
    const t = event.target;
    const form = t && t.form ? t.form : null;
    if (t.tagName === "SELECT" && form && form.getAttribute("data-form") === "share") form.requestSubmit();
  });
}
