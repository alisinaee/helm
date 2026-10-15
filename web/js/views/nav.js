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
    running += snap.runningCount || 0;
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

function badgeFor(section, counts) {
  if (section.id === "inbox" && counts.inbox > 0) {
    return '<span class="nav-b" data-tone="neutral">' + esc(counts.inbox) +
      '<span class="sr-only"> waiting for you</span></span>';
  }
  if (section.id === "issues" && counts.issues > 0) {
    return '<span class="nav-b" data-tone="danger">' + esc(counts.issues) +
      '<span class="sr-only">' + (counts.issues === 1 ? " open blocker" : " open blockers") + "</span></span>";
  }
  if (section.id === "head" && counts.head > 0) {
    return '<span class="nav-b" data-tone="neutral">' + esc(counts.head) +
      '<span class="sr-only"> open asks</span></span>';
  }
  if (section.id === "work" && counts.work > 0) {
    return '<span class="nav-b" data-tone="danger">' + esc(counts.work) +
      '<span class="sr-only"> tasks need you</span></span>';
  }
  if (section.id === "agents" && counts.agents > 0) {
    return '<span class="nav-b" data-tone="success">' + esc(counts.agents) +
      '<span class="sr-only"> running</span></span>';
  }
  if (section.id === "tokens" && counts.tokens) {
    const label = counts.tokens === "danger" ? "limit reached" : "limit warning";
    return '<span class="nav-b" data-tone="' + esc(counts.tokens) + '" data-dot="1">' +
      '<span class="sr-only">' + esc(label) + "</span></span>";
  }
  return "";
}

function linkHtml(vm, section, counts) {
  const current = vm.route.section === section.id;
  return '<a class="nav-i" href="' + esc(sectionHash(vm.route, section.id)) + '"' +
    (current ? ' aria-current="page"' : "") + ' title="' + esc(section.label) + '">' +
    icon(section.icon) + '<span class="nav-l">' + esc(section.label) + "</span>" +
    badgeFor(section, counts) + "</a>";
}

export function navView(vm) {
  const counts = countsFor(vm);
  const mini = vm.ui.navMini;
  const list = SECTIONS.map(function (s) {
    return linkHtml(vm, s, counts);
  }).join("");
  return '<div class="nav-list">' + list + "</div>" +
    '<div class="nav-foot">' + linkHtml(vm, SETTINGS, counts) +
    '<button type="button" class="nav-collapse" data-action="nav-mini" aria-label="' +
    (mini ? "Expand menu" : "Collapse menu") + '">' + icon("collapse") +
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
