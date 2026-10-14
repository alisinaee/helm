// Projects tab (WP29): "All projects" first, then one row per project. Rows sort needs-you first, then running, then
// the rest, and by name inside each group. A row shows a status dot with its word, a progress meter and the badges:
// open questions, open blockers and running jobs. Questions and blockers are known only for the project whose
// snapshot is loaded, so other rows leave them out rather than show a guess. A project blocked by a limit shows a
// "Blocked" mark.

import { bannerHtml, emptyHtml, esc, meterHtml, skeletonHtml } from "../dom.js";
import { sectionById } from "../routes.js";
import { buildHash } from "../router.js";
import { copyButton } from "../ref.js";

const ICON_PATH = "/icons.svg#i-";

export function iconHtml(name) {
  return '<svg class="ico" aria-hidden="true" focusable="false"><use href="' + ICON_PATH + esc(name) +
    '"></use></svg>';
}

function plural(n, one, many) {
  return n + " " + (n === 1 ? one : many);
}

// The open-blocker count from a snapshot: open issues whose kind is "blocker". Null when no snapshot is loaded.
function blockersOf(snap) {
  if (!snap) return null;
  return snap.issues.filter(function (issue) {
    return issue.kind === "blocker";
  }).length;
}

// One row's facts: the summary row from /api/v1/projects, plus the snapshot when it is loaded.
export function rowFacts(summary, snap) {
  const questions = snap ? snap.questions.length : null;
  const blockers = blockersOf(snap);
  const blocked = Boolean(snap && snap.control.blocked);
  const stopped = Boolean(snap && snap.control.stopped);
  const needYou = (summary.needUser || 0) + (questions || 0) + (blockers || 0) > 0;
  const running = summary.running || 0;
  let state = "idle";
  let word = "Idle";
  if (blocked) {
    state = "blocked";
    word = "Blocked by limit";
  } else if (summary.stale) {
    state = "stale";
    word = "Stale";
  } else if (needYou) {
    state = "needs";
    word = "Needs you";
  } else if (running > 0) {
    state = "running";
    word = "Running";
  } else if (stopped) {
    state = "stopped";
    word = "Stopped";
  }
  return { id: summary.id, name: summary.name, progress: summary.progress, state: state, word: word,
    needYou: needYou, running: running, questions: questions, blockers: blockers, blocked: blocked };
}

// Needs-you rows first (rank 0), then running (1), then the rest (2). Ties go by name.
function rank(facts) {
  if (facts.needYou) return 0;
  if (facts.running > 0) return 1;
  return 2;
}

export function sortRows(list) {
  return list.slice().sort(function (a, b) {
    const diff = rank(a) - rank(b);
    if (diff !== 0) return diff;
    return String(a.name).localeCompare(String(b.name));
  });
}

// One fixed slot per count (questions, blockers, running) so the numbers line up down the panel; then the lock chip.
function countBadge(kind, n, icon, one, many) {
  return '<span class="p-badge" data-kind="' + kind + '" title="' + esc(plural(n, one, many)) + '">' +
    iconHtml(icon) + esc(n) + '<span class="sr-only"> ' + esc(plural(n, one, many)) + "</span></span>";
}

function badgesHtml(facts) {
  const q = facts.questions ? countBadge("question", facts.questions, "inbox", "open question", "open questions") : "";
  const b = facts.blockers ? countBadge("blocker", facts.blockers, "issues", "open blocker", "open blockers") : "";
  const r = facts.running > 0 ? countBadge("running", facts.running, "agents", "job running", "jobs running") : "";
  const lock = facts.blocked ? '<span class="p-chip" title="A usage limit is blocking this project">Locked</span>' : "";
  return "<span>" + q + "</span><span>" + b + "</span><span>" + r + "</span>" + lock;
}

function rowHtml(facts, route, current) {
  const section = sectionById(route.section) ? route.section : "overview";
  const href = buildHash({ name: "project", id: facts.id, section: section, view: null, item: null, filters: {} });
  const pct = facts.progress == null ? 0 : Math.round(facts.progress * 100);
  return '<li><a class="p-row" href="' + esc(href) + '" data-state="' + esc(facts.state) + '"' +
    (current ? ' aria-current="page"' : "") + ' title="' + esc(facts.name) + '">' +
    '<span class="p-head"><span class="p-dot" aria-hidden="true"></span><span class="p-name">' + esc(facts.name) +
    '</span><span class="p-word">' + esc(facts.word) + "</span></span>" +
    '<span class="p-meter">' + meterHtml(pct, facts.blocked ? "danger" : "accent") + '<span class="sr-only"> ' +
    esc(pct + "% done") + "</span></span>" +
    '<span class="p-badges row-grid">' + badgesHtml(facts) + "</span></a>" +
    copyButton("project", facts.id, facts.name, { project: facts.id }) + "</li>";
}

function allRowHtml(rows, route) {
  const needs = rows.filter(function (r) {
    return r.needYou;
  }).length;
  const running = rows.reduce(function (sum, r) {
    return sum + r.running;
  }, 0);
  const href = "#/all/" + (sectionById(route.section) ? route.section : "overview");
  const current = route.name !== "project";
  return '<li><a class="p-row p-all" href="' + esc(href) + '"' + (current ? ' aria-current="page"' : "") + ">" +
    '<span class="p-head"><span class="p-name">All projects</span><span class="p-word">' +
    esc(plural(rows.length, "project", "projects")) + "</span></span>" +
    '<span class="p-badges">' +
    (needs ? '<span class="p-badge" data-kind="needs">' + esc(needs) + '<span class="sr-only"> need you</span>' +
      "</span>" : "") +
    (running ? '<span class="p-badge" data-kind="running">' + iconHtml("agents") + esc(running) +
      '<span class="sr-only"> jobs running</span></span>' : "") +
    "</span></a></li>";
}

export function projectsView(vm) {
  if (vm.projectsError) {
    return bannerHtml("danger", "Projects could not be loaded.", vm.projectsError.message || "Unknown error");
  }
  if (!Array.isArray(vm.projects)) {
    return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90", "w-40"]) + "</div>";
  }
  if (vm.projects.length === 0) {
    return emptyHtml("No projects yet.", "<span>Add one from a project folder with roadmap project add.</span>");
  }
  // A snapshot's id is the project's config id, which can differ from the registry id the rows use. The current
  // project's snapshot is keyed by the route id; the others match when the two ids are the same.
  const byId = new Map();
  for (const snap of vm.snapshotList || []) byId.set(snap.id, snap);
  const current = vm.route.name === "project" ? vm.route.id : null;
  if (current && vm.project && vm.project.snapshot) byId.set(current, vm.project.snapshot);
  const facts = vm.projects.map(function (summary) {
    return rowFacts(summary, byId.get(summary.id) || null);
  });
  const rows = sortRows(facts).map(function (f) {
    return rowHtml(f, vm.route, f.id === current);
  }).join("");
  return '<ul class="p-list" aria-label="Projects">' + allRowHtml(facts, vm.route) + rows + "</ul>";
}
