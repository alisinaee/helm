// Overview (WP30). Project scope: a limit banner when a limit is at 80% or more (with an Override button), the Running
// or Stopped banner with one button, KPI tiles, the Inbox preview (up to 5), Agents live, meters (today, this week and
// the limit rows), open blockers and the newest 15 activity lines. All projects: the limit banner across projects, one
// card per project and Running now (home.js), and the Inbox across projects, grouped by project.

import { esc, meterHtml } from "../dom.js";
import { fmtCount, fmtTokens } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { homeView } from "./home.js";
import { inboxHash, inboxPreviewHtml, itemHash, pageState, scopeSnapshots, watchCountdowns } from "./inbox.js";
import { activityRowHtml } from "./activity.js";
import { eventFromLine } from "./activity_data.js";
import { kpiView } from "./kpi.js";
import { runningSection } from "./running.js";
import { extrasSection } from "./extras.js";
import { legendSection } from "./legend.js";
import { nextSection } from "./next.js";
import { phasesSection } from "./phases.js";
import { recentSection } from "./recent.js";
import { overviewWorkHtml } from "./workitems.js";

const WARN_SHARE = 0.8;
const WINDOW_WORD = { day: "daily", week: "weekly", total: "total" };
const ACTIVITY_MAX = 15;
const PREVIEW_MAX = 5;
// The word for a value that is not known yet (a bare dash says nothing).
const UNKNOWN = "unknown";

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
    ? "All projects usage: " + pct + "% of the " + word + " limit."
    : worst.pname + " is at " + pct + "% of its " + word + " limit.";
  const detail = amountText(row) + (row.est ? " (an estimate)." : ".") +
    (row.state === "block" ? " Work stopped by limit." : " Work continues.");
  const tone = row.state === "block" ? "danger" : "warning";
  const button = inProject
    ? '<p class="ov-actions"><button type="button" class="btn" data-action="override" data-project="' +
      esc(worst.pid) + '" data-focus="override">Override for 1 hour</button></p>'
    : '<p class="banner-detail">Open a project to override its limits.</p>';
  return '<div class="banner banner-' + tone + '" role="status"><p class="banner-title">' + esc(title) +
    '</p><p class="banner-detail">' + esc(detail) + "</p>" + button + "</div>";
}

// Every Overview banner goes through one stack, so all of them share the same left edge, padding and grid.
function bannerStack(parts) {
  const items = parts.filter(Boolean);
  return items.length ? '<div class="ov-banners">' + items.join("") + "</div>" : "";
}

// Running or Stopped. Stopped keeps its Resume button; Running has no button here (the top bar holds Stop).
function controlBanner(vm) {
  const c = vm.control;
  if (!c || !c.known) return "";
  const offline = vm.conn.ok === false ? " disabled" : "";
  if (c.stopped) {
    return '<div class="banner banner-warning ov-control"><p class="banner-title">Stopped. No new jobs will run.' +
      '</p><p class="ov-actions"><button type="button" class="btn" data-action="control" data-op="control.resume" ' +
      'data-project="' + esc(c.id) + '" data-focus="control"' + offline + ">Resume</button></p></div>";
  }
  const title = c.blocked ? "Limit reached; execution paused." : "Running. Agents may start jobs.";
  const detail = c.blocked && c.reason ? '<p class="banner-detail">' + esc(c.reason) + "</p>" : "";
  return '<div class="banner ov-control"><p class="banner-title">' + esc(title) + "</p>" + detail + "</div>";
}

function limitLineHtml(row) {
  const share = row.limit > 0 && row.used != null ? Math.min(100, (row.used / row.limit) * 100) : null;
  const tone = row.state === "block" ? "danger" : row.state === "warn" ? "warning" : "accent";
  const label = (row.scope === "global" ? "All projects" : "This project") + ", " + (WINDOW_WORD[row.window] || "");
  const text = row.used == null || row.limit == null ? UNKNOWN
    : (row.est ? "≈ " : "") + amountText(row);
  const pace = row.paceAt ? '<p class="mt-pace">Projected limit reached at ' +
    esc(String(row.paceAt).slice(11, 16)) + "</p>" : "";
  return '<li class="mt-row"><p class="mt-label">' + esc(label) + "</p>" + meterHtml(share, tone) +
    '<p class="mt-text">' + esc(text) + "</p>" + pace + "</li>";
}

// Meters for one snapshot: today's and this week's use in plain words, then each limit row with its meter.
function metersBody(snap) {
  const day = snap.dayUse;
  const week = snap.weekUse;
  if (!snap.meters) return '<p class="placeholder">Usage pending next sync.</p>';
  const rows = snap.meters;
  const today = day && day.value != null ? "Today: " + round1(day.value) + " points of your weekly allowance"
    : "Today: " + UNKNOWN;
  const thisWeek = week && week.value != null ? "This week: " + round1(week.value) + "% of your weekly allowance"
    : "This week: " + UNKNOWN;
  const tokens = "Tokens tracked today " + (day && day.tokK != null ? fmtTokens(day.tokK) : UNKNOWN) +
    ", this week " + (week && week.tokK != null ? fmtTokens(week.tokK) : UNKNOWN) + ".";
  const list = rows.length
    ? '<ul class="mt-list">' + rows.map(limitLineHtml).join("") + "</ul>"
    : '<p class="placeholder">No limits set; full allowance available.</p>';
  return '<p class="mt-line">' + esc(today) + "</p><p class=\"mt-line\">" + esc(thisWeek) + "</p>" +
    '<p class="mt-line">' + esc(tokens) + "</p>" + list;
}

// ref ({ project, count }) adds the section copy-reference button to the header. Cards without it get none.
function cardHtml(id, title, summary, body, ref) {
  const copy = ref ? copyButton("section", "overview." + id, title,
    { project: ref.project, sum: refSummary("section", ref.count) }) : "";
  return '<section class="ov-card" aria-labelledby="ov-' + id + '-h"><h2 class="ov-h" id="ov-' + id + '-h">' +
    esc(title) + (summary ? ' <span class="ov-sum">' + esc(summary) + "</span>" : "") + copy + "</h2>" + body +
    "</section>";
}

// The copy-reference button of a task row (the row's own link stays the link).
function taskCopy(snap, id) {
  const task = snap.tasks.filter(function (t) {
    return t.id === id;
  })[0] || null;
  return copyButton("task", id, task ? task.title : id, { project: snap.id, sum: refSummary("task", task, snap) });
}

function blockersHtml(snap) {
  const blockers = snap.issues.filter(function (i) {
    return i.kind === "blocker";
  });
  const count = snap.blocked.length + blockers.length;
  if (!snap.blocked.length && !blockers.length) {
    return cardHtml("blockers", "Open blockers", "", '<p class="placeholder">No open blockers.</p>',
      { project: snap.id, count: 0 });
  }
  const tasks = snap.blocked.map(function (id) {
    return '<li class="nz-row nz-slot"><span class="nz-txt"><a href="' + esc(itemHash(snap.id, id)) + '">' + esc(id) +
      "</a> is blocked</span>" + taskCopy(snap, id) + "</li>";
  });
  // The issue rows keep the same two tracks: the text, then an empty action slot.
  const issues = blockers.map(function (i) {
    return '<li class="nz-row nz-slot"><span class="nz-txt">' + esc(i.id) + " " + esc(i.title) + (i.tasks.length
      ? " (blocks " + esc(i.tasks.join(", ")) + ")" : "") + '</span><span class="nz-act"></span></li>';
  });
  return cardHtml("blockers", "Open blockers", fmtCount(snap.blocked.length) +
    (snap.blocked.length === 1 ? " task" : " tasks"),
    '<ul class="nz-list">' + tasks.concat(issues).join("") + "</ul>", { project: snap.id, count: count });
}

// The row markup and styles belong to the Activity page; the Overview card loads the same stylesheet once.
function ensureActivityCss() {
  if (typeof document === "undefined" || document.querySelector("link[data-hx-css]")) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/css/activity.css";
  link.setAttribute("data-hx-css", "1");
  document.head.appendChild(link);
}

function activityHtml(snap, now) {
  const lines = snap.activity.slice().reverse().slice(0, ACTIVITY_MAX);
  ensureActivityCss();
  const ctx = { pid: snap.id, now: now, sel: null, fresh: null, all: false };
  const body = lines.length
    ? '<ol class="act-list hx-list">' + lines.map(function (line) {
      return activityRowHtml(eventFromLine(line, snap.id, snap.title), ctx);
    }).join("") + "</ol>"
    : '<p class="placeholder">No activity yet.</p>';
  return cardHtml("activity", "Activity", "", body, { project: snap.id, count: lines.length });
}

// One line with the open asks the head has not handled yet; links to the Head screen. Empty when there are none.
function headChip(snap) {
  const n = (snap.head && snap.head.counts && snap.head.counts.unhandled) || 0;
  if (!(n > 0)) return "";
  return '<p class="ov-chip"><a href="#/p/' + esc(snap.id) + '/head?f=unhandled">' + esc(n) +
    (n === 1 ? " ask" : " asks") + " unhandled</a></p>";
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
  const main = headChip(snap) + kpiView(vm) +
    cardHtml("inbox", "Inbox", "", inboxPreviewHtml(vm, PREVIEW_MAX) +
      '<p class="ov-more"><a href="' + esc(inboxHash(vm)) + '">Open Inbox</a></p>',
    { project: snap.id, count: snap.needUser }) + runningSection(vm) + phases;
  const meterCount = snap.meters ? snap.meters.length : 0;
  const workList = overviewWorkHtml(snap);
  const side = (workList ? cardHtml("work", "Work", "", workList, { project: snap.id, count: snap.work.length }) : "") +
    cardHtml("meters", "Meters", "", metersBody(snap), { project: snap.id, count: meterCount }) +
    blockersHtml(snap) + activityHtml(snap, now) +
    nextSection(vm) + recentSection(vm) + extrasSection(vm) + legendSection(vm);
  return bannerStack([limitBanner(worstLimit(scopes), true), controlBanner(vm)]) +
    '<div class="ov"><div class="ov-main">' + main + '</div><div class="ov-side">' + side + "</div></div>";
}

function allOverview(vm) {
  const scopes = scopeSnapshots(vm);
  const inbox = cardHtml("inbox", "Inbox", "", inboxPreviewHtml(vm, PREVIEW_MAX) +
    '<p class="ov-more"><a href="#/all/inbox">Open Inbox</a></p>');
  return bannerStack([limitBanner(worstLimit(scopes), false)]) +
    '<div class="ov"><div class="ov-main">' + homeView(vm) + '</div><div class="ov-side">' + inbox + "</div></div>";
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  return vm.route.name === "project" ? projectOverview(vm) : allOverview(vm);
}
