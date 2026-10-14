// Tokens (WP33): the meters (Today and This week) for the scope, the limits editor, the account card, spend and the
// override. Scope follows the panel: All projects is global, a project is that project. Every number is read from the
// snapshot (meters.limits, meters.today and meters.week); the only arithmetic is the bar lengths and the position of
// the "today started here" tick, which is a width, not a limit.

import { bannerHtml, chipHtml, esc, meterHtml } from "../dom.js";
import { MISSING, fmtPercent, fmtTokens } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { pageState } from "./inbox.js";
import { attachLimitListeners, limitsHtml, setLimitContext } from "./limits.js";
import { usageView } from "./usage.js";

const WARN_AT = 80;
const RANK = { block: 3, warn: 2, ok: 1, unknown: 0 };
const STATE_WORDS = { ok: "ok", warn: "Warning", block: "Stopped", unknown: "unknown" };
const STATE_KIND = { ok: "success", warn: "warning", block: "danger", unknown: "neutral" };
const OVERRIDE_HOURS = [1, 2, 3, 4];

// The bar length for a used and a limit value, clamped to 0-100. Presentation only.
function barPct(used, limit) {
  if (!(limit > 0) || used == null) return 0;
  return Math.min(100, Math.max(0, (used / limit) * 100));
}

function fmtUnit(kind, value) {
  if (value == null) return MISSING;
  return kind === "tok" ? fmtTokens(value) : fmtPercent(value);
}

// The row of a window that needs the most attention, or null when the scope has no row for that window.
function primaryRow(rows, window) {
  let best = null;
  for (const row of rows || []) {
    if (row.window !== window) continue;
    if (!best || RANK[row.state] > RANK[best.state]) best = row;
  }
  return best;
}

function paceLine(row, window, unknown) {
  if (unknown) return "Usage data is outdated; limit unmeasured.";
  if (row.state === "block") return "Limit reached.";
  if (row.paceAt) return "At this pace: limit reached about " + row.paceAt.slice(11, 16);
  return window === "day" ? "Won't reach today" : "Won't reach this week";
}

// One meter: the used and the limit, the 80% warning tick, an optional "today started here" tick, the state and the
// pace line. An empty meter says what the scope has instead of a limit.
function meterCard(label, window, row, fallback, dayTick) {
  if (!row) {
    return '<div class="met" data-state="none"><div class="met-head"><span class="met-label">' + esc(label) +
      '</span><span class="met-value">' + esc(fallback) + "</span></div></div>";
  }
  const unknown = row.state === "unknown" || row.used == null;
  const state = unknown ? "unknown" : row.state;
  const tone = unknown ? "unknown" : row.state === "block" ? "danger" : row.state === "warn" ? "warning" : "accent";
  const est = row.est ? "≈ " : "";
  const value = unknown ? "unknown" : est + fmtUnit(row.kind, row.used) + " of " + fmtUnit(row.kind, row.limit);
  const warnTick = '<span class="mrail" data-pct="' + WARN_AT + '"><i class="mtick mtick-warn"></i></span>';
  const today = dayTick == null ? "" : '<span class="mrail mrail-day" data-pct="' + dayTick +
    '"><i class="mtick mtick-day"></i></span>';
  const bar = '<div class="mbar">' + meterHtml(unknown ? 0 : barPct(row.used, row.limit), tone) + warnTick +
    today + "</div>";
  return '<div class="met" data-state="' + esc(state) + '"><div class="met-head"><span class="met-label">' +
    esc(label) + '</span><span class="met-value num">' + esc(value) + "</span>" +
    chipHtml(STATE_WORDS[state], STATE_KIND[state]) + "</div>" + bar +
    '<p class="pace">' + esc(paceLine(row, window, unknown)) + "</p></div>";
}

// The day tick on the weekly meter: where the week stood when today started. Week used minus today's points.
function dayTickFor(weekRow, dayPts) {
  if (!weekRow || weekRow.kind !== "pct" || weekRow.scope !== "global" || dayPts == null) return null;
  if (weekRow.used == null || !(weekRow.limit > 0)) return null;
  return barPct(weekRow.used - dayPts, weekRow.limit);
}

function metersHtml(rows, snap, isProject) {
  const dayRow = primaryRow(rows, "day");
  const weekRow = primaryRow(rows, "week");
  const dayPts = snap && snap.dayUse ? snap.dayUse.value : null;
  const weekPct = snap && snap.weekUse ? snap.weekUse.value : null;
  const dayFallback = isProject ? "No day limit for this project" : "No day limit" +
    (dayPts == null ? "" : ". Used today " + fmtPercent(dayPts));
  const weekFallback = isProject ? "No weekly limit for this project" : "No weekly limit" +
    (weekPct == null ? "" : ". Account at " + fmtPercent(weekPct));
  const legend = '<p class="met-legend">Marker at ' + WARN_AT + "% indicates warning threshold.</p>";
  return '<div class="met-row">' + meterCard("Today", "day", dayRow, dayFallback, null) +
    meterCard("This week", "week", weekRow, weekFallback, dayTickFor(weekRow, dayPts)) + "</div>" + legend;
}

// Account card: the 5-hour and weekly percent (usage.js), and the project's stop at weekly percent when set.
function accountHtml(vm, rows, pid) {
  const ceiling = rows.filter(function (row) {
    return row.kind === "acct";
  });
  const note = ceiling.length ? '<p class="page-note">Project stop: ' + esc(fmtPercent(ceiling[0].limit)) +
    " of weekly budget.</p>" : "";
  const copy = copyButton("section", "tokens.account", "Account", { project: pid,
    sum: refSummary("section", rows.length) });
  return '<section class="ov-card tk-card" aria-labelledby="tk-account"><div class="lim-bar">' +
    '<h3 id="tk-account" class="lim-h">Account</h3>' + copy + "</div>" + usageView(vm) + note + "</section>";
}

function capRow(scope, key, name, budgetRow) {
  const spent = budgetRow ? fmtTokens(budgetRow.spent) : MISSING;
  const cap = budgetRow && budgetRow.limit != null ? String(budgetRow.limit) : "";
  return '<li class="row-grid tk-spend"><span class="rg-t spend-name" title="' + esc(name) + '">' + esc(name) +
    '</span><span class="rg-num num spend-val">' + esc(spent) + '</span><span class="rg-num num">' +
    esc(cap ? "of " + cap + "k" : "no cap") + "</span>" +
    '<label class="lim-field"><span class="lim-label">Token limit (thousands)</span>' +
    '<input class="lim-num" type="number" min="1" step="1" value="' + esc(cap) + '" data-focus="cap-' + esc(scope) +
    "-" + esc(key) + '"></label>' +
    '<button type="button" class="btn btn-small" data-action="spend-cap" data-scope="' + esc(scope) +
    '" data-key="' + esc(key) + '" aria-label="Save cap for ' + esc(name) +
    '" data-focus="save-' + esc(scope) + "-" + esc(key) + '">Save cap</button></li>';
}

// Spend for one project: the project cap, phase, model and the top five tasks by spend. Caps are set here.
function spendHtml(snap) {
  const bud = snap.budget || { phases: {}, models: {}, total: null };
  const phaseNames = {};
  for (const p of snap.phases || []) phaseNames[p.id] = p.name;
  const taskRows = (snap.tasks || []).filter(function (t) {
    return t.spentK > 0;
  }).sort(function (a, b) {
    return b.spentK - a.spentK;
  }).slice(0, 5);
  const phases = Object.keys(bud.phases || {});
  const models = Object.keys(bud.models || {});
  const parts = [
    '<ul class="spend-list" aria-label="Project cap">' + capRow("project", "", "Project total", bud.total) + "</ul>",
    phases.length ? '<h4 class="lim-h2">Phases</h4><ul class="spend-list">' + phases.map(function (id) {
      return capRow("phases", id, phaseNames[id] || id, bud.phases[id]);
    }).join("") + "</ul>" : "",
    models.length ? '<h4 class="lim-h2">Models</h4><ul class="spend-list">' + models.map(function (id) {
      return capRow("models", id, id, bud.models[id]);
    }).join("") + "</ul>" : "",
    '<h4 class="lim-h2">Top 5 tasks by spend</h4>' + (taskRows.length ? '<ul class="spend-list">' +
      taskRows.map(function (t) {
        return capRow("tasks", t.id, t.title || t.id, { spent: t.spentK, limit: t.capK });
      }).join("") + "</ul>" : '<p class="page-note">No task has spent tokens yet.</p>'),
  ];
  return parts.join("");
}

// Global spend: one row per project with today's and this week's tracked tokens and the estimated share (≈).
function projectTableHtml(vm) {
  const names = {};
  for (const p of vm.projects || []) names[p.id] = p.name;
  const body = (vm.snapshotList || []).map(function (snap) {
    const day = snap.dayUse || {};
    const week = snap.weekUse || {};
    const share = week.estPts == null ? MISSING : "≈ " + fmtPercent(week.estPts);
    return "<tr><th scope=\"row\">" + esc(names[snap.id] || snap.title) + "</th><td class=\"num\">" +
      esc(fmtTokens(day.tokK)) + '</td><td class="num">' + esc(fmtTokens(week.tokK)) +
      '</td><td class="num">' + esc(share) + "</td></tr>";
  }).join("");
  return '<table class="tk-table"><caption class="sr-only">Spend by project</caption><thead><tr>' +
    '<th scope="col">Project</th><th scope="col">Today</th><th scope="col">This week</th>' +
    '<th scope="col">Share of week</th></tr></thead><tbody>' + body + "</tbody></table>";
}

function overrideHtml(pid) {
  const options = OVERRIDE_HOURS.map(function (h) {
    return '<option value="' + h + '">' + h + (h === 1 ? " hour" : " hours") + "</option>";
  }).join("");
  const copy = copyButton("section", "tokens.override", "Override", { project: pid,
    sum: refSummary("section", OVERRIDE_HOURS.length) });
  return '<section class="ov-card" aria-labelledby="tk-override"><div class="lim-bar">' +
    '<h3 id="tk-override" class="lim-h">Override</h3>' + copy + "</div>" +
    '<p class="page-note">Temporarily ignore limits; logged in Activity.</p>' +
    '<div class="tk-override"><label class="lim-field"><span class="lim-label">For</span>' +
    '<select class="lim-select" data-focus="ov-hours">' + options + "</select></label>" +
    '<button type="button" class="btn" data-action="lim-override" aria-label="Apply override for ' + esc(pid) +
    '" data-focus="ov-go">Override</button></div></section>';
}

function accuracyHtml() {
  return '<div class="acc"><p class="acc-line">Percentages are estimates; ' +
    '<span class="acc-more">reported token counts exact.</span></p>' +
    "<details><summary>How these limits are measured</summary><ol>" +
    "<li>External usage skews project estimates higher.</li>" +
    "<li>Tokens are counted when jobs finish.</li>" +
    "<li>When the reader is off, those hours are added at the next reading, but they land on that day.</li>" +
    "</ol></details></div>";
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  attachLimitListeners();
  const isProject = vm.route.name === "project";
  const snap = isProject ? vm.project.snapshot : (vm.snapshotList || [])[0] || null;
  const pid = isProject ? vm.route.id : (vm.projects[0] ? vm.projects[0].id : null);
  // Copy refs name one project: the project view's own. All projects has none, so its section refs are omitted.
  const refPid = isProject ? pid : null;
  let rows = [];
  if (isProject) {
    rows = snap.meters || [];
  } else {
    const withMeters = (vm.snapshotList || []).find(function (s) {
      return Array.isArray(s.meters);
    });
    rows = withMeters ? withMeters.meters.filter(function (r) {
      return r.scope === "global";
    }) : [];
  }
  const scope = isProject ? "project" : "global";
  setLimitContext({ scope: scope, pid: pid, rows: rows });
  const measured = isProject ? snap.meters !== null : (vm.snapshotList || []).some(function (s) {
    return Array.isArray(s.meters);
  });
  const notice = measured ? "" : bannerHtml("warning", "Limits are not measured yet.",
    "Usage data still loading; limits unavailable.");
  const title = isProject ? "Tokens for " + vm.project.name : "Tokens for all projects";
  const head = '<div class="page-head"><h2 class="page-title">' + esc(title) + "</h2>" +
    '<p class="page-note">' + esc(isProject
      ? "Project limits, spend, and applicable global limits."
      : "All projects. Global limits and every project's spend.") + "</p></div>";
  const meters = '<section class="ov-card" aria-label="Meters">' +
    metersHtml(rows, snap, isProject) + "</section>";
  const spendCount = isProject ? (snap.tasks || []).filter(function (t) {
    return typeof t.tokensK === "number";
  }).length : (vm.snapshotList || []).length;
  const spend = isProject
    ? '<section class="ov-card" aria-labelledby="tk-spend"><div class="lim-bar">' +
      '<h3 id="tk-spend" class="lim-h">Spend</h3>' + copyButton("section", "tokens.spend", "Spend",
        { project: refPid, sum: refSummary("section", spendCount) }) + "</div>" + spendHtml(snap) + "</section>"
    : '<section class="ov-card" aria-labelledby="tk-spend"><div class="lim-bar">' +
      '<h3 id="tk-spend" class="lim-h">Spend</h3>' + copyButton("section", "tokens.spend", "Spend",
        { project: refPid, sum: refSummary("section", spendCount) }) + "</div>" + projectTableHtml(vm) + "</section>";
  const override = isProject ? overrideHtml(pid) : "";
  return head + notice + meters + '<section class="ov-card" aria-label="Limits">' + limitsHtml(scope, rows) +
    "</section>" + accountHtml(vm, rows, refPid) + spend + override +
    '<section class="ov-card" aria-label="Accuracy">' + accuracyHtml() + "</section>";
}

