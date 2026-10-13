// Overview (WP30). Project scope: a limit banner when a limit is at 80% or more (with an Override button), the Running
// or Stopped banner with one button, KPI tiles, the Inbox preview (up to 5), Agents live, meters (today, this week and
// the limit rows), open blockers and the newest 15 activity lines. All projects: the limit banner across projects, one
// card per project and Running now (home.js), and the Inbox across projects, grouped by project.

import { esc, meterHtml } from "../dom.js";
import { fmtCount, fmtTokens, MISSING } from "../format.js";
import { homeView } from "./home.js";
import { inboxHash, inboxPreviewHtml, itemHash, pageState, scopeSnapshots, watchCountdowns } from "./inbox.js";
import { activityRowHtml } from "./activity.js";
import { kpiView } from "./kpi.js";
import { runningSection } from "./running.js";
import { extrasSection } from "./extras.js";
import { legendSection } from "./legend.js";
import { nextSection } from "./next.js";
import { phasesSection } from "./phases.js";
import { recentSection } from "./recent.js";

const WARN_SHARE = 0.8;
const WINDOW_WORD = { day: "daily", week: "weekly", total: "total" };
const ACTIVITY_MAX = 15;
const PREVIEW_MAX = 5;

function round1(n) {
  return Math.round(n * 10) / 10;
}

// The limit row nearest its limit across the scopes, when it is at 80% or more (or already warn or block). Null when
// no row is that full. Rows that are unknown never count.
export function worstLimit(scopes) {
  let worst = null;
  for (const s of scopes) {
    const rows = s.snap.meters || [];
    for (const row of rows) {
      if (row.state === "unknown" || row.used == null || !(row.limit > 0)) continue;
      const share = row.used / row.limit;
      const hot = row.state === "warn" || row.state === "block" || share >= WARN_SHARE;
      if (hot && (worst === null || share > worst.share)) {
        worst = { row: row, share: share, pid: s.id, pname: s.name };
      }
    }
  }
  return worst;
}

// The row's amount in plain words: "8.5% of your weekly allowance", "120k of 500k tokens".
function amountText(row) {
  if (row.kind === "tok") return fmtTokens(row.used) + " of " + fmtTokens(row.limit) + " tokens";
  if (row.kind === "acct") return round1(row.used) + "% of the weekly account limit";
  return round1(row.used) + "% of " + row.limit + "% of your weekly allowance";
}

function limitBanner(worst, inProject) {
  if (!worst) return "";
  const row = worst.row;
  const pct = Math.round(worst.share * 100);
  const word = WINDOW_WORD[row.window] || "";
  const title = row.scope === "global"
    ? "Usage across all projects is at " + pct + "% of the " + word + " limit."
    : worst.pname + " is at " + pct + "% of its " + word + " limit.";
  const detail = amountText(row) + (row.est ? " (an estimate)." : ".") +
    (row.state === "block" ? " Work is stopped by this limit." : " Work keeps running.");
  const tone = row.state === "block" ? "danger" : "warning";
  const button = inProject
    ? '<p class="ov-actions"><button type="button" class="btn" data-action="override" data-project="' +
      esc(worst.pid) + '" data-focus="override">Override for 1 hour</button></p>'
    : '<p class="banner-detail">Open a project to override its limits.</p>';
  return '<div class="banner banner-' + tone + '" role="status"><p class="banner-title">' + esc(title) +
    '</p><p class="banner-detail">' + esc(detail) + "</p>" + button + "</div>";
}

// Running or Stopped, with one button (control.stop or control.resume), the same ops the top bar uses.
function controlBanner(vm) {
  const c = vm.control;
  if (!c || !c.known) return "";
  const offline = vm.conn.ok === false ? " disabled" : "";
  if (c.stopped) {
    return '<div class="banner banner-warning ov-control"><p class="banner-title">Stopped. No agent starts a new job.' +
      '</p><p class="ov-actions"><button type="button" class="btn" data-action="control" data-op="control.resume" ' +
      'data-project="' + esc(c.id) + '" data-focus="control"' + offline + ">Resume</button></p></div>";
  }
  const title = c.blocked ? "Blocked by a limit. Agents wait." : "Running. Agents may start jobs.";
  const detail = c.blocked && c.reason ? '<p class="banner-detail">' + esc(c.reason) + "</p>" : "";
  return '<div class="banner ov-control"><p class="banner-title">' + esc(title) + "</p>" + detail +
    '<p class="ov-actions"><button type="button" class="btn" data-action="control" data-op="control.stop" ' +
    'data-project="' + esc(c.id) + '" data-focus="control"' + offline + ">Stop</button></p></div>";
}

function limitLineHtml(row) {
  const share = row.limit > 0 && row.used != null ? Math.min(100, (row.used / row.limit) * 100) : null;
  const tone = row.state === "block" ? "danger" : row.state === "warn" ? "warning" : "accent";
  const label = (row.scope === "global" ? "All projects" : "This project") + ", " + (WINDOW_WORD[row.window] || "");
  const text = row.used == null || row.limit == null ? MISSING
    : (row.est ? "≈ " : "") + amountText(row);
  const pace = row.paceAt ? '<p class="mt-pace">At this pace the limit is reached about ' +
    esc(String(row.paceAt).slice(11, 16)) + "</p>" : "";
  return '<li class="mt-row"><p class="mt-label">' + esc(label) + "</p>" + meterHtml(share, tone) +
    '<p class="mt-text">' + esc(text) + "</p>" + pace + "</li>";
}

// Meters for one snapshot: today's and this week's use in plain words, then each limit row with its meter.
function metersBody(snap) {
  const day = snap.dayUse;
  const week = snap.weekUse;
  if (!snap.meters) return '<p class="placeholder">Usage is unknown until the next reading.</p>';
  const rows = snap.meters;
  const today = day && day.value != null ? "Today: " + round1(day.value) + " points of your weekly allowance"
    : "Today: " + MISSING;
  const thisWeek = week && week.value != null ? "This week: " + round1(week.value) + "% of your weekly allowance"
    : "This week: " + MISSING;
  const tokens = "Tokens tracked today " + (day && day.tokK != null ? fmtTokens(day.tokK) : MISSING) +
    ", this week " + (week && week.tokK != null ? fmtTokens(week.tokK) : MISSING) + ".";
  const list = rows.length
    ? '<ul class="mt-list">' + rows.map(limitLineHtml).join("") + "</ul>"
    : '<p class="placeholder">No limits set. Agents may use your whole weekly allowance.</p>';
  return '<p class="mt-line">' + esc(today) + "</p><p class=\"mt-line\">" + esc(thisWeek) + "</p>" +
    '<p class="mt-line">' + esc(tokens) + "</p>" + list;
}

function cardHtml(id, title, summary, body) {
  return '<section class="ov-card" aria-labelledby="ov-' + id + '-h"><h2 class="ov-h" id="ov-' + id + '-h">' +
    esc(title) + (summary ? ' <span class="ov-sum">' + esc(summary) + "</span>" : "") + "</h2>" + body + "</section>";
}

function blockersHtml(snap) {
  const blockers = snap.issues.filter(function (i) {
    return i.kind === "blocker";
  });
  if (!snap.blocked.length && !blockers.length) {
    return cardHtml("blockers", "Open blockers", "", '<p class="placeholder">No open blockers.</p>');
  }
  const tasks = snap.blocked.map(function (id) {
    return '<li class="nz-row"><a href="' + esc(itemHash(snap.id, id)) + '">' + esc(id) +
      "</a> is blocked</li>";
  });
  const issues = blockers.map(function (i) {
    return '<li class="nz-row">' + esc(i.id) + " " + esc(i.title) + (i.tasks.length
      ? " (blocks " + esc(i.tasks.join(", ")) + ")" : "") + "</li>";
  });
  return cardHtml("blockers", "Open blockers", fmtCount(snap.blocked.length) + " tasks",
    '<ul class="nz-list">' + tasks.concat(issues).join("") + "</ul>");
}

function activityHtml(snap, now) {
  const lines = snap.activity.slice().reverse().slice(0, ACTIVITY_MAX);
  const body = lines.length
    ? '<ol class="act-list">' + lines.map(function (line) {
      return activityRowHtml(line, snap.id, snap.title, now, false);
    }).join("") + "</ol>"
    : '<p class="placeholder">No activity yet.</p>';
  return cardHtml("activity", "Activity", "", body);
}

function projectOverview(vm) {
  const snap = vm.project.snapshot;
  const scopes = scopeSnapshots(vm);
  const now = Date.now();
  watchCountdowns();
  // WP32 restores the sections WP30 dropped: Phases (with a link to the Roadmap), Next up, Recent progress, Extras and
  // Legend. Each one is a section-header from the section modules, so it folds like the rest.
  const phases = phasesSection(vm) + '<p class="ov-more"><a href="#/p/' + esc(vm.route.id) +
    '/roadmap">Open Roadmap</a></p>';
  const main = controlBanner(vm) + kpiView(vm) +
    cardHtml("inbox", "Inbox", "", inboxPreviewHtml(vm, PREVIEW_MAX) +
      '<p class="ov-more"><a href="' + esc(inboxHash(vm)) + '">Open Inbox</a></p>') + runningSection(vm) + phases;
  const side = cardHtml("meters", "Meters", "", metersBody(snap)) + blockersHtml(snap) + activityHtml(snap, now) +
    nextSection(vm) + recentSection(vm) + extrasSection(vm) + legendSection(vm);
  return limitBanner(worstLimit(scopes), true) +
    '<div class="ov"><div class="ov-main">' + main + '</div><div class="ov-side">' + side + "</div></div>";
}

function allOverview(vm) {
  const scopes = scopeSnapshots(vm);
  const inbox = cardHtml("inbox", "Inbox", "", inboxPreviewHtml(vm, PREVIEW_MAX) +
    '<p class="ov-more"><a href="#/all/inbox">Open Inbox</a></p>');
  return limitBanner(worstLimit(scopes), false) +
    '<div class="ov"><div class="ov-main">' + homeView(vm) + '</div><div class="ov-side">' + inbox + "</div></div>";
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  return vm.route.name === "project" ? projectOverview(vm) : allOverview(vm);
}
