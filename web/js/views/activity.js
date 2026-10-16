// Activity (WP30): the activity lines, newest first. In a project it is that project's lines; in All projects the lines
// of every project are merged by time (50 at most). Each line that can be undone has an Undo button (op undo). Source
// filters are LATER. The snapshot keeps the newest 15 lines per project, so that is what this page can show.

import { chipHtml, emptyHtml, esc } from "../dom.js";
import { MISSING, relTime } from "../format.js";
import { pageState, scopeSnapshots } from "./inbox.js";

const ALL_MAX = 50;
// The source names in plain words (the log keeps gui, cli, agent or phone).
const SOURCE_WORD = { gui: "Dashboard", cli: "Terminal", agent: "Agent", phone: "Phone" };

// One activity line as a list item. The Undo button is shown only when the line says it can be undone. Its visible
// label is the fixed word "Undo"; the full text (what it undoes) goes in aria-label and title.
// One row on a fixed grid: age | text (one line, ellipsis, full text in title) | source chip | icon-only Undo.
// "R10.4 done -> done" reads "R10.4 done → done" with no-break spaces around the arrow.
export function activityRowHtml(line, pid, pname, now, showProject) {
  const when = relTime(line.atMs, now);
  const what = line.sum || line.op || "change";
  const shown = esc(what).replace(/\s*(?:-&gt;|→)\s*/g, " → ");
  const label = esc("Undo " + what);
  const undo = line.undo
    ? '<button type="button" class="act-undo" data-action="undo-line" data-project="' + esc(pid) +
      '" data-activity="' + esc(line.id) + '" aria-label="' + label + '" title="' + label +
      '" data-focus="undo-' + esc(pid) + "-" + esc(line.id) + '"><svg class="ico" aria-hidden="true" ' +
      'focusable="false"><path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></svg></button>'
    : "";
  const chips = chipHtml(SOURCE_WORD[line.src] || "Other", "neutral") +
    (showProject ? chipHtml(pname, "neutral") : "");
  return '<li class="act-row row-grid"><span class="act-time num" title="' + esc(when.title) + '">' +
    esc(when.text || MISSING) + '</span><span class="act-sum" title="' + esc(what) + '">' + shown +
    '</span><span class="act-src">' + chips + "</span>" + undo + "</li>";
}

// The lines in view, newest first: [{line, pid, pname}].
export function mergedLines(scopes, limit) {
  const all = [];
  for (const s of scopes) {
    for (const line of s.snap.activity) all.push({ line: line, pid: s.id, pname: s.name });
  }
  all.sort(function (a, b) {
    return (b.line.atMs == null ? -Infinity : b.line.atMs) - (a.line.atMs == null ? -Infinity : a.line.atMs);
  });
  return limit ? all.slice(0, limit) : all;
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  const scopes = scopeSnapshots(vm);
  const showProject = vm.route.name !== "project";
  const now = Date.now();
  const lines = mergedLines(scopes, showProject ? ALL_MAX : 0);
  const note = showProject ? "Recent activity across projects." : "Recent project activity.";
  const body = lines.length
    ? '<ol class="act-list">' + lines.map(function (entry) {
      return activityRowHtml(entry.line, entry.pid, entry.pname, now, showProject);
    }).join("") + "</ol>"
    : emptyHtml("No activity yet.");
  return '<div class="page-head"><h2 class="page-title">Activity</h2><p class="page-note">' + esc(note) + "</p></div>" +
    '<section class="ov-card" aria-label="Activity log">' + body + "</section>";
}
