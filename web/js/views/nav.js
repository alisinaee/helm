// Left nav (WP28): the section list with badges and the settings link at the foot. The bottom bar (small screens)
// shows the first four sections, then More, which opens a sheet with the rest. Badges come from countsFor().

import { esc } from "../dom.js";
import { sectionHash } from "../router.js";
import { SECTIONS, SETTINGS } from "../routes.js";

let moreOpen = false;

export function toggleMore() {
  moreOpen = !moreOpen;
}

function icon(name) {
  return '<svg class="ico" aria-hidden="true" focusable="false"><use href="/icons.svg#i-' + esc(name) +
    '"></use></svg>';
}

const STALE_MS = 30 * 60 * 1000;

// Running jobs seen recently: running or claimed, ignoring a job whose heartbeat is older than 30 minutes
// (a job with no heartbeat field is kept).
// A snapshot without job rows falls back to its own running count.
function liveRunning(snap) {
  if (!Array.isArray(snap.running)) return snap.runningCount || 0;
  const now = Date.now();
  return snap.running.filter(function (j) {
    const at = j.updatedMs || j.heartbeatMs;
    return typeof at !== "number" || now - at <= STALE_MS;
  }).length;
}

const SEEN_KEY = "helm.nav.seen";

function readSeen() {
  try {
    const raw = JSON.parse(localStorage.getItem(SEEN_KEY) || "{}");
    return raw && typeof raw === "object" ? raw : {};
  } catch (e) {
    return {};
  }
}

// Opening a section marks its current count seen (called by navView for the current section).
function markSeen(id, n) {
  try {
    const seen = readSeen();
    if (seen[id] === n) return;
    seen[id] = n;
    localStorage.setItem(SEEN_KEY, JSON.stringify(seen));
  } catch (e) { /* storage blocked: no new state */ }
}

// Counts for the badges. Scope is the project in a project route, else every registered project.
export function countsFor(vm) {
  const snaps = vm.snapshotList || [];
  let questions = 0;
  let needYou = 0;
  let blockers = 0;
  let running = 0;
  let tasksNeedingYou = 0;
  let headAsks = 0;
  for (const snap of snaps) {
    // Open asks the head has not handled yet (HEAD-SPEC section 5, snapshot head.counts.unhandled).
    headAsks += (snap.head && snap.head.counts && snap.head.counts.unhandled) || 0;
    // The same rows the Inbox page lists: open questions, and the needs-you task rows.
    questions += (snap.questions || []).length;
    needYou += (snap.needsYou || []).filter(function (row) {
      return row.kind === "task";
    }).length;
    // Head rows the head marked needs-you (the Inbox's Head asks, R7.81).
    needYou += ((snap.head && snap.head.rows) || []).filter(function (row) {
      return row && row.status === "needs-you";
    }).length;
    blockers += (snap.issues || []).filter(function (issue) {
      return issue.kind === "blocker";
    }).length;
    running += liveRunning(snap);
    tasksNeedingYou += snap.tasks.filter(function (t) {
      return t.needsUser;
    }).length;
  }
  let limitTone = null;
  for (const row of vm.meterRows || []) {
    if (row.state === "block") limitTone = "danger";
    else if (row.state === "warn" && limitTone !== "danger") limitTone = "warning";
  }
  return { inbox: questions + needYou, work: tasksNeedingYou, agents: running, tokens: limitTone,
    issues: blockers, head: headAsks };
}

const BADGES = {
  inbox: { key: "inbox", tone: "neutral", word: "waiting for you" },
  head: { key: "head", tone: "neutral", word: "open asks" },
  work: { key: "work", tone: "neutral", word: "need you" },
  agents: { key: "agents", tone: "success", word: "running" },
};

function badgeFor(section, counts, seen, current) {
  if (section.id === "tokens" && counts.tokens) {
    const label = counts.tokens === "danger" ? "limit reached" : "limit warning";
    return '<span class="nav-b" data-tone="' + esc(counts.tokens) + '" data-dot="1" title="' + label + '">' +
      '<span class="sr-only">' + esc(label) + "</span></span>";
  }
  const def = BADGES[section.id];
  if (!def) return "";
  let n = counts[def.key] || 0;
  let tone = def.tone;
  let word = def.word;
  if (section.id === "work") {
    n = counts.work + counts.issues;
    tone = counts.issues > 0 ? "danger" : "neutral";
    word = counts.issues > 0 ? "need you or blocked" : "need you";
  }
  if (n <= 0) return "";
  if (current) markSeen(section.id, n);
  const fresh = !current && typeof seen[section.id] === "number" && n > seen[section.id];
  return '<span class="nav-b" data-tone="' + tone + '"' + (fresh ? ' data-new="1"' : "") + ' title="' + n + " " +
    word + '"><span aria-hidden="true">' + (n > 99 ? "99+" : n) + '</span><span class="sr-only">' + n + " " +
    word + "</span></span>";
}

function linkHtml(vm, section, counts) {
  const current = vm.route.section === section.id;
  return '<a class="nav-i" href="' + esc(sectionHash(vm.route, section.id)) + '"' +
    (current ? ' aria-current="page"' : "") + ' title="' + esc(section.label) + '">' +
    icon(section.icon) + '<span class="nav-l">' + esc(section.label) + "</span>" +
    badgeFor(section, counts, readSeen(), current) + "</a>";
}

export function navView(vm) {
  const counts = countsFor(vm);
  const mini = vm.ui.navMini;
  const list = SECTIONS.map(function (s) {
    return linkHtml(vm, s, counts);
  }).join("");
  return '<p class="nav-brand" title="Helm">' + (mini ? "H" : "Helm") + "</p>" +
    '<div class="nav-list">' + list + "</div>" +
    '<div class="nav-foot">' + linkHtml(vm, SETTINGS, counts) +
    '<button type="button" class="nav-collapse" data-action="nav-mini" aria-label="' +
    (mini ? "Expand menu" : "Collapse menu") + '">' + icon(mini ? "expand" : "collapse") +
    '<span class="nav-l">' + (mini ? "Expand" : "Collapse") + "</span></button></div>";
}

export function bnavView(vm) {
  const counts = countsFor(vm);
  const bottom = SECTIONS.filter(function (s) {
    return s.bottom;
  });
  const rest = SECTIONS.filter(function (s) {
    return !s.bottom;
  }).concat([SETTINGS]);
  const more = '<button type="button" class="bnav-i" data-action="toggle-more" data-focus="bnav-more"' +
    ' aria-expanded="' + moreOpen + '" aria-controls="bnav-more">' + icon("more") +
    '<span class="nav-l">More</span></button>';
  const sheet = '<div id="bnav-more" class="sheet"' + (moreOpen ? "" : " hidden") + ">" +
    rest.map(function (s) {
      return linkHtml(vm, s, counts);
    }).join("") + "</div>";
  return sheet + '<div class="bnav-row">' + bottom.map(function (s) {
    return linkHtml(vm, s, counts).replace('class="nav-i"', 'class="bnav-i"');
  }).join("") + more + "</div>";
}
