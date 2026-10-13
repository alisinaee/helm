// Limit rows (WP33): the editor rows, the add presets and their actions. The rows are the snapshot's meters.limits;
// every change goes through run() in cmd.js, so a refusal reverts and shows a toast, and a change that can be undone
// gets an Undo toast. Rows read through from autonomy.json or budget.json are shown read-only with their source.
// The client does no maths on the limits: the slider and stepper only move the value the server will check.

import { emptyHtml, esc } from "../dom.js";
import { fmtTokens } from "../format.js";
import { run } from "../cmd.js";
import { showToast } from "./toast.js";

const WINDOW_WORDS = { day: "Day", week: "Week", total: "Total" };
const STATE_WORDS = { ok: "ok", warn: "Warning", block: "Stopped", unknown: "unknown" };
const STATE_TONE = { ok: "neutral", warn: "warning", block: "danger", unknown: "neutral" };
const STORED_SRC = ["config", "limits"];
const FAIR_DAY = "14.3";

// The three add presets. The daily preset for all projects only appears in global scope.
export const PRESETS = [
  { id: "day10", label: "Stay under 10% a day", scopes: ["global", "project"],
    row: { window: "day", kind: "pct", value: 10, action: "block" } },
  { id: "week60", label: "Weekly 60%", scopes: ["global", "project"],
    row: { window: "week", kind: "pct", value: 60, action: "block" } },
  { id: "dayall", label: "Daily for all projects", scopes: ["global"],
    row: { window: "day", kind: "pct", value: Number(FAIR_DAY), action: "block" } },
];

let addOpen = false;
let sheetId = null;

// The rows that belong to a scope, as the limits editor lists them.
export function rowsForScope(scope, rows) {
  return (rows || []).filter(function (row) {
    return scope === "global" ? row.scope === "global" : true;
  });
}

// Whether a row can be edited here: a stored row of this scope. Read-through rows (autonomy, budget) and rows of
// another scope are read-only.
export function editable(row, scope) {
  return row.scope === scope && STORED_SRC.indexOf(row.src) >= 0 && (row.kind === "pct" || row.kind === "tok") &&
    row.action !== null;
}

function valueText(row) {
  if (row.value == null && row.limit == null) return "not set";
  const v = row.limit;
  if (row.kind === "tok") return fmtTokens(v);
  return String(v) + "%";
}

// The row's name: "Day limit 10% of weekly", "Week limit 500k tokens" or the account's "Weekly stop 72%".
function titleText(row, est) {
  if (row.kind === "acct") return "Weekly stop " + est + valueText(row);
  const unit = row.kind === "tok" ? " tokens" : " of weekly";
  return (WINDOW_WORDS[row.window] || row.window) + " limit " + est + valueText(row) + unit;
}

// The preview under an editor: a plain-words reading of the value.
export function previewText(kind, window, value) {
  const v = Number(value);
  if (!Number.isFinite(v) || v <= 0) return "Enter a value above 0.";
  if (kind === "tok") {
    const shown = v >= 1000 ? (v / 1000).toFixed(1) + "M" : String(v) + "k";
    return "≈ " + shown + " tokens. Exact for jobs that report their tokens.";
  }
  const where = window === "week" ? "of your weekly allowance" : "of weekly, per day";
  const hint = window === "day" ? " A fair day is about " + FAIR_DAY + "%." : "";
  return "≈ " + v + "% " + where + "." + hint;
}

function clampValue(kind, value) {
  if (kind === "tok") return Math.max(1, Math.round(value));
  return Math.min(100, Math.max(1, Math.round(value)));
}

function windowOptions(row, scope) {
  const opts = ["day", "week"];
  if (row.kind === "tok" && scope === "project") opts.push("total");
  return opts;
}

function selectHtml(id, label, options, current, focus) {
  return '<label class="lim-field"><span class="lim-label">' + esc(label) + "</span>" +
    '<select class="lim-select" data-focus="' + esc(focus) + '" data-field="' + esc(id) + '">' +
    options.map(function (o) {
      return '<option value="' + esc(o.value) + '"' + (o.value === current ? " selected" : "") + ">" +
        esc(o.text) + "</option>";
    }).join("") + "</select></label>";
}

// One editable row: window, unit, stepper and slider or number field, action, preview, delete.
function editorHtml(row, scope) {
  const id = row.id;
  const isPct = row.kind === "pct";
  const value = row.limit == null ? 0 : row.limit;
  const range = isPct
    ? '<input class="lim-range" type="range" min="1" max="100" step="1" value="' + esc(value) +
      '" aria-label="Limit for ' + esc(id) + ', percent" data-focus="range-' + esc(id) + '" data-row="' +
      esc(id) + '">'
    : '<input class="lim-num" type="number" min="1" step="1" value="' + esc(value) +
      '" aria-label="Limit for ' + esc(id) + ', thousands of tokens" data-focus="num-' + esc(id) +
      '" data-row="' + esc(id) + '">';
  const unitOpts = [{ value: "pct", text: "% of weekly" }, { value: "tok", text: "tokens" }];
  const winOpts = windowOptions(row, scope).map(function (w) {
    return { value: w, text: WINDOW_WORDS[w] };
  });
  return '<div class="lim-edit">' +
    selectHtml("window", "Window", winOpts, row.window, "win-" + id).replace('data-field="window"',
      'data-field="window" data-row="' + esc(id) + '"') +
    selectHtml("unit", "Unit", unitOpts, isPct ? "pct" : "tok", "unit-" + id).replace('data-field="unit"',
      'data-field="unit" data-row="' + esc(id) + '"') +
    '<div class="lim-value"><span class="lim-label" aria-hidden="true">' + esc(isPct ? "Limit" : "Thousands") +
    "</span>" +
    '<div class="lim-stepper">' +
    '<button type="button" class="btn btn-small step" data-action="lim-step" data-row="' + esc(id) +
    '" data-dir="-1" aria-label="Lower limit ' + esc(id) + '" data-focus="dn-' + esc(id) + '">−</button>' +
    range +
    '<button type="button" class="btn btn-small step" data-action="lim-step" data-row="' + esc(id) +
    '" data-dir="1" aria-label="Raise limit ' + esc(id) + '" data-focus="up-' + esc(id) + '">+</button></div></div>' +
    selectHtml("action", "When reached", [{ value: "block", text: "Stop" }, { value: "warn", text: "Warn" }],
      row.action, "act-" + id).replace('data-field="action"', 'data-field="action" data-row="' + esc(id) + '"') +
    '<p class="lim-preview" data-preview-for="' + esc(id) + '">' +
    esc(previewText(row.kind, row.window, value)) + "</p>" +
    '<button type="button" class="btn btn-small" data-action="lim-del" data-row="' + esc(id) +
    '" data-focus="del-' + esc(id) + '">Delete</button></div>';
}

function readOnlyHtml(row, scope) {
  const from = row.src === "autonomy" ? "from autonomy.json (the weekly stop)" :
    row.src === "budget" ? "from budget.json (the project token budget)" :
      row.scope === "global" && scope === "project" ? "from All projects, applies to this project" :
        "and its action is not in the snapshot yet, so it cannot be edited here";
  return '<p class="lim-readonly">Read only, ' + esc(from) + ".</p>" +
    (STORED_SRC.indexOf(row.src) >= 0 && row.scope === scope ?
      '<button type="button" class="btn btn-small" data-action="lim-del" data-row="' + esc(row.id) +
      '" data-focus="del-' + esc(row.id) + '">Delete</button>' : "");
}

// One limit row: a summary line (window, value, unit, state, pace) with the editor or the read-only note.
export function limitRowHtml(row, scope) {
  const state = STATE_WORDS[row.state] ? row.state : "unknown";
  const est = row.est ? "≈ " : "";
  const sheetOpen = sheetId === row.id;
  const body = editable(row, scope) ? editorHtml(row, scope) : readOnlyHtml(row, scope);
  return '<li class="lim-row' + (sheetOpen ? " is-sheet" : "") + '" id="lim-' + esc(row.id) + '" data-state="' +
    esc(state) + '">' +
    '<div class="lim-head"><span class="lim-title">' + esc(titleText(row, est)) + "</span>" +
    '<span class="chip chip-' + esc(STATE_TONE[state]) + '">' + esc(STATE_WORDS[state]) + "</span>" +
    '<span class="lim-id">' + esc(row.id) + "</span>" +
    '<button type="button" class="btn btn-small lim-edit-btn" data-action="lim-sheet" data-row="' + esc(row.id) +
    '" aria-expanded="' + (sheetOpen ? "true" : "false") + '" aria-controls="lim-' + esc(row.id) +
    '" data-focus="sheet-' + esc(row.id) + '">' +
    (sheetOpen ? "Done" : "Edit") + "</button></div>" + body + "</li>";
}

function presetsHtml(scope) {
  return '<div class="lim-presets" role="group" aria-label="Add a limit">' +
    PRESETS.filter(function (p) {
      return p.scopes.indexOf(scope) >= 0;
    }).map(function (p) {
      return '<button type="button" class="btn" data-action="lim-preset" data-preset="' + esc(p.id) +
        '" data-focus="preset-' + esc(p.id) + '">' + esc(p.label) + "</button>";
    }).join("") + "</div>";
}

// The limits editor: the rows, an empty state with the presets, and the add control.
export function limitsHtml(scope, rows) {
  const list = rowsForScope(scope, rows);
  const head = '<div class="lim-bar"><h3 class="lim-h">Limits</h3>' +
    '<button type="button" class="btn btn-small" data-action="lim-add" data-focus="lim-add">+ Add limit</button></div>';
  if (!list.length) {
    return '<div class="lim-block">' + head + presetsHtml(scope) +
      emptyHtml("No limits. Agents may use your whole weekly allowance.", "") + "</div>";
  }
  const add = addOpen ? presetsHtml(scope) : "";
  return '<div class="lim-block">' + head + add +
    '<ul class="lim-list">' + list.map(function (row) {
      return limitRowHtml(row, scope);
    }).join("") + "</ul>" +
    '<p class="lim-note">Warn shows a banner. Stop blocks agents from starting new work.</p></div>';
}

// The args for limit.set from a row with some fields replaced.
function rowArgs(row, scope, change) {
  const base = { id: row.id, scope: row.scope || scope, window: row.window, kind: row.kind,
    value: row.limit, action: row.action || "block" };
  return Object.assign(base, change);
}

function setRow(args, pid, label) {
  return run("limit.set", args, { project: pid, label: label });
}

function valueOf(el) {
  return Number(el.value);
}

// Read the editor's current row fields from the DOM for a commit (the row is the snapshot row, see rowArgs).
function rowById(rows, id) {
  for (const row of rows || []) {
    if (row.id === id) return row;
  }
  return null;
}

// Actions for the limits editor. Returns true when it handled the action (app.js then re-renders).
// ctx: {scope, pid, rows} as built by the section, kept in the module between renders.
let ctx = { scope: "project", pid: null, rows: [] };

export function setLimitContext(next) {
  ctx = next;
}

export function limitAction(action, el) {
  if (action === "lim-add") {
    addOpen = !addOpen;
    return true;
  }
  if (action === "lim-sheet") {
    const id = el.getAttribute("data-row");
    sheetId = sheetId === id ? null : id;
    return true;
  }
  if (action === "lim-preset") {
    const preset = PRESETS.find(function (p) {
      return p.id === el.getAttribute("data-preset");
    });
    if (!preset) return true;
    addOpen = false;
    run("limit.set", Object.assign({ scope: ctx.scope }, preset.row), { project: ctx.pid, label: preset.label +
      " added" });
    return true;
  }
  if (action === "lim-del") {
    const id = el.getAttribute("data-row");
    sheetId = null;
    run("limit.rm", { id: id }, { project: ctx.pid, label: "Limit " + id + " removed" });
    return true;
  }
  if (action === "lim-step") {
    const row = rowById(ctx.rows, el.getAttribute("data-row"));
    if (!row) return true;
    const dir = Number(el.getAttribute("data-dir")) < 0 ? -1 : 1;
    const step = row.kind === "tok" ? 100 : 1;
    const next = clampValue(row.kind, (row.limit || 0) + dir * step);
    if (next === row.limit) return true;
    setRow(rowArgs(row, ctx.scope, { value: next }), ctx.pid, "Limit " + row.id + " set");
    return true;
  }
  if (action === "spend-cap") {
    const field = el.parentNode.querySelector("input");
    const scope = el.getAttribute("data-scope");
    const key = el.getAttribute("data-key") || "";
    const raw = field ? field.value.trim() : "";
    const value = raw === "" ? null : Number(raw);
    if (value !== null && (!Number.isFinite(value) || value <= 0)) {
      showToast({ text: "A cap is a number of thousands above 0, or empty for no cap.", tone: "danger" });
      return true;
    }
    if (scope === "tasks") {
      run("task.cap", { id: key, value: value }, { project: ctx.pid, label: "Cap set on " + key });
    } else {
      run("budget.set", { scope: scope, key: key, value: value }, { project: ctx.pid,
        label: "Cap set on " + (key || "project") });
    }
    return true;
  }
  if (action === "lim-override") {
    const select = el.parentNode.querySelector("select");
    const hours = select ? Number(select.value) : 1;
    run("control.override", { hours: hours }, { project: ctx.pid, label: "Override set for " + hours + " h" });
    return true;
  }
  return false;
}

// Input and change handlers, attached once to <main> (patch() replaces its children, not the element). The slider
// and number fields move only the preview while typing; a change commits the value.
let listening = false;

export function attachLimitListeners() {
  if (listening || typeof document === "undefined") return;
  const main = document.getElementById("main");
  if (!main) return;
  listening = true;
  main.addEventListener("input", function (event) {
    const t = event.target;
    const id = t && t.getAttribute ? t.getAttribute("data-row") : null;
    if (!id || (t.type !== "range" && t.type !== "number")) return;
    const row = rowById(ctx.rows, id);
    if (!row) return;
    const preview = main.querySelector('[data-preview-for="' + id + '"]');
    if (preview) preview.textContent = previewText(row.kind, row.window, valueOf(t));
  });
  main.addEventListener("change", function (event) {
    const t = event.target;
    const id = t && t.getAttribute ? t.getAttribute("data-row") : null;
    if (!id) return;
    const row = rowById(ctx.rows, id);
    if (!row) return;
    const field = t.getAttribute("data-field");
    if (field === "window") {
      setRow(rowArgs(row, ctx.scope, { window: t.value }), ctx.pid, "Window set");
    } else if (field === "action") {
      setRow(rowArgs(row, ctx.scope, { action: t.value }), ctx.pid, t.value === "warn" ? "Set to warn" : "Set to stop");
    } else if (field === "unit") {
      const kind = t.value === "tok" ? "tok" : "pct";
      const value = kind === "tok" ? 100 : 10;
      const win = kind === "pct" && row.window === "total" ? "week" : row.window;
      setRow(rowArgs(row, ctx.scope, { kind: kind, value: value, window: win }), ctx.pid, "Unit set");
    } else if (t.type === "range" || t.type === "number") {
      const next = valueOf(t);
      if (!Number.isFinite(next) || next <= 0) {
        showToast({ text: "Enter a number above 0.", tone: "danger" });
        return;
      }
      const value = clampValue(row.kind, next);
      if (value === row.limit) return;
      setRow(rowArgs(row, ctx.scope, { value: value }), ctx.pid, "Limit " + row.id + " set");
    }
  });
}
